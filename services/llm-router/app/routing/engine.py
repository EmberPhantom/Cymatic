"""Routing Policy Engine - Task-based and sensitivity-based routing with circuit breaker"""

import copy
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import BaseModel

from app.routing.circuit_breaker import (
    can_execute_provider,
    get_all_circuit_breaker_status,
    get_circuit_breaker,
    record_provider_failure,
    record_provider_success,
)
from app.routing.circuit_breaker import CircuitState
from app.schemas.providers import (
    DEFAULT_PROVIDERS,
    ModelProfile,
    ProviderConfig,
    ProviderName,
    ProviderStatus,
    RoutingPolicy,
    SensitivityLevel,
    TaskType,
)

logger = structlog.get_logger()


class RoutingDecision(BaseModel):
    provider: ProviderName
    model: str
    model_profile: ModelProfile
    reason: str
    fallback: ProviderName | None = None


class RoutingEngine:
    """Routes LLM requests to appropriate providers based on task and sensitivity with circuit breaker protection."""

    def __init__(self) -> None:
        # Deep copy so per-engine toggles (e.g. LOCAL enabled flag) never
        # mutate the global DEFAULT_PROVIDERS shared across engines/tests.
        self.providers: dict[ProviderName, ProviderConfig] = copy.deepcopy(
            DEFAULT_PROVIDERS
        )
        self.policies: dict[str, RoutingPolicy] = {}
        self.status: dict[ProviderName, ProviderStatus] = {}
        self._apply_provider_flags()
        self._initialize_default_policies()
        self._initialize_status()

    def _apply_provider_flags(self) -> None:
        """Enable/disable providers from settings.

        - LOCAL: enabled if ENABLE_LOCAL_LLM=true
        - GROQ/OPENROUTER/NVIDIA/OPENAI/SARVAM/APINEX: enabled iff API key non-empty.
          This prevents routing to providers without credentials (P0-2:
          OPENAI was marked enabled with empty key and shadowed working GROQ).
        """
        try:
            from app.core.config import get_settings

            settings = get_settings()

            def _has_key(value: object) -> bool:
                return bool(value and isinstance(value, str) and value.strip())

            local_enabled = bool(settings.ENABLE_LOCAL_LLM)
            apinex_key = getattr(settings, "APINEX_API_KEY", "")
            apinex_enabled = _has_key(apinex_key)
            groq_enabled = _has_key(getattr(settings, "GROQ_API_KEY", ""))
            openrouter_enabled = _has_key(getattr(settings, "OPENROUTER_API_KEY", ""))
            nvidia_enabled = _has_key(getattr(settings, "NVIDIA_NIM_API_KEY", ""))
            openai_enabled = _has_key(getattr(settings, "OPENAI_API_KEY", ""))
            sarvam_enabled = _has_key(getattr(settings, "SARVAM_API_KEY", ""))
        except Exception:
            local_enabled = False
            apinex_enabled = False
            groq_enabled = False
            openrouter_enabled = False
            nvidia_enabled = False
            openai_enabled = False
            sarvam_enabled = False
            apinex_key = ""

        local = self.providers.get(ProviderName.LOCAL)
        if local is not None:
            local.enabled = local_enabled

        for name, enabled in (
            (ProviderName.GROQ, groq_enabled),
            (ProviderName.OPENROUTER, openrouter_enabled),
            (ProviderName.NVIDIA_NIM, nvidia_enabled),
            (ProviderName.OPENAI, openai_enabled),
            (ProviderName.SARVAM, sarvam_enabled),
        ):
            cfg = self.providers.get(name)
            if cfg is not None:
                cfg.enabled = enabled

        apinex = self.providers.get(ProviderName.APINEX)
        if apinex is not None:
            apinex.enabled = apinex_enabled
            if apinex_enabled:
                try:
                    apinex.api_key = apinex_key
                    apinex.base_url = getattr(
                        settings, "APINEX_BASE_URL", "https://api.apinex.bond/v1"
                    )
                except Exception:
                    pass

    def _apply_local_llm_flag(self) -> None:
        """Backward-compatible alias for _apply_provider_flags."""
        self._apply_provider_flags()

    def _initialize_status(self) -> None:
        """Initialize provider status for all configured providers."""
        for provider_name in ProviderName:
            self.status[provider_name] = ProviderStatus(name=provider_name)

    def _initialize_default_policies(self) -> None:
        """Initialize default routing policies (table in policies.py).

        When APInex is active, it is the primary cloud provider with
        free/glm-5.3-flash. When LOCAL is off and APInex is off, prefer a
        keyed cloud model directly (P0-2: previously preferred phi-3-mini
        with LOCAL not in allowed list, forcing every request through
        fallback/last-resort).
        """
        from app.routing.policies import build_default_policies

        try:
            from app.core.config import get_settings

            settings = get_settings()
            local_enabled = bool(getattr(settings, "ENABLE_LOCAL_LLM", False))
            apinex_key = getattr(settings, "APINEX_API_KEY", "")
            apinex_active = bool(apinex_key and apinex_key.strip())
        except Exception:
            local_enabled = False
            apinex_active = False

        self.policies = build_default_policies(
            local_enabled=local_enabled, apinex_active=apinex_active
        )
        # --- legacy inline table follows (now unreachable, kept for reference
        # during review; delete after one green cycle) ---

    def get_policy(
        self, task_type: TaskType, sensitivity: SensitivityLevel
    ) -> RoutingPolicy:
        """Get routing policy for task and sensitivity (fail-closed to paid)."""
        key = f"{task_type}_{sensitivity}"
        policy = self.policies.get(key)
        if policy is not None:
            return policy
        logger.warning(
            "routing_policy_missing", task=str(task_type), sensitivity=str(sensitivity)
        )
        # Fail-closed: never fall back to free GROQ/OPENROUTER for unknown combos,
        # especially TENANT_SENSITIVE/REGULATED. Default to paid OpenAI.
        return RoutingPolicy(
            task_type=task_type,
            sensitivity=sensitivity,
            preferred_profile="gpt-4o-mini",
            fallback_profile=None,
            allowed_providers=[ProviderName.OPENAI],
            blocked_providers=[
                ProviderName.GROQ,
                ProviderName.OPENROUTER,
                ProviderName.APINEX,
            ],
        )

    def route(
        self,
        task_type: TaskType,
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
    ) -> RoutingDecision:
        """Route request to best provider with circuit breaker protection (single source of truth)."""
        policy = self.get_policy(task_type, sensitivity)

        # Find preferred provider
        for provider_name in policy.allowed_providers:
            if provider_name in policy.blocked_providers:
                continue

            provider = self.providers.get(provider_name)
            if not provider or not provider.enabled:
                continue

            # Check sensitivity support
            if sensitivity not in provider.supported_sensitivity:
                continue

            # Check circuit breaker – single source of truth, no dual healthy check
            if not can_execute_provider(provider_name):
                logger.warning("circuit_breaker_open", provider=provider_name)
                continue

            # Check if provider has the model
            model_profile = provider.models.get(policy.preferred_profile)
            if model_profile:
                fallback: ProviderName | None = None
                if policy.fallback_profile:
                    for fb_provider in policy.allowed_providers:
                        if fb_provider != provider_name:
                            fb_config = self.providers.get(fb_provider)
                            if (
                                fb_config
                                and fb_config.enabled
                                and fb_config.models.get(policy.fallback_profile)
                                and can_execute_provider(fb_provider)
                            ):
                                fallback = fb_provider
                                break

                return RoutingDecision(
                    provider=provider_name,
                    model=policy.preferred_profile,
                    model_profile=model_profile,
                    reason=f"Preferred model for {task_type} at {sensitivity} sensitivity",
                    fallback=fallback,
                )

        # Try fallback profile
        if policy.fallback_profile:
            for provider_name in policy.allowed_providers:
                if provider_name in policy.blocked_providers:
                    continue
                provider = self.providers.get(provider_name)
                if not provider or not provider.enabled:
                    continue
                if sensitivity not in provider.supported_sensitivity:
                    continue

                if not can_execute_provider(provider_name):
                    continue

                model_profile = provider.models.get(policy.fallback_profile)
                if model_profile:
                    return RoutingDecision(
                        provider=provider_name,
                        model=policy.fallback_profile,
                        model_profile=model_profile,
                        reason=f"Fallback model for {task_type} at {sensitivity} sensitivity",
                        fallback=None,
                    )

        # Last resort: any available provider with compatible model
        for provider_name in policy.allowed_providers:
            if provider_name in policy.blocked_providers:
                continue
            provider = self.providers.get(provider_name)
            if not provider or not provider.enabled:
                continue
            if sensitivity not in provider.supported_sensitivity:
                continue

            if not can_execute_provider(provider_name):
                continue

            for model_id, model_profile in provider.models.items():
                if task_type in model_profile.task_types:
                    return RoutingDecision(
                        provider=provider_name,
                        model=model_id,
                        model_profile=model_profile,
                        reason=f"Last resort model for {task_type}",
                        fallback=None,
                    )

        raise ValueError(
            f"No available provider for {task_type} at {sensitivity} sensitivity. "
            "Check /health hint: start ollama with '--profile local' + "
            "'ollama pull phi3:mini' and ENABLE_LOCAL_LLM=true, or set "
            "APINEX_API_KEY/GROQ_API_KEY/OPENROUTER_API_KEY."
        )

    def record_provider_result(
        self, provider: ProviderName | str, success: bool, latency_ms: float = 0
    ) -> None:
        """Record provider request result for circuit breaker and sync status from breaker state."""
        if success:
            record_provider_success(provider)
        else:
            record_provider_failure(provider)

        # Update provider status - resolve str to ProviderName if possible
        provider_key: ProviderName | None = None
        if isinstance(provider, ProviderName):
            provider_key = provider
        else:
            try:
                provider_key = ProviderName(provider)
            except ValueError:
                return
        if provider_key in self.status:
            # Single source of truth: healthy derived from circuit breaker state
            try:
                cb = get_circuit_breaker(provider_key)
                healthy = cb.state != CircuitState.OPEN
            except Exception:
                healthy = success
            # Only mark unhealthy when circuit is open; keep latency/error tracking
            self.status[provider_key].healthy = healthy
            self.status[provider_key].latency_ms = latency_ms
            if not success:
                self.status[provider_key].error_count += 1
            else:
                # On success, decay error count if circuit closed
                if healthy and self.status[provider_key].error_count > 0:
                    self.status[provider_key].error_count = max(
                        0, self.status[provider_key].error_count - 1
                    )
            self.status[provider_key].last_check = datetime.now(
                timezone.utc
            ).isoformat()

    def get_circuit_breaker_status(self) -> dict[str, dict[str, Any]]:
        """Get circuit breaker status for all providers."""
        return get_all_circuit_breaker_status()

    def update_provider_config(self, provider: ProviderConfig) -> None:
        """Update provider configuration."""
        self.providers[provider.name] = provider

    def update_provider_status(
        self,
        name: ProviderName,
        healthy: bool,
        latency_ms: float = 0,
        error_count: int = 0,
    ) -> None:
        """Update provider health status."""
        self.status[name].healthy = healthy
        self.status[name].latency_ms = latency_ms
        self.status[name].error_count = error_count
        self.status[name].last_check = datetime.now(timezone.utc).isoformat()

    def get_provider_status(self) -> dict[ProviderName, ProviderStatus]:
        return self.status


# Global routing engine
routing_engine = RoutingEngine()


def route_request(
    task_type: TaskType, sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
) -> RoutingDecision:
    """Convenience function for routing."""
    return routing_engine.route(task_type, sensitivity)


def get_routing_policy(
    task_type: TaskType, sensitivity: SensitivityLevel
) -> RoutingPolicy:
    """Get routing policy."""
    return routing_engine.get_policy(task_type, sensitivity)

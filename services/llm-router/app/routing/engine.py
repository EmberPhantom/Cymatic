"""Routing Policy Engine - Task-based and sensitivity-based routing with circuit breaker"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from app.schemas.providers import (
    ProviderConfig, ModelProfile, RoutingPolicy, TaskType, SensitivityLevel,
    ProviderName, DEFAULT_PROVIDERS, ProviderStatus
)
from app.routing.circuit_breaker import (
    get_circuit_breaker, record_provider_success, record_provider_failure,
    can_execute_provider, get_circuit_breaker_status, get_all_circuit_breaker_status
)
import structlog
from datetime import datetime

logger = structlog.get_logger()


class RoutingDecision(BaseModel):
    provider: ProviderName
    model: str
    model_profile: ModelProfile
    reason: str
    fallback: Optional[ProviderName] = None


class RoutingEngine:
    """Routes LLM requests to appropriate providers based on task and sensitivity with circuit breaker protection."""
    
    def __init__(self):
        self.providers: Dict[ProviderName, ProviderConfig] = DEFAULT_PROVIDERS.copy()
        self.policies: Dict[str, RoutingPolicy] = {}
        self.status: Dict[ProviderName, ProviderStatus] = {}
        self._initialize_default_policies()
        self._initialize_status()
    
    def _initialize_status(self):
        """Initialize provider status for all configured providers."""
        for provider_name in ProviderName:
            self.status[provider_name] = ProviderStatus(name=provider_name)

    def _initialize_default_policies(self):
        """Initialize default routing policies."""
        # Task-based routing with sensitivity
        self.policies = {
            # Fast/small model for intent extraction
            f"{TaskType.INTENT_EXTRACTION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.INTENT_EXTRACTION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            f"{TaskType.INTENT_EXTRACTION}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.INTENT_EXTRACTION,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            f"{TaskType.INTENT_EXTRACTION}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.INTENT_EXTRACTION,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="gpt-4o-mini",
                fallback_profile="nvidia/nemotron-3-ultra",
                allowed_providers=[ProviderName.OPENAI, ProviderName.NVIDIA_NIM],
            ),
            
            # Strong reasoning for spec generation
            f"{TaskType.SPEC_GENERATION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.SPEC_GENERATION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.SPEC_GENERATION}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.SPEC_GENERATION,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.SPEC_GENERATION}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.SPEC_GENERATION,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="gpt-4o",
                fallback_profile="nvidia/nemotron-3-ultra",
                allowed_providers=[ProviderName.OPENAI, ProviderName.NVIDIA_NIM],
            ),
            f"{TaskType.SPEC_GENERATION}_{SensitivityLevel.REGULATED}": RoutingPolicy(
                task_type=TaskType.SPEC_GENERATION,
                sensitivity=SensitivityLevel.REGULATED,
                preferred_profile="gpt-4o",
                fallback_profile=None,
                allowed_providers=[ProviderName.OPENAI],
                blocked_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            
            # Structured output reliable for validation
            f"{TaskType.VALIDATION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.VALIDATION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.VALIDATION}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.VALIDATION,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.VALIDATION}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.VALIDATION,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="gpt-4o",
                fallback_profile="nvidia/nemotron-3-ultra",
                allowed_providers=[ProviderName.OPENAI, ProviderName.NVIDIA_NIM],
            ),
            
            # Low latency for copilot chat
            f"{TaskType.COPILOT_CHAT}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.COPILOT_CHAT,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            f"{TaskType.COPILOT_CHAT}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.COPILOT_CHAT,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            f"{TaskType.COPILOT_CHAT}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.COPILOT_CHAT,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="gpt-4o-mini",
                fallback_profile="nvidia/nemotron-3-ultra",
                allowed_providers=[ProviderName.OPENAI, ProviderName.NVIDIA_NIM],
            ),
            
            # Embeddings
            f"{TaskType.EMBEDDING}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.EMBEDDING,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="text-embedding-3-small",
                fallback_profile=None,
                allowed_providers=[ProviderName.OPENAI],
            ),
            f"{TaskType.EMBEDDING}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.EMBEDDING,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="text-embedding-3-small",
                fallback_profile=None,
                allowed_providers=[ProviderName.OPENAI],
            ),
            f"{TaskType.EMBEDDING}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.EMBEDDING,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="text-embedding-3-small",
                fallback_profile=None,
                allowed_providers=[ProviderName.OPENAI],
            ),
            
            # Clarification - fast model
            f"{TaskType.CLARIFICATION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.CLARIFICATION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            f"{TaskType.CLARIFICATION}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.CLARIFICATION,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-8b-instant",
                fallback_profile="gpt-4o-mini",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
            ),
            
            # Research - larger context
            f"{TaskType.RESEARCH}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.RESEARCH,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="google/gemini-pro-1.5",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.OPENROUTER],
            ),
            f"{TaskType.RESEARCH}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.RESEARCH,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="google/gemini-pro-1.5",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.OPENROUTER],
            ),
            
            # Domain expert - strong reasoning
            f"{TaskType.DOMAIN_EXPERT}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.DOMAIN_EXPERT,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.DOMAIN_EXPERT}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.DOMAIN_EXPERT,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="llama-3.1-70b-versatile",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.GROQ, ProviderName.OPENROUTER],
            ),
            f"{TaskType.DOMAIN_EXPERT}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.DOMAIN_EXPERT,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="gpt-4o",
                fallback_profile="nvidia/nemotron-3-ultra",
                allowed_providers=[ProviderName.OPENAI, ProviderName.NVIDIA_NIM],
            ),
            
            # Asset selection
            f"{TaskType.ASSET_SELECTION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.ASSET_SELECTION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="google/gemini-pro-1.5",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.OPENROUTER],
            ),
            
            # Composition
            f"{TaskType.COMPOSITION}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.COMPOSITION,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="google/gemini-pro-1.5",
                fallback_profile="anthropic/claude-3.5-sonnet",
                allowed_providers=[ProviderName.OPENROUTER],
            ),
            
            # STT - Sarvam for Telugu support
            f"{TaskType.STT}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.STT,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="saarika:v2",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
            f"{TaskType.STT}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.STT,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="saarika:v2",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
            f"{TaskType.STT}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.STT,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="saarika:v2",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
            
            # TTS - Sarvam for Telugu support
            f"{TaskType.TTS}_{SensitivityLevel.PUBLIC}": RoutingPolicy(
                task_type=TaskType.TTS,
                sensitivity=SensitivityLevel.PUBLIC,
                preferred_profile="bulbul:v1",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
            f"{TaskType.TTS}_{SensitivityLevel.INTERNAL}": RoutingPolicy(
                task_type=TaskType.TTS,
                sensitivity=SensitivityLevel.INTERNAL,
                preferred_profile="bulbul:v1",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
            f"{TaskType.TTS}_{SensitivityLevel.TENANT_SENSITIVE}": RoutingPolicy(
                task_type=TaskType.TTS,
                sensitivity=SensitivityLevel.TENANT_SENSITIVE,
                preferred_profile="bulbul:v1",
                fallback_profile=None,
                allowed_providers=[ProviderName.SARVAM],
            ),
        }
    
    def get_policy(self, task_type: TaskType, sensitivity: SensitivityLevel) -> RoutingPolicy:
        """Get routing policy for task and sensitivity."""
        key = f"{task_type}_{sensitivity}"
        return self.policies.get(key, RoutingPolicy(
            task_type=task_type,
            sensitivity=sensitivity,
            preferred_profile="llama-3.1-8b-instant",
            fallback_profile="gpt-4o-mini",
            allowed_providers=[ProviderName.GROQ, ProviderName.OPENAI],
        ))
    
    def route(self, task_type: TaskType, sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> RoutingDecision:
        """Route request to best provider with circuit breaker protection."""
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
            
            # Check circuit breaker
            from app.routing.circuit_breaker import can_execute_provider
            if not can_execute_provider(provider_name):
                logger.warning("circuit_breaker_open", provider=provider_name)
                continue
            
            # Check if provider has the model
            model_profile = provider.models.get(policy.preferred_profile)
            if model_profile:
                # Check health
                if self.status[provider_name].healthy:
                    fallback = None
                    if policy.fallback_profile:
                        for fb_provider in policy.allowed_providers:
                            if fb_provider != provider_name:
                                fb_config = self.providers.get(fb_provider)
                                if fb_config and fb_config.enabled and fb_config.models.get(policy.fallback_profile):
                                    fallback = fb_provider
                                    break
                    
                    return RoutingDecision(
                        provider=provider_name,
                        model=policy.preferred_profile,
                        model_profile=model_profile,
                        reason=f"Preferred model for {task_type} at {sensitivity} sensitivity",
                        fallback=fallback
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
                
                # Check circuit breaker
                from app.routing.circuit_breaker import can_execute_provider
                if not can_execute_provider(provider_name):
                    continue
                
                model_profile = provider.models.get(policy.fallback_profile)
                if model_profile and self.status[provider_name].healthy:
                    return RoutingDecision(
                        provider=provider_name,
                        model=policy.fallback_profile,
                        model_profile=model_profile,
                        reason=f"Fallback model for {task_type} at {sensitivity} sensitivity",
                        fallback=None
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
            
            from app.routing.circuit_breaker import can_execute_provider
            if not can_execute_provider(provider_name):
                continue
            
            for model_id, model_profile in provider.models.items():
                if task_type in model_profile.task_types and self.status[provider_name].healthy:
                    return RoutingDecision(
                        provider=provider_name,
                        model=model_id,
                        model_profile=model_profile,
                        reason=f"Last resort model for {task_type}",
                        fallback=None
                    )
        
        raise ValueError(f"No available provider for {task_type} at {sensitivity} sensitivity")
    
    def record_provider_result(self, provider: str, success: bool, latency_ms: float = 0):
        """Record provider request result for circuit breaker."""
        from app.routing.circuit_breaker import record_provider_success, record_provider_failure
        if success:
            record_provider_success(provider)
        else:
            record_provider_failure(provider)
        
        # Update provider status
        if provider in self.status:
            self.status[provider].healthy = success
            self.status[provider].latency_ms = latency_ms
            if not success:
                self.status[provider].error_count += 1
            from datetime import datetime
            self.status[provider].last_check = datetime.utcnow().isoformat()
    
    def get_circuit_breaker_status(self) -> Dict[str, Dict]:
        """Get circuit breaker status for all providers."""
        from app.routing.circuit_breaker import get_all_circuit_breaker_status
        return get_all_circuit_breaker_status()
    
    def update_provider_config(self, provider: ProviderConfig):
        """Update provider configuration."""
        self.providers[provider.name] = provider
    
    def update_provider_status(self, name: ProviderName, healthy: bool, latency_ms: float = 0, error_count: int = 0):
        """Update provider health status."""
        self.status[name].healthy = healthy
        self.status[name].latency_ms = latency_ms
        self.status[name].error_count = error_count
        from datetime import datetime
        self.status[name].last_check = datetime.utcnow().isoformat()
    
    def get_provider_status(self) -> Dict[ProviderName, ProviderStatus]:
        return self.status
    
    def get_circuit_breaker_status(self) -> Dict[str, dict]:
        from app.routing.circuit_breaker import get_all_circuit_breaker_status
        return get_all_circuit_breaker_status()


# Global routing engine
routing_engine = RoutingEngine()


def route_request(task_type: TaskType, sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> RoutingDecision:
    """Convenience function for routing."""
    return routing_engine.route(task_type, sensitivity)


def get_routing_policy(task_type: TaskType, sensitivity: SensitivityLevel) -> RoutingPolicy:
    """Get routing policy."""
    return routing_engine.get_policy(task_type, sensitivity)
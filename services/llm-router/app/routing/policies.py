"""Default routing-policy table (extracted from RoutingEngine).

Row-driven builder: each row declares (task, sensitivities, preferred,
fallback, providers, ...) and expands to one RoutingPolicy per
sensitivity. Flag-dependent cloud preferences resolve in
``build_default_policies``; tenant/regulated rows are static paid paths.
"""

from dataclasses import dataclass, field

from app.schemas.providers import (
    ProviderName,
    RoutingPolicy,
    SensitivityLevel,
    TaskType,
)

_FREE = [ProviderName.GROQ, ProviderName.OPENROUTER, ProviderName.APINEX]
_FREE_PLUS_NVIDIA = [
    ProviderName.GROQ,
    ProviderName.OPENROUTER,
    ProviderName.NVIDIA_NIM,
    ProviderName.APINEX,
]
_PAID_PAIR = [ProviderName.OPENAI, ProviderName.NVIDIA_NIM]


@dataclass
class _Row:
    task: TaskType
    sensitivities: list[SensitivityLevel]
    pref: str
    fb: str | None = None
    providers: list[ProviderName] = field(default_factory=list)
    blocked: list[ProviderName] = field(default_factory=list)
    timeout: int | None = None


def build_default_policies(
    *, local_enabled: bool, apinex_active: bool
) -> dict[str, RoutingPolicy]:
    """Build the task x sensitivity policy map for the given feature flags."""
    local = [ProviderName.LOCAL] if local_enabled else []
    apinex = [ProviderName.APINEX] if apinex_active else []

    if local_enabled:
        intent_pref = spec_pref = clarify_pref = "phi-3-mini-3.8b-q4"
    elif apinex_active:
        intent_pref = spec_pref = clarify_pref = "free/glm-5.3-flash"
    else:
        intent_pref = "openai/gpt-oss-20b"
        spec_pref = "openai/gpt-oss-120b"
        clarify_pref = "openai/gpt-oss-20b"

    both = local_enabled and apinex_active
    intent_fb = clarify_fb = "free/glm-5.3-flash" if both else "openai/gpt-oss-20b"
    intent_providers = clarify_providers = (
        local
        + apinex
        + [ProviderName.GROQ, ProviderName.OPENROUTER, ProviderName.OPENAI]
    )
    spec_fb = "free/glm-5.3-flash" if both else "gpt-4o-mini"
    spec_providers = (
        local
        + apinex
        + [
            ProviderName.OPENAI,
            ProviderName.NVIDIA_NIM,
            ProviderName.GROQ,
            ProviderName.OPENROUTER,
        ]
    )
    val_pref = domain_pref = (
        "free/glm-5.3-flash" if apinex_active else "openai/gpt-oss-120b"
    )
    val_fb = domain_fb = (
        "openai/gpt-oss-120b" if apinex_active else "anthropic/claude-3.5-sonnet"
    )
    val_providers = domain_providers = apinex + [
        ProviderName.GROQ,
        ProviderName.OPENROUTER,
    ]
    copilot_pref = "free/glm-5.3-flash" if apinex_active else "openai/gpt-oss-20b"
    copilot_fb = "openai/gpt-oss-20b" if apinex_active else "gpt-4o-mini"
    copilot_providers = apinex + [ProviderName.GROQ, ProviderName.OPENAI]
    research_pref = asset_pref = comp_pref = (
        "free/glm-5.3-flash" if apinex_active else "google/gemini-pro-1.5"
    )
    research_fb = asset_fb = comp_fb = (
        "google/gemini-pro-1.5" if apinex_active else "anthropic/claude-3.5-sonnet"
    )
    research_providers = asset_providers = comp_providers = apinex + [
        ProviderName.OPENROUTER
    ]

    pub_int = [SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL]
    strict_tenant = [ProviderName.LOCAL, ProviderName.OPENAI, ProviderName.NVIDIA_NIM]
    openai_only = [ProviderName.OPENAI]

    rows = [
        _Row(
            TaskType.INTENT_EXTRACTION,
            pub_int,
            intent_pref,
            intent_fb,
            intent_providers,
            timeout=150,
        ),
        _Row(
            TaskType.INTENT_EXTRACTION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "phi-3-mini-3.8b-q4",
            "gpt-4o-mini",
            strict_tenant,
            _FREE,
            150,
        ),
        _Row(
            TaskType.INTENT_EXTRACTION,
            [SensitivityLevel.REGULATED],
            "phi-3-mini-3.8b-q4",
            "gpt-4o-mini",
            [ProviderName.LOCAL, ProviderName.OPENAI],
            _FREE,
            150,
        ),
        _Row(TaskType.SPEC_GENERATION, pub_int, spec_pref, spec_fb, spec_providers),
        _Row(
            TaskType.SPEC_GENERATION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "phi-3-mini-3.8b-q4",
            "gpt-4o-mini",
            strict_tenant,
            _FREE,
        ),
        _Row(
            TaskType.SPEC_GENERATION,
            [SensitivityLevel.REGULATED],
            "phi-3-mini-3.8b-q4",
            "gpt-4o-mini",
            [ProviderName.LOCAL, ProviderName.OPENAI],
            _FREE,
        ),
        _Row(TaskType.VALIDATION, pub_int, val_pref, val_fb, val_providers),
        _Row(
            TaskType.VALIDATION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o",
            "nvidia/nemotron-3-ultra",
            _PAID_PAIR,
            _FREE,
        ),
        _Row(
            TaskType.VALIDATION,
            [SensitivityLevel.REGULATED],
            "gpt-4o",
            None,
            openai_only,
            _FREE_PLUS_NVIDIA,
        ),
        _Row(
            TaskType.COPILOT_CHAT, pub_int, copilot_pref, copilot_fb, copilot_providers
        ),
        _Row(
            TaskType.COPILOT_CHAT,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o-mini",
            "nvidia/nemotron-3-ultra",
            _PAID_PAIR,
            _FREE,
        ),
        _Row(
            TaskType.COPILOT_CHAT,
            [SensitivityLevel.REGULATED],
            "gpt-4o-mini",
            None,
            openai_only,
            _FREE_PLUS_NVIDIA,
        ),
        _Row(
            TaskType.EMBEDDING,
            [
                SensitivityLevel.PUBLIC,
                SensitivityLevel.INTERNAL,
                SensitivityLevel.TENANT_SENSITIVE,
            ],
            "text-embedding-3-small",
            None,
            openai_only,
        ),
        _Row(
            TaskType.CLARIFICATION,
            pub_int,
            clarify_pref,
            clarify_fb,
            clarify_providers,
            timeout=180,
        ),
        _Row(
            TaskType.CLARIFICATION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "phi-3-mini-3.8b-q4",
            "gpt-4o-mini",
            strict_tenant,
            _FREE,
            180,
        ),
        _Row(
            TaskType.RESEARCH, pub_int, research_pref, research_fb, research_providers
        ),
        _Row(
            TaskType.RESEARCH,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o",
            None,
            openai_only,
            _FREE,
        ),
        _Row(
            TaskType.RESEARCH,
            [SensitivityLevel.REGULATED],
            "gpt-4o",
            None,
            openai_only,
            _FREE,
        ),
        _Row(TaskType.DOMAIN_EXPERT, pub_int, domain_pref, domain_fb, domain_providers),
        _Row(
            TaskType.DOMAIN_EXPERT,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o",
            "nvidia/nemotron-3-ultra",
            _PAID_PAIR,
            _FREE,
        ),
        _Row(
            TaskType.DOMAIN_EXPERT,
            [SensitivityLevel.REGULATED],
            "gpt-4o",
            None,
            openai_only,
            _FREE_PLUS_NVIDIA,
        ),
        _Row(TaskType.ASSET_SELECTION, pub_int, asset_pref, asset_fb, asset_providers),
        _Row(
            TaskType.ASSET_SELECTION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o-mini",
            None,
            openai_only,
            _FREE,
        ),
        _Row(
            TaskType.ASSET_SELECTION,
            [SensitivityLevel.REGULATED],
            "gpt-4o-mini",
            None,
            openai_only,
            _FREE,
        ),
        _Row(TaskType.COMPOSITION, pub_int, comp_pref, comp_fb, comp_providers),
        _Row(
            TaskType.COMPOSITION,
            [SensitivityLevel.TENANT_SENSITIVE],
            "gpt-4o-mini",
            None,
            openai_only,
            _FREE,
        ),
        _Row(
            TaskType.COMPOSITION,
            [SensitivityLevel.REGULATED],
            "gpt-4o-mini",
            None,
            openai_only,
            _FREE,
        ),
        _Row(
            TaskType.STT,
            [
                SensitivityLevel.PUBLIC,
                SensitivityLevel.INTERNAL,
                SensitivityLevel.TENANT_SENSITIVE,
            ],
            "saarika:v2",
            None,
            [ProviderName.SARVAM],
        ),
        _Row(
            TaskType.TTS,
            [
                SensitivityLevel.PUBLIC,
                SensitivityLevel.INTERNAL,
                SensitivityLevel.TENANT_SENSITIVE,
            ],
            "bulbul:v1",
            None,
            [ProviderName.SARVAM],
        ),
    ]

    policies: dict[str, RoutingPolicy] = {}
    for row in rows:
        for sens in row.sensitivities:
            kwargs: dict = {
                "task_type": row.task,
                "sensitivity": sens,
                "preferred_profile": row.pref,
                "fallback_profile": row.fb,
                "allowed_providers": list(row.providers),
                "blocked_providers": list(row.blocked),
            }
            if row.timeout is not None:
                kwargs["timeout_seconds"] = row.timeout
            policies[f"{row.task}_{sens}"] = RoutingPolicy(**kwargs)
    return policies

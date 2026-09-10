"""Provider Configuration Models"""
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class ProviderName(str, Enum):
    GROQ = "groq"
    OPENROUTER = "openrouter"
    NVIDIA_NIM = "nvidia_nim"
    OPENAI = "openai"
    SARVAM = "sarvam"
    LOCAL = "local"


class ModelClass(str, Enum):
    FAST = "fast"
    STRONG = "strong"
    EMBEDDING = "embedding"
    STT = "stt"
    TTS = "tts"


class SensitivityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    TENANT_SENSITIVE = "tenant_sensitive"
    REGULATED = "regulated"


class TaskType(str, Enum):
    INTENT_EXTRACTION = "intent_extraction"
    SPEC_GENERATION = "spec_generation"
    VALIDATION = "validation"
    COPILOT_CHAT = "copilot_chat"
    EMBEDDING = "embedding"
    STT = "stt"
    TTS = "tts"
    CLARIFICATION = "clarification"
    RESEARCH = "research"
    DOMAIN_EXPERT = "domain_expert"
    ASSET_SELECTION = "asset_selection"
    COMPOSITION = "composition"


class ProviderConfig(BaseModel):
    name: ProviderName
    enabled: bool = True
    priority: int = 100  # Lower = higher priority
    api_key: str = ""
    base_url: str | None = None
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000
    supported_tasks: list[TaskType] = []
    supported_sensitivity: list[SensitivityLevel] = [
        SensitivityLevel.PUBLIC,
        SensitivityLevel.INTERNAL,
    ]
    models: dict[str, "ModelProfile"] = {}
    metadata: dict[str, Any] = {}


class ModelProfile(BaseModel):
    model_id: str
    provider: ProviderName
    task_types: list[TaskType]
    cost_class: Literal["free", "low", "medium", "high"] = "low"
    latency_class: Literal["fast", "medium", "slow"] = "medium"
    max_tokens: int = 4096
    context_window: int = 8192
    supports_json_mode: bool = False
    supports_streaming: bool = True
    metadata: dict[str, Any] = {}


class RoutingPolicy(BaseModel):
    task_type: TaskType
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    preferred_profile: str
    fallback_profile: str | None = None
    allowed_providers: list[ProviderName] = []
    blocked_providers: list[ProviderName] = []
    max_retries: int = 2
    timeout_seconds: int = 30
    cache_ttl_seconds: int = 3600


class ProviderStatus(BaseModel):
    name: ProviderName
    healthy: bool = True
    last_check: str | None = None
    error_count: int = 0
    latency_ms: float = 0.0
    rate_limit_remaining: int | None = None


# Default Provider Configurations
DEFAULT_PROVIDERS: dict[ProviderName, ProviderConfig] = {
    ProviderName.GROQ: ProviderConfig(
        name=ProviderName.GROQ,
        enabled=True,
        priority=10,
        base_url="https://api.groq.com/openai/v1",
        rate_limit_rpm=30,
        rate_limit_tpm=6000,
        supported_tasks=[
            TaskType.INTENT_EXTRACTION,
            TaskType.CLARIFICATION,
            TaskType.COPILOT_CHAT,
            TaskType.RESEARCH,
        ],
        supported_sensitivity=[SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL],
        models={
            "openai/gpt-oss-20b": ModelProfile(
                model_id="openai/gpt-oss-20b",
                provider=ProviderName.GROQ,
                task_types=[
                    TaskType.INTENT_EXTRACTION,
                    TaskType.CLARIFICATION,
                    TaskType.COPILOT_CHAT,
                ],
                cost_class="free",
                latency_class="fast",
                max_tokens=8192,
                context_window=131072,
                supports_json_mode=True,
            ),
            "openai/gpt-oss-120b": ModelProfile(
                model_id="openai/gpt-oss-120b",
                provider=ProviderName.GROQ,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION, TaskType.DOMAIN_EXPERT],
                cost_class="free",
                latency_class="medium",
                max_tokens=8192,
                context_window=131072,
                supports_json_mode=True,
            ),
            "qwen-qwq-32b": ModelProfile(
                model_id="qwen-qwq-32b",
                provider=ProviderName.GROQ,
                task_types=[
                    TaskType.INTENT_EXTRACTION,
                    TaskType.CLARIFICATION,
                    TaskType.COPILOT_CHAT,
                    TaskType.RESEARCH,
                ],
                cost_class="free",
                latency_class="medium",
                max_tokens=8192,
                context_window=131072,
                supports_json_mode=True,
            ),
        },
    ),
    ProviderName.OPENROUTER: ProviderConfig(
        name=ProviderName.OPENROUTER,
        enabled=True,
        priority=20,
        base_url="https://openrouter.ai/api/v1",
        rate_limit_rpm=60,
        rate_limit_tpm=20000,
        supported_tasks=[
            TaskType.SPEC_GENERATION,
            TaskType.VALIDATION,
            TaskType.DOMAIN_EXPERT,
            TaskType.RESEARCH,
            TaskType.ASSET_SELECTION,
            TaskType.COMPOSITION,
        ],
        supported_sensitivity=[SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL],
        models={
            "anthropic/claude-3.5-sonnet": ModelProfile(
                model_id="anthropic/claude-3.5-sonnet",
                provider=ProviderName.OPENROUTER,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION, TaskType.DOMAIN_EXPERT],
                cost_class="medium",
                latency_class="medium",
                max_tokens=8192,
                context_window=200000,
                supports_json_mode=True,
            ),
            "google/gemini-pro-1.5": ModelProfile(
                model_id="google/gemini-pro-1.5",
                provider=ProviderName.OPENROUTER,
                task_types=[TaskType.RESEARCH, TaskType.ASSET_SELECTION, TaskType.COMPOSITION],
                cost_class="low",
                latency_class="medium",
                max_tokens=8192,
                context_window=1000000,
                supports_json_mode=True,
            ),
            "qwen/qwen-2.5-72b-instruct": ModelProfile(
                model_id="qwen/qwen-2.5-72b-instruct",
                provider=ProviderName.OPENROUTER,
                task_types=[
                    TaskType.INTENT_EXTRACTION,
                    TaskType.CLARIFICATION,
                    TaskType.RESEARCH,
                    TaskType.COPILOT_CHAT,
                ],
                cost_class="low",
                latency_class="medium",
                max_tokens=8192,
                context_window=32768,
                supports_json_mode=True,
            ),
        },
    ),
    ProviderName.NVIDIA_NIM: ProviderConfig(
        name=ProviderName.NVIDIA_NIM,
        enabled=True,
        priority=30,
        rate_limit_rpm=60,
        rate_limit_tpm=50000,
        supported_tasks=[
            TaskType.SPEC_GENERATION,
            TaskType.VALIDATION,
            TaskType.COPILOT_CHAT,
        ],
        supported_sensitivity=[
            SensitivityLevel.PUBLIC,
            SensitivityLevel.INTERNAL,
            SensitivityLevel.TENANT_SENSITIVE,
        ],
        models={
            "nvidia/nemotron-3-ultra": ModelProfile(
                model_id="nvidia/nemotron-3-ultra",
                provider=ProviderName.NVIDIA_NIM,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION, TaskType.COPILOT_CHAT],
                cost_class="low",
                latency_class="medium",
                max_tokens=4096,
                context_window=128000,
                supports_json_mode=True,
            ),
        },
    ),
    ProviderName.OPENAI: ProviderConfig(
        name=ProviderName.OPENAI,
        enabled=True,
        priority=40,
        base_url="https://api.openai.com/v1",
        rate_limit_rpm=60,
        rate_limit_tpm=100000,
        supported_tasks=[
            TaskType.SPEC_GENERATION,
            TaskType.VALIDATION,
            TaskType.COPILOT_CHAT,
            TaskType.EMBEDDING,
        ],
        supported_sensitivity=[
            SensitivityLevel.PUBLIC,
            SensitivityLevel.INTERNAL,
            SensitivityLevel.TENANT_SENSITIVE,
        ],
        models={
            "gpt-4o-mini": ModelProfile(
                model_id="gpt-4o-mini",
                provider=ProviderName.OPENAI,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION, TaskType.COPILOT_CHAT],
                cost_class="low",
                latency_class="fast",
                max_tokens=16384,
                context_window=128000,
                supports_json_mode=True,
            ),
            "gpt-4o": ModelProfile(
                model_id="gpt-4o",
                provider=ProviderName.OPENAI,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION, TaskType.DOMAIN_EXPERT],
                cost_class="high",
                latency_class="medium",
                max_tokens=16384,
                context_window=128000,
                supports_json_mode=True,
            ),
            "text-embedding-3-small": ModelProfile(
                model_id="text-embedding-3-small",
                provider=ProviderName.OPENAI,
                task_types=[TaskType.EMBEDDING],
                cost_class="low",
                latency_class="fast",
                max_tokens=8191,
                context_window=8191,
            ),
        },
    ),
    ProviderName.LOCAL: ProviderConfig(
        name=ProviderName.LOCAL,
        enabled=True,
        priority=5,
        base_url="http://ollama:11434/v1",
        rate_limit_rpm=10,
        rate_limit_tpm=8000,
        supported_tasks=[
            TaskType.SPEC_GENERATION,
            TaskType.VALIDATION,
        ],
        # Local inference never leaves the box, so it is safe for all
        # sensitivity levels including tenant-sensitive and regulated.
        supported_sensitivity=[
            SensitivityLevel.PUBLIC,
            SensitivityLevel.INTERNAL,
            SensitivityLevel.TENANT_SENSITIVE,
            SensitivityLevel.REGULATED,
        ],
        models={
            "phi-3-mini-3.8b-q4": ModelProfile(
                model_id="phi-3-mini-3.8b-q4",
                provider=ProviderName.LOCAL,
                task_types=[TaskType.SPEC_GENERATION, TaskType.VALIDATION],
                cost_class="free",
                latency_class="slow",
                max_tokens=2048,
                context_window=4096,
                supports_json_mode=True,
                metadata={
                    "quant": "q4_k_m",
                    "vram_mb": 2300,
                    "cpu_only": True,
                    # Name of the model inside Ollama (ollama pull <name>).
                    "ollama_model": "phi3:mini",
                },
            ),
        },
    ),
    ProviderName.SARVAM: ProviderConfig(
        name=ProviderName.SARVAM,
        enabled=True,
        priority=50,
        base_url="https://api.sarvam.ai",
        rate_limit_rpm=30,
        rate_limit_tpm=10000,
        supported_tasks=[TaskType.STT, TaskType.TTS],
        supported_sensitivity=[
            SensitivityLevel.PUBLIC,
            SensitivityLevel.INTERNAL,
            SensitivityLevel.TENANT_SENSITIVE,
        ],
        models={
            "saarika:v2": ModelProfile(
                model_id="saarika:v2",
                provider=ProviderName.SARVAM,
                task_types=[TaskType.STT],
                cost_class="low",
                latency_class="fast",
                max_tokens=0,
                context_window=0,
                metadata={
                    "languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or"]
                },
            ),
            "bulbul:v1": ModelProfile(
                model_id="bulbul:v1",
                provider=ProviderName.SARVAM,
                task_types=[TaskType.TTS],
                cost_class="low",
                latency_class="fast",
                max_tokens=0,
                context_window=0,
                metadata={
                    "languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or"],
                    "speakers": ["anushka", "manisha", "vidya", "arjun", "rahul"],
                },
            ),
        },
    ),
}

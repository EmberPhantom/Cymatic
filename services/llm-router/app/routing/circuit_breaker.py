"""Circuit Breaker Implementation for LLM Provider Fault Tolerance"""
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pydantic import BaseModel, PrivateAttr
from threading import Lock
import structlog

from app.schemas.providers import ProviderName

logger = structlog.get_logger()


class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker(BaseModel):
    """Circuit breaker for provider fault tolerance."""
    provider: ProviderName
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    
    # Configuration
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0  # seconds before trying half-open
    
    # Thread safety
    _lock: Lock = PrivateAttr(default_factory=Lock)
    
    def record_success(self):
        """Record successful request."""
        with self._lock:
            self.failure_count = 0
            self.success_count += 1
            self.last_success_time = datetime.now(timezone.utc)
            
            if self.state == CircuitState.HALF_OPEN and self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("circuit_breaker_closed", provider=self.provider)
    
    def record_failure(self):
        """Record failed request."""
        with self._lock:
            self.failure_count += 1
            self.success_count = 0
            self.last_failure_time = datetime.now(timezone.utc)
            
            if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning("circuit_breaker_opened", provider=self.provider, failures=self.failure_count)
            
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                logger.warning("circuit_breaker_reopened", provider=self.provider)
    
    def can_execute(self) -> bool:
        """Check if request can be executed."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed >= self.timeout:
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                        logger.info("circuit_breaker_half_open", provider=self.provider)
                        return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                return True
            
            return False
    
    def get_state(self) -> CircuitState:
        with self._lock:
            return self.state


# Global circuit breaker instances
_circuit_breakers: Dict[ProviderName, CircuitBreaker] = {}
_lock = Lock()


def get_circuit_breaker(provider: str) -> CircuitBreaker:
    """Get or create circuit breaker for provider."""
    global _circuit_breakers
    with _lock:
        if provider not in _circuit_breakers:
            _circuit_breakers[provider] = CircuitBreaker(provider=provider)
        return _circuit_breakers[provider]


def record_provider_success(provider: str):
    """Record successful request for provider."""
    cb = get_circuit_breaker(provider)
    cb.record_success()


def record_provider_failure(provider: str):
    """Record failed request for provider."""
    cb = get_circuit_breaker(provider)
    cb.record_failure()


def can_execute_provider(provider: str) -> bool:
    """Check if provider can execute request."""
    cb = get_circuit_breaker(provider)
    return cb.can_execute()


def get_circuit_breaker_status(provider: str) -> dict:
    """Get circuit breaker status for provider."""
    cb = get_circuit_breaker(provider)
    return {
        "state": cb.state.value,
        "failure_count": cb.failure_count,
        "success_count": cb.success_count,
        "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None,
    }


def get_all_circuit_breaker_status() -> Dict[str, dict]:
    """Get status of all circuit breakers."""
    return {provider: get_circuit_breaker_status(provider) for provider in ["groq", "openrouter", "nvidia_nim", "openai", "sarvam"]}
"""Simulation Specification Validator - re-exported from shared package.

Single source: cymatic_shared.services.spec_validator (union of the
strictest rules formerly split across service forks).
"""

from cymatic_shared.services.spec_validator import (  # noqa: F401
    SpecValidator,
    SpecValidationResult,
    ValidationErrorDetail,
    validate_spec,
    spec_validator,
)

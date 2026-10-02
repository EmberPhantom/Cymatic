"""Stable ID formats for jobs and generation runs. Single source."""
import uuid


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex}"


def new_job_id(*parts: object) -> str:
    """Join parts with underscores: new_job_id("validate", 3, 1987)."""
    return "_".join(str(p) for p in parts)

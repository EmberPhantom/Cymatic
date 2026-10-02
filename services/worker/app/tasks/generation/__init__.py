"""Generation task handlers (split package; imports preserved)."""
from app.db.session import AsyncSessionLocal  # noqa: F401 (patch target)
from .spec_tasks import generate_spec_task, validate_spec_task  # noqa: F401
from .scene_tasks import generate_scene_task, publish_scene_task  # noqa: F401
from .ops_tasks import process_asset_task, analytics_aggregation_task  # noqa: F401

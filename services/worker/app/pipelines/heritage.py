"""Heritage Generation Pipeline - Orchestrates agents for heritage spec generation"""
from typing import Any

from pydantic import BaseModel

from cymatic_shared.schemas.simulation_spec import SimulationSpec
from app.agents.architect_agent import ArchitectResult, create_simulation_spec
from app.agents.asset_agent import AssetAgentResult, select_assets
from app.agents.clarification_agent import ClarificationResult, process_clarification_answers
from app.agents.composer_agent import ComposerResult, compose_scene
from app.agents.domain_expert_agent import DomainCheckResult, check_domain_compliance
from app.agents.intake_agent import IntakeResult, process_intake
from app.agents.research_agent import ResearchResult, research_generation
from app.agents.scene_package import ScenePackage
from app.agents.validation_agent import ValidationAgentResult, validate_simulation_spec
from app.core.queue import Job, JobStatus
from app.pipelines.checkpoint import PipelineCheckpoint, PipelineCheckpointManager
from app.pipelines.heritage_templates import HeritageTemplateLibrary, create_heritage_spec_from_template
import structlog

logger = structlog.get_logger()


class PipelineInput(BaseModel):
    project_id: int
    prompt: str
    context: dict[str, Any] = {}
    # Any: clarify convert_value legitimately yields bool/int (furnished,
    # bedrooms); consumers use truthiness/.get, so accept them here instead
    # of failing validation (was dict[str, str], rejected furnished=False).
    clarification_answers: dict[str, Any] = {}
    # Authoritative project domain from the generate_spec task (see real_estate).
    expected_domain: str | None = None


class PipelineResult(BaseModel):
    spec: SimulationSpec | None = None
    scene_package: ScenePackage | None = None
    intake: IntakeResult | None = None
    clarification: ClarificationResult | None = None
    research: ResearchResult | None = None
    domain_check: DomainCheckResult | None = None
    architect: ArchitectResult | None = None
    composer: ComposerResult | None = None
    assets: AssetAgentResult | None = None
    validation: ValidationAgentResult | None = None
    status: str = "pending"
    error: str | None = None


class HeritagePipeline:
    """Orchestrates the complete heritage specification generation pipeline."""

    # Heritage-specific templates
    HERITAGE_TEMPLATES = {
        "temple": {
            "default_pois": ["gopuram_entrance", "mandapa", "garbhagriha", "pradakshina_path", "temple_tank"],
            "layout": "axial",
            "narration_style": "spiritual",
        },
        "palace": {
            "default_pois": ["main_gate", "diwan_i_am", "diwan_i_khas", "zenana", "royal_gardens", "armory"],
            "layout": "courtyard_sequence",
            "narration_style": "historical",
        },
        "courtyard": {
            "default_pois": ["entrance_gate", "central_fountain", "baradari", "side_pavilions", "service_areas"],
            "layout": "enclosed_courtyard",
            "narration_style": "cultural",
        },
        "monument": {
            "default_pois": ["base_platform", "main_structure", "inscriptions", "surrounding_gardens"],
            "layout": "radial",
            "narration_style": "commemorative",
        }
    }

    # Pipeline stages in order (parity with real_estate for checkpoint resume) - HIGH: 72 no checkpoint manager
    STAGES = [
        "intake",
        "clarification",
        "research",
        "architect",
        "composer",
        "domain_expert",
        "asset_selection",
        "validation",
    ]

    def __init__(self):
        self.checkpoint_manager = PipelineCheckpointManager()

    def _load_stage_outputs(self, stage_outputs: dict[str, Any], result: 'PipelineResult'):
        """Load stage outputs into result object (parity with RealEstatePipeline)."""
        if "intake" in stage_outputs:
            try:
                result.intake = IntakeResult(**stage_outputs["intake"])
            except Exception:
                pass
        if "clarification" in stage_outputs:
            try:
                result.clarification = ClarificationResult(**stage_outputs["clarification"])
            except Exception:
                pass
        if "research" in stage_outputs:
            try:
                result.research = ResearchResult(**stage_outputs["research"])
            except Exception:
                pass
        if "architect" in stage_outputs:
            from cymatic_shared.schemas.simulation_spec import SimulationSpec
            arch_data = stage_outputs["architect"]
            try:
                if isinstance(arch_data, dict) and "spec" in arch_data and isinstance(arch_data["spec"], dict):
                    result.architect = ArchitectResult(spec=SimulationSpec(**arch_data["spec"]), generation_notes=arch_data.get("generation_notes", []))
                else:
                    result.architect = ArchitectResult(spec=SimulationSpec(**arch_data))
            except Exception:
                pass
        if "composer" in stage_outputs:
            try:
                result.composer = ComposerResult(**stage_outputs["composer"])
            except Exception:
                pass
        if "domain_expert" in stage_outputs:
            try:
                result.domain_check = DomainCheckResult(**stage_outputs["domain_expert"])
            except Exception:
                pass
        if "asset_selection" in stage_outputs:
            try:
                result.assets = AssetAgentResult(**stage_outputs["asset_selection"])
            except Exception:
                pass
        if "validation" in stage_outputs:
            try:
                result.validation = ValidationAgentResult(**stage_outputs["validation"])
            except Exception:
                pass
        if "scene_package" in stage_outputs:
            try:
                result.scene_package = ScenePackage(**stage_outputs["scene_package"])
            except Exception:
                pass

    async def _run_stage(  # noqa: PLR0912
        self,
        stage: str,
        stage_index: int,
        input_data: PipelineInput,
        stage_outputs: dict[str, Any],
        job: Job | None = None,
    ) -> 'PipelineResult':
        """Execute a single pipeline stage (checkpoint-aware)."""
        result = PipelineResult()
        self._load_stage_outputs(stage_outputs or {}, result)

        if job:
            job.status = JobStatus.RUNNING

        try:
            if stage == "intake":
                logger.info("pipeline_stage_start", stage="intake", project_id=input_data.project_id)
                result.intake = await process_intake(input_data.prompt, input_data.context)

            elif stage == "clarification":
                if not input_data.clarification_answers:
                    result.clarification = ClarificationResult(questions=[], updated_fields={}, ready_for_generation=True, completion_percentage=1.0)
                else:
                    if result.intake is None:
                        raise ValueError("Intake result missing for clarification stage")
                    logger.info("pipeline_stage_start", stage="clarification", project_id=input_data.project_id)
                    clarify_domain = input_data.expected_domain or result.intake.detected_domain
                    result.clarification = await process_clarification_answers(
                        clarify_domain, result.intake.extracted_entities, input_data.clarification_answers,
                    )
                    if not result.clarification.ready_for_generation:
                        return PipelineResult(status="awaiting_clarification", error="Awaiting clarification")

            elif stage == "research":
                if result.intake is None:
                    raise ValueError("Intake result missing for research stage")
                logger.info("pipeline_stage_start", stage="research", project_id=input_data.project_id)
                site_type = result.intake.extracted_entities.get("site_type", "courtyard")
                research_reqs = {"target_fps": 60, "max_triangles": 100000, "texture_budget_mb": 100}
                result.research = research_generation(input_data.expected_domain or result.intake.detected_domain, site_type, research_reqs)

            elif stage == "architect":
                if result.intake is None:
                    raise ValueError("Intake result missing for architect stage")
                logger.info("pipeline_stage_start", stage="architect", project_id=input_data.project_id)
                clarification_data = result.clarification.updated_fields if result.clarification else {}
                architect_domain = input_data.expected_domain or result.intake.detected_domain
                if result.intake.detected_domain != architect_domain:
                    logger.warning(
                        "pipeline_domain_mismatch",
                        project_id=input_data.project_id,
                        expected=architect_domain,
                        detected=result.intake.detected_domain,
                    )
                template = self.HERITAGE_TEMPLATES.get(result.intake.extracted_entities.get("site_type", "courtyard"), self.HERITAGE_TEMPLATES["courtyard"])
                site_type = result.intake.extracted_entities.get("site_type", "courtyard")
                template_id = (input_data.context or {}).get("template_id") or clarification_data.get("template_id")
                # Track whether full library was used to avoid double layout later
                used_template_library = bool(template_id and template_id in HeritageTemplateLibrary.TEMPLATES)
                if used_template_library:
                    spec = create_heritage_spec_from_template(template_id, f"Project {input_data.project_id}", {**clarification_data, "site_type": site_type})
                    result.architect = ArchitectResult(spec=spec, generation_notes=[f"heritage template {template_id}"])
                    # Persist flag via context for composer stage skip check
                    if result.architect.spec is not None:
                        result.architect.spec.metadata.tags.append("_template_layout")
                else:
                    result.architect = await create_simulation_spec(
                        domain=architect_domain,
                        objective=input_data.prompt,
                        intake_data={**result.intake.extracted_entities, "site_type": site_type, "template": template},
                        clarification_data=clarification_data,
                        context=input_data.context,
                    )

            elif stage == "composer":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for composer stage")
                if result.intake is None:
                    raise ValueError("Intake result missing for composer stage")
                # HIGH: 120 composer double layout - skip if architect already produced layout via template library
                is_template_layout = result.architect.spec is not None and "_template_layout" in (result.architect.spec.metadata.tags or [])
                if is_template_layout:
                    logger.info("composer_skipped_template_layout", project_id=input_data.project_id)
                    # Keep existing layout; do not recompose
                    result.composer = None
                else:
                    logger.info("pipeline_stage_start", stage="composer", project_id=input_data.project_id)
                    clarification_data = result.clarification.updated_fields if result.clarification else {}
                    result.composer = compose_scene(
                        entities=result.architect.spec.entities,
                        domain=input_data.expected_domain or result.intake.detected_domain,
                        user_preferences=clarification_data,
                    )
                    result.architect.spec.entities = result.composer.entities
                    result.architect.spec.navigation = result.composer.navigation
                    result.architect.spec.lighting = result.composer.lighting

            elif stage == "domain_expert":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for domain_expert stage")
                logger.info("pipeline_stage_start", stage="domain_expert", project_id=input_data.project_id)
                result.domain_check = check_domain_compliance(result.architect.spec)
                if not result.domain_check.valid:
                    return PipelineResult(status="domain_validation_failed", error="Heritage domain compliance check failed")

            elif stage == "asset_selection":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for asset_selection stage")
                if result.intake is None:
                    raise ValueError("Intake result missing for asset_selection stage")
                logger.info("pipeline_stage_start", stage="asset_selection", project_id=input_data.project_id)
                result.assets = select_assets(
                    spec_entities=result.architect.spec.entities,
                    domain=input_data.expected_domain or result.intake.detected_domain,
                    performance_budget=result.architect.spec.performance_budget.model_dump(),
                )

            elif stage == "validation":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for validation stage")
                logger.info("pipeline_stage_start", stage="validation", project_id=input_data.project_id)
                result.validation = validate_simulation_spec(result.architect.spec.model_dump())
                if not result.validation.valid:
                    return PipelineResult(status="validation_failed", error="Final validation failed")

            return PipelineResult(
                spec=result.architect.spec if result.architect else None,
                scene_package=None,
                intake=result.intake,
                clarification=result.clarification,
                research=result.research,
                domain_check=result.domain_check,
                architect=result.architect,
                composer=result.composer,
                assets=result.assets,
                validation=result.validation,
                status="completed",
            )

        except Exception as e:  # noqa: BLE001 - broad for stability (heritage parity)
            logger.error("pipeline_stage_failed", stage=stage, project_id=input_data.project_id, error=str(e))
            raise

    async def run(self, input_data: PipelineInput, job: Job | None = None) -> PipelineResult:
        """Execute the full heritage pipeline with checkpointing (parity with RealEstatePipeline)."""
        result = PipelineResult()

        # Try to load existing checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint(input_data.project_id)
        start_stage_index = 0

        if checkpoint:
            logger.info("checkpoint_loaded", project_id=input_data.project_id, stage=checkpoint.stage)
            try:
                ckpt_input = PipelineInput(**checkpoint.input_data)
                if input_data.prompt and input_data.prompt != ckpt_input.prompt:
                    ckpt_input.prompt = input_data.prompt
                if input_data.context:
                    ckpt_input.context = {**ckpt_input.context, **input_data.context}
                if input_data.clarification_answers:
                    ckpt_input.clarification_answers = {**ckpt_input.clarification_answers, **input_data.clarification_answers}
                input_data = ckpt_input
            except Exception:  # noqa: BLE001
                logger.warning("checkpoint_input_reconcile_failed", project_id=input_data.project_id)
            stage_outputs = dict(checkpoint.stage_outputs)
            start_stage_index = checkpoint.stage_index + 1
            self._load_stage_outputs(checkpoint.stage_outputs, result)
        else:
            stage_outputs = {}

        try:
            for stage_index in range(start_stage_index, len(self.STAGES)):
                stage = self.STAGES[stage_index]
                stage_result = await self._run_stage(stage, stage_index, input_data, stage_outputs, job)

                # Merge
                if stage_result.intake:
                    result.intake = stage_result.intake
                if stage_result.clarification:
                    result.clarification = stage_result.clarification
                if stage_result.research:
                    result.research = stage_result.research
                if stage_result.architect:
                    result.architect = stage_result.architect
                if stage_result.composer:
                    result.composer = stage_result.composer
                if stage_result.domain_check:
                    result.domain_check = stage_result.domain_check
                if stage_result.assets:
                    result.assets = stage_result.assets
                if stage_result.validation:
                    result.validation = stage_result.validation
                if stage_result.scene_package:
                    result.scene_package = stage_result.scene_package

                if stage_result.status in ("awaiting_clarification", "domain_validation_failed", "validation_failed", "failed"):
                    return stage_result

                # Checkpoint save - preserve prior outputs
                if stage_result.intake is not None:
                    stage_outputs["intake"] = stage_result.intake.model_dump()
                if stage_result.clarification is not None:
                    stage_outputs["clarification"] = stage_result.clarification.model_dump()
                if stage_result.research is not None:
                    stage_outputs["research"] = stage_result.research.model_dump()
                if stage_result.architect is not None:
                    try:
                        stage_outputs["architect"] = stage_result.architect.model_dump()
                    except Exception:
                        stage_outputs["architect"] = stage_result.architect.spec.model_dump()
                if stage_result.composer is not None:
                    stage_outputs["composer"] = stage_result.composer.model_dump()
                if stage_result.domain_check is not None:
                    stage_outputs["domain_expert"] = stage_result.domain_check.model_dump()
                if stage_result.assets is not None:
                    stage_outputs["asset_selection"] = stage_result.assets.model_dump()
                if stage_result.validation is not None:
                    stage_outputs["validation"] = stage_result.validation.model_dump()
                if stage_result.scene_package is not None:
                    stage_outputs["scene_package"] = stage_result.scene_package.model_dump()
                if stage not in stage_outputs:
                    stage_outputs[stage] = stage_outputs.get(stage, {})

                self.checkpoint_manager.save_checkpoint(
                    PipelineCheckpoint(
                        project_id=input_data.project_id,
                        stage=stage,
                        stage_index=stage_index,
                        input_data=input_data.model_dump(),
                        stage_outputs=dict(stage_outputs),
                    )
                )

            result.spec = result.architect.spec if result.architect else None
            result.status = "completed"
            logger.info("pipeline_completed", project_id=input_data.project_id, status=result.status)
            if result.status == "completed":
                self.checkpoint_manager.clear_checkpoint(input_data.project_id)

        except Exception as e:  # noqa: BLE001 - HIGH: 185 narrow except -> Exception
            logger.error("pipeline_failed", project_id=input_data.project_id, error=str(e))
            result.status = "failed"
            result.error = str(e)

        return result
    
    def get_template(self, site_type: str) -> dict[str, Any]:
        """Get heritage template for site type."""
        return self.HERITAGE_TEMPLATES.get(site_type, self.HERITAGE_TEMPLATES["courtyard"])

    def list_templates(self) -> list[str]:
        """List available heritage templates."""
        return list(self.HERITAGE_TEMPLATES.keys())


# Global pipeline instance
heritage_pipeline = HeritagePipeline()


async def generate_heritage_spec(
    project_id: int,
    prompt: str,
    context: dict[str, Any] | None = None,
    clarification_answers: dict[str, Any] | None = None,
    expected_domain: str | None = None,
) -> PipelineResult:
    """Convenience function for heritage spec generation."""
    input_data = PipelineInput(
        project_id=project_id,
        prompt=prompt,
        context=context or {},
        clarification_answers=clarification_answers or {},
        expected_domain=expected_domain or "heritage",
    )
    return await heritage_pipeline.run(input_data)

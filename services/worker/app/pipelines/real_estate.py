"""Real Estate Generation Pipeline - Orchestrates all agents for spec generation with checkpointing"""
from typing import Any

from pydantic import BaseModel

from cymatic_shared.schemas.simulation_spec import SimulationSpec
from app.agents.asset_agent import AssetAgentResult, select_assets
from app.agents.architect_agent import ArchitectResult, create_simulation_spec
from app.agents.clarification_agent import ClarificationResult, process_clarification_answers
from app.agents.composer_agent import ComposerResult, compose_scene
from app.agents.domain_expert_agent import DomainCheckResult, check_domain_compliance
from app.agents.intake_agent import IntakeResult, process_intake
from app.agents.research_agent import ResearchResult, research_generation
from app.agents.scene_package import ScenePackage
from app.agents.validation_agent import ValidationAgentResult, validate_simulation_spec
from app.core.queue import Job, JobStatus
from app.pipelines.checkpoint import PipelineCheckpoint, PipelineCheckpointManager
import structlog

logger = structlog.get_logger()


class PipelineInput(BaseModel):
    project_id: int
    prompt: str
    context: dict[str, Any] = {}
    clarification_answers: dict[str, str] = {}
    # Authoritative project domain from the generate_spec task. Intake still
    # detects its own domain for telemetry, but architect uses this when set
    # so API (project.domain) and worker (detected) can't fork question sets.
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


class RealEstatePipeline:
    """Orchestrates the complete real estate specification generation pipeline with checkpointing."""
    
    # Pipeline stages in order
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
        """Load stage outputs into result object."""
        if "intake" in stage_outputs:
            from app.agents.intake_agent import IntakeResult
            try:
                result.intake = IntakeResult(**stage_outputs["intake"])
            except Exception:
                pass
        if "clarification" in stage_outputs:
            from app.agents.clarification_agent import ClarificationResult
            try:
                result.clarification = ClarificationResult(**stage_outputs["clarification"])
            except Exception:
                pass
        if "research" in stage_outputs:
            from app.agents.research_agent import ResearchResult
            try:
                result.research = ResearchResult(**stage_outputs["research"])
            except Exception:
                pass
        if "architect" in stage_outputs:
            from cymatic_shared.schemas.simulation_spec import SimulationSpec
            arch_data = stage_outputs["architect"]
            try:
                # Support both shapes: {"spec": {...}, "generation_notes": [...]} and direct spec dict
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
        """Execute a single pipeline stage."""
        from app.agents.clarification_agent import process_clarification_answers
        from app.agents.intake_agent import process_intake

        result = PipelineResult()
        # Hydrate outputs from prior stages (or a restored checkpoint) so
        # downstream stages can reference intake/architect/etc.
        self._load_stage_outputs(stage_outputs or {}, result)

        if job:
            job.status = JobStatus.RUNNING

        try:
            if stage == "intake":
                logger.info("pipeline_stage_start", stage="intake", project_id=input_data.project_id)
                result.intake = await process_intake(input_data.prompt, input_data.context)

            elif stage == "clarification":
                if not input_data.clarification_answers:
                    # No clarification answers provided, skip to next stage
                    result.clarification = ClarificationResult(
                        questions=[],
                        updated_fields={},
                        ready_for_generation=True,
                        completion_percentage=1.0,
                    )
                else:
                    if result.intake is None:
                        raise ValueError("Intake result missing for clarification stage")
                    logger.info("pipeline_stage_start", stage="clarification", project_id=input_data.project_id)
                    result.clarification = await process_clarification_answers(
                        input_data.expected_domain or result.intake.detected_domain,
                        result.intake.extracted_entities,
                        input_data.clarification_answers,
                    )

                    if not result.clarification.ready_for_generation:
                        return PipelineResult(
                            status="awaiting_clarification",
                            error="Awaiting clarification",
                        )

            elif stage == "research":
                if result.intake is None:
                    raise ValueError("Intake result missing for research stage")
                logger.info("pipeline_stage_start", stage="research", project_id=input_data.project_id)
                style = result.intake.extracted_entities.get("style", "modern")
                research_reqs = {
                    "target_fps": 60,
                    "max_triangles": 100000,
                    "texture_budget_mb": 100,
                }
                result.research = research_generation(
                    input_data.expected_domain or result.intake.detected_domain,
                    style,
                    research_reqs,
                )

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
                result.architect = await create_simulation_spec(
                    domain=architect_domain,
                    objective=input_data.prompt,
                    intake_data=result.intake.extracted_entities,
                    clarification_data=clarification_data,
                    context=input_data.context,
                )

            elif stage == "composer":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for composer stage")
                if result.intake is None:
                    raise ValueError("Intake result missing for composer stage")
                logger.info("pipeline_stage_start", stage="composer", project_id=input_data.project_id)
                clarification_data = result.clarification.updated_fields if result.clarification else {}
                result.composer = compose_scene(
                    entities=result.architect.spec.entities,
                    domain=input_data.expected_domain or result.intake.detected_domain,
                    user_preferences=clarification_data,
                )

                # Update spec with composed layout
                result.architect.spec.entities = result.composer.entities
                result.architect.spec.navigation = result.composer.navigation
                result.architect.spec.lighting = result.composer.lighting

            elif stage == "domain_expert":
                if result.architect is None or result.architect.spec is None:
                    raise ValueError("Architect result missing for domain_expert stage")
                logger.info("pipeline_stage_start", stage="domain_expert", project_id=input_data.project_id)
                result.domain_check = check_domain_compliance(result.architect.spec)

                if not result.domain_check.valid:
                    return PipelineResult(
                        status="domain_validation_failed",
                        error="Domain compliance check failed",
                    )

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
                    return PipelineResult(
                        status="validation_failed",
                        error="Final validation failed",
                    )

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

        except Exception as e:  # noqa: BLE001 - broad catch ensures fallback pipeline stability
            logger.error("pipeline_stage_failed", stage=stage, project_id=input_data.project_id, error=str(e))
            raise

    async def run(self, input_data: PipelineInput, job: Job | None = None) -> PipelineResult:
        """Execute the full pipeline with checkpointing."""
        result = PipelineResult()

        # Try to load existing checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint(input_data.project_id)
        start_stage_index = 0

        if checkpoint:
            logger.info("checkpoint_loaded", project_id=input_data.project_id, stage=checkpoint.stage)
            # Reconcile staleness: checkpoint.input_data may contain prior prompt/context.
            # Use checkpoint input as base, but overlay any fresh non-empty fields from incoming input_data.
            # This prevents stale prompt override while allowing clarification_answers updates.
            try:
                ckpt_input = PipelineInput(**checkpoint.input_data)
                # Overlay: if incoming prompt differs and is non-empty, prefer incoming (user correction)
                # Otherwise keep checkpoint
                if input_data.prompt and input_data.prompt != ckpt_input.prompt:
                    logger.info("checkpoint_input_stale_prompt", checkpoint_prompt=ckpt_input.prompt[:50], incoming_prompt=input_data.prompt[:50])
                    # Keep incoming prompt but preserve checkpoint's context if incoming empty
                    ckpt_input.prompt = input_data.prompt
                if input_data.context:
                    ckpt_input.context = {**ckpt_input.context, **input_data.context}
                if input_data.clarification_answers:
                    ckpt_input.clarification_answers = {**ckpt_input.clarification_answers, **input_data.clarification_answers}
                input_data = ckpt_input
            except Exception:  # noqa: BLE001
                logger.warning("checkpoint_input_reconcile_failed", project_id=input_data.project_id)
            # Restore stage outputs
            stage_outputs = dict(checkpoint.stage_outputs)  # copy to avoid mutation of cached dict
            start_stage_index = checkpoint.stage_index + 1

            # Restore data from checkpoint
            self._load_stage_outputs(checkpoint.stage_outputs, result)
        else:
            stage_outputs = {}
        
        try:
            # Execute remaining stages
            for stage_index in range(start_stage_index, len(self.STAGES)):
                stage = self.STAGES[stage_index]
                stage_result = await self._run_stage(stage, stage_index, input_data, stage_outputs, job)
                
                # Merge stage result
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

                # Update checkpoint after each stage - preserve all prior stage outputs (HIGH: 288 checkpoint key, 309 save logic)
                # Store each stage result under its canonical key; do not wipe unrelated keys
                if stage_result.intake is not None:
                    stage_outputs["intake"] = stage_result.intake.model_dump()
                if stage_result.clarification is not None:
                    stage_outputs["clarification"] = stage_result.clarification.model_dump()
                if stage_result.research is not None:
                    stage_outputs["research"] = stage_result.research.model_dump()
                if stage_result.architect is not None:
                    # Store full ArchitectResult to preserve generation_notes (HIGH: 296 vs ArchitectResult)
                    # Loader handles both spec-only dict and full result dict for backward compat
                    try:
                        stage_outputs["architect"] = stage_result.architect.model_dump()
                        # For backward compat, also ensure spec dict available via spec key if loader expects spec-only
                        # Loader now checks both shapes
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
                # Also ensure generic stage key points to its typed key for outer checkpoint resume logic
                # (keeps checkpoint.stage_index mapping stable)
                if stage not in stage_outputs:
                    # e.g., stage "domain_expert" already stored as domain_expert; avoid empty placeholder
                    stage_outputs[stage] = stage_outputs.get(stage, {})

                # Save checkpoint after each stage (atomic via PipelineCheckpointManager)
                self.checkpoint_manager.save_checkpoint(
                    PipelineCheckpoint(
                        project_id=input_data.project_id,
                        stage=stage,
                        stage_index=stage_index,
                        input_data=input_data.model_dump(),
                        stage_outputs=dict(stage_outputs),  # copy for safety
                    )
                )

            # Success
            result.spec = result.architect.spec if result.architect else None
            # Remove self-assignment (HIGH: 321) - keep scene_package as is (None for MVP)
            # result.scene_package already merged above
            result.status = "completed"

            logger.info("pipeline_completed", project_id=input_data.project_id, status=result.status)

            # Clear checkpoint only on successful completion (HIGH: 327 clear only success)
            if result.status == "completed":
                self.checkpoint_manager.clear_checkpoint(input_data.project_id)

        except Exception as e:  # noqa: BLE001 - broad catch to ensure pipeline reports failure for any error (HIGH: outer except)
            logger.error("pipeline_failed", project_id=input_data.project_id, error=str(e))
            result.status = "failed"
            result.error = str(e)
        
        return result
    
    async def run_intake_only(self, prompt: str, context: dict[str, Any] | None = None) -> IntakeResult:
        """Run only the intake stage."""
        return await process_intake(prompt, context or {})

    async def run_clarification(
        self,
        domain: str,
        current_answers: dict[str, Any],
        new_answers: dict[str, str],
    ) -> ClarificationResult:
        """Run only the clarification stage."""
        return await process_clarification_answers(domain, current_answers, new_answers)

    async def run_from_clarification(
        self,
        project_id: int,
        prompt: str,
        intake_data: IntakeResult,
        clarification_data: ClarificationResult,
        context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Run pipeline from clarification stage onwards."""
        input_data = PipelineInput(
            project_id=project_id,
            prompt=prompt,
            context=context or {},
            clarification_answers=clarification_data.updated_fields
        )
        # Manually set intake and clarification
        result = await self.run(input_data)
        result.intake = intake_data
        result.clarification = clarification_data
        return result


# Global pipeline instance
real_estate_pipeline = RealEstatePipeline()


async def generate_real_estate_spec(
    project_id: int,
    prompt: str,
    context: dict[str, Any] | None = None,
    clarification_answers: dict[str, str] | None = None,
    expected_domain: str | None = None,
) -> PipelineResult:
    """Convenience function for real estate spec generation."""
    input_data = PipelineInput(
        project_id=project_id,
        prompt=prompt,
        context=context or {},
        clarification_answers=clarification_answers or {},
        expected_domain=expected_domain or "real_estate",
    )
    return await real_estate_pipeline.run(input_data)

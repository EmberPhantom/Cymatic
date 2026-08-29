"""Real Estate Generation Pipeline - Orchestrates all agents for spec generation with checkpointing"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from cymatic_shared.schemas.simulation_spec import SimulationSpec, Entity
from app.agents.intake_agent import process_intake, IntakeResult
from app.agents.clarification_agent import process_clarification_answers, ClarificationResult
from app.agents.research_agent import research_generation, ResearchResult
from app.agents.domain_expert_agent import check_domain_compliance, DomainCheckResult
from app.agents.architect_agent import create_simulation_spec, ArchitectResult
from app.agents.asset_agent import select_assets, AssetAgentResult
from app.agents.composer_agent import compose_scene, ComposerResult
from app.agents.validation_agent import validate_simulation_spec, ValidationAgentResult
from app.agents.scene_package import generate_scene_package, ScenePackage
from app.core.queue import Job, JobPriority, JobStatus
from app.pipelines.checkpoint import PipelineCheckpointManager, PipelineCheckpoint
import structlog
import asyncio

logger = structlog.get_logger()


class PipelineInput(BaseModel):
    project_id: int
    prompt: str
    context: Dict[str, Any] = {}
    clarification_answers: Dict[str, str] = {}


class PipelineResult(BaseModel):
    spec: Optional[SimulationSpec] = None
    scene_package: Optional[ScenePackage] = None
    intake: Optional[IntakeResult] = None
    clarification: Optional[ClarificationResult] = None
    research: Optional[ResearchResult] = None
    domain_check: Optional[DomainCheckResult] = None
    architect: Optional[ArchitectResult] = None
    composer: Optional[ComposerResult] = None
    assets: Optional[AssetAgentResult] = None
    validation: Optional[ValidationAgentResult] = None
    status: str = "pending"
    error: Optional[str] = None


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
    
    def _load_stage_outputs(self, stage_outputs: Dict[str, Any], result: 'PipelineResult'):
        """Load stage outputs into result object."""
        if "intake" in stage_outputs:
            from app.agents.intake_agent import IntakeResult
            result.intake = IntakeResult(**stage_outputs["intake"])
        if "clarification" in stage_outputs:
            from app.agents.clarification_agent import ClarificationResult
            result.clarification = ClarificationResult(**stage_outputs["clarification"])
        if "research" in stage_outputs:
            from app.agents.research_agent import ResearchResult
            result.research = ResearchResult(**stage_outputs["research"])
        if "architect" in stage_outputs:
            from cymatic_shared.schemas.simulation_spec import SimulationSpec
            result.architect = ArchitectResult(spec=SimulationSpec(**stage_outputs["architect"]))
        if "composer" in stage_outputs:
            result.composer = ComposerResult(**stage_outputs["composer"])
        if "domain_expert" in stage_outputs:
            result.domain_check = DomainCheckResult(**stage_outputs["domain_expert"])
        if "asset_selection" in stage_outputs:
            result.assets = AssetAgentResult(**stage_outputs["asset_selection"])
        if "validation" in stage_outputs:
            result.validation = ValidationAgentResult(**stage_outputs["validation"])
        if "scene_package" in stage_outputs:
            result.scene_package = ScenePackage(**stage_outputs["scene_package"])
    
    async def _run_stage(self, stage: str, stage_index: int, input_data: PipelineInput, 
                         stage_outputs: Dict[str, Any], job: Job = None) -> 'PipelineResult':
        """Execute a single pipeline stage."""
        from app.agents.intake_agent import process_intake
        from app.agents.clarification_agent import process_clarification_answers
        from app.agents.research_agent import research_generation
        from app.agents.architect_agent import create_simulation_spec
        from app.agents.asset_agent import select_assets
        from app.agents.composer_agent import compose_scene
        from app.agents.validation_agent import validate_simulation_spec
        from app.agents.scene_package import generate_scene_package
        from app.agents.domain_expert_agent import check_domain_compliance
        
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
                        completion_percentage=1.0
                    )
                else:
                    logger.info("pipeline_stage_start", stage="clarification", project_id=input_data.project_id)
                    result.clarification = await process_clarification_answers(
                        result.intake.detected_domain,
                        result.intake.extracted_entities,
                        input_data.clarification_answers
                    )
                    
                    if not result.clarification.ready_for_generation:
                        return PipelineResult(
                            status="awaiting_clarification",
                            error="Awaiting clarification"
                        )
                
            elif stage == "research":
                logger.info("pipeline_stage_start", stage="research", project_id=input_data.project_id)
                style = result.intake.extracted_entities.get("style", "modern")
                research_reqs = {
                    "target_fps": 60,
                    "max_triangles": 100000,
                    "texture_budget_mb": 100,
                }
                result.research = research_generation(
                    result.intake.detected_domain,
                    style,
                    research_reqs
                )
                
            elif stage == "architect":
                logger.info("pipeline_stage_start", stage="architect", project_id=input_data.project_id)
                clarification_data = result.clarification.updated_fields if result.clarification else {}
                result.architect = await create_simulation_spec(
                    domain=result.intake.detected_domain,
                    objective=input_data.prompt,
                    intake_data=result.intake.extracted_entities,
                    clarification_data=clarification_data,
                    context=input_data.context
                )
                
            elif stage == "composer":
                logger.info("pipeline_stage_start", stage="composer", project_id=input_data.project_id)
                clarification_data = result.clarification.updated_fields if result.clarification else {}
                result.composer = compose_scene(
                    entities=result.architect.spec.entities,
                    domain=result.intake.detected_domain,
                    user_preferences=clarification_data
                )
                
                # Update spec with composed layout
                result.architect.spec.entities = result.composer.entities
                result.architect.spec.navigation = result.composer.navigation
                result.architect.spec.lighting = result.composer.lighting
                
            elif stage == "domain_expert":
                logger.info("pipeline_stage_start", stage="domain_expert", project_id=input_data.project_id)
                result.domain_check = check_domain_compliance(result.architect.spec)
                
                if not result.domain_check.valid:
                    return PipelineResult(
                        status="domain_validation_failed",
                        error="Domain compliance check failed"
                    )
                
            elif stage == "asset_selection":
                logger.info("pipeline_stage_start", stage="asset_selection", project_id=input_data.project_id)
                result.assets = select_assets(
                    spec_entities=result.architect.spec.entities,
                    domain=result.intake.detected_domain,
                    performance_budget=result.architect.spec.performance_budget.model_dump()
                )
                
            elif stage == "validation":
                logger.info("pipeline_stage_start", stage="validation", project_id=input_data.project_id)
                result.validation = validate_simulation_spec(result.architect.spec.model_dump())
                
                if not result.validation.valid:
                    return PipelineResult(
                        status="validation_failed",
                        error="Final validation failed"
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
                status="completed"
            )
            
        except (ValueError, KeyError) as e:
            logger.error("pipeline_stage_failed", stage=stage, project_id=input_data.project_id, error=str(e))
            raise
    
    async def run(self, input_data: PipelineInput, job: Job = None) -> PipelineResult:
        """Execute the full pipeline with checkpointing."""
        result = PipelineResult()
        
        # Try to load existing checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint(input_data.project_id)
        start_stage_index = 0
        
        if checkpoint:
            logger.info("checkpoint_loaded", project_id=input_data.project_id, stage=checkpoint.stage)
            # Restore stage outputs
            stage_outputs = checkpoint.stage_outputs
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
                
                # Update checkpoint after each stage
                stage_outputs[stage] = {}
                if hasattr(stage_result, 'intake') and stage_result.intake:
                    stage_outputs["intake"] = stage_result.intake.model_dump()
                if hasattr(stage_result, 'clarification') and stage_result.clarification:
                    stage_outputs["clarification"] = stage_result.clarification.model_dump()
                if hasattr(stage_result, 'research') and stage_result.research:
                    stage_outputs["research"] = stage_result.research.model_dump()
                if hasattr(stage_result, 'architect') and stage_result.architect:
                    stage_outputs["architect"] = stage_result.architect.spec.model_dump()
                if hasattr(stage_result, 'composer') and stage_result.composer:
                    stage_outputs["composer"] = stage_result.composer.model_dump()
                if hasattr(stage_result, 'domain_check') and stage_result.domain_check:
                    stage_outputs["domain_expert"] = stage_result.domain_check.model_dump()
                if hasattr(stage_result, 'assets') and stage_result.assets:
                    stage_outputs["asset_selection"] = stage_result.assets.manifest.model_dump()
                if hasattr(stage_result, 'validation') and stage_result.validation:
                    stage_outputs["validation"] = stage_result.validation.model_dump()
                if hasattr(stage_result, 'scene_package') and stage_result.scene_package:
                    stage_outputs["scene_package"] = stage_result.scene_package.model_dump()
                
                # Save checkpoint after each stage
                self.checkpoint_manager.save_checkpoint(
                    PipelineCheckpoint(
                        project_id=input_data.project_id,
                        stage=stage,
                        stage_index=stage_index,
                        input_data=input_data.model_dump(),
                        stage_outputs=stage_outputs,
                    )
                )
            
            # Success
            result.spec = result.architect.spec if result.architect else None
            result.scene_package = result.scene_package
            result.status = "completed"
            
            logger.info("pipeline_completed", project_id=input_data.project_id, status=result.status)
            
            # Clear checkpoint on success
            self.checkpoint_manager.clear_checkpoint(input_data.project_id)
            
        except (ValueError, KeyError, OSError) as e:
            logger.error("pipeline_failed", project_id=input_data.project_id, error=str(e))
            result.status = "failed"
            result.error = str(e)
        
        return result
    
    async def run_intake_only(self, prompt: str, context: Dict[str, Any] = None) -> IntakeResult:
        """Run only the intake stage."""
        return await process_intake(prompt, context or {})
    
    async def run_clarification(
        self,
        domain: str,
        current_answers: Dict[str, Any],
        new_answers: Dict[str, str]
    ) -> ClarificationResult:
        """Run only the clarification stage."""
        return await process_clarification_answers(domain, current_answers, new_answers)
    
    async def run_from_clarification(
        self,
        project_id: int,
        prompt: str,
        intake_data: IntakeResult,
        clarification_data: ClarificationResult,
        context: Dict[str, Any] = None
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
    context: Dict[str, Any] = None,
    clarification_answers: Dict[str, str] = None
) -> PipelineResult:
    """Convenience function for real estate spec generation."""
    input_data = PipelineInput(
        project_id=project_id,
        prompt=prompt,
        context=context or {},
        clarification_answers=clarification_answers or {}
    )
    return await real_estate_pipeline.run(input_data)

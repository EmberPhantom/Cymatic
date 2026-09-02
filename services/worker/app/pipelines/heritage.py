"""Heritage Generation Pipeline - Orchestrates agents for heritage spec generation"""
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
from app.core.queue import Job, JobStatus
from app.pipelines.heritage_templates import create_heritage_spec_from_template, HeritageTemplateLibrary
import structlog

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
    
    async def run(self, input_data: PipelineInput, job: Job = None) -> PipelineResult:
        """Execute the full heritage pipeline."""
        result = PipelineResult()
        
        try:
            # Stage 1: Intake
            logger.info("pipeline_stage_start", stage="intake", project_id=input_data.project_id)
            if job:
                job.status = JobStatus.RUNNING
            result.intake = await process_intake(input_data.prompt, input_data.context)
            
            # Stage 2: Clarification
            if input_data.clarification_answers:
                logger.info("pipeline_stage_start", stage="clarification", project_id=input_data.project_id)
                result.clarification = await process_clarification_answers(
                    result.intake.detected_domain,
                    result.intake.extracted_entities,
                    input_data.clarification_answers
                )
                
                if not result.clarification.ready_for_generation:
                    result.status = "awaiting_clarification"
                    return result
            
            # Stage 3: Research
            logger.info("pipeline_stage_start", stage="research", project_id=input_data.project_id)
            site_type = result.intake.extracted_entities.get("site_type", "courtyard")
            research_reqs = {
                "target_fps": 60,
                "max_triangles": 100000,
                "texture_budget_mb": 100,
            }
            result.research = research_generation(
                result.intake.detected_domain,
                site_type,
                research_reqs
            )
            
            # Stage 4: Apply heritage template
            template = self.HERITAGE_TEMPLATES.get(site_type, self.HERITAGE_TEMPLATES["courtyard"])
            
            # Stage 5: Architect - Create spec with template (use full library if available)
            logger.info("pipeline_stage_start", stage="architect", project_id=input_data.project_id)
            clarification_data = result.clarification.updated_fields if result.clarification else {}
            # If template_id provided or site_type matches library, use full template library for richer heritage spec
            template_id = (input_data.context or {}).get("template_id") or clarification_data.get("template_id")
            if template_id and template_id in HeritageTemplateLibrary.TEMPLATES:
                # Full library path includes courtyard_sequence radial fixes
                spec = create_heritage_spec_from_template(template_id, f"Project {input_data.project_id}", {**clarification_data, "site_type": site_type})
                from app.agents.architect_agent import ArchitectResult
                result.architect = ArchitectResult(spec=spec, prompt=input_data.prompt, domain="heritage", used_fallback=False)
            else:
                result.architect = await create_simulation_spec(
                    domain=result.intake.detected_domain,
                    objective=input_data.prompt,
                    intake_data={**result.intake.extracted_entities, "site_type": site_type, "template": template},
                    clarification_data=clarification_data,
                    context=input_data.context
                )
            
            # Stage 6: Composer - Spatial layout
            logger.info("pipeline_stage_start", stage="composer", project_id=input_data.project_id)
            result.composer = compose_scene(
                entities=result.architect.spec.entities,
                domain=result.intake.detected_domain,
                user_preferences=clarification_data
            )
            
            # Update spec with composed layout
            result.architect.spec.entities = result.composer.entities
            result.architect.spec.navigation = result.composer.navigation
            result.architect.spec.lighting = result.composer.lighting
            
            # Stage 7: Domain Expert Check (heritage-specific)
            logger.info("pipeline_stage_start", stage="domain_expert", project_id=input_data.project_id)
            result.domain_check = check_domain_compliance(result.architect.spec)
            
            if not result.domain_check.valid:
                result.status = "domain_validation_failed"
                result.error = "Heritage domain compliance check failed"
                return result
            
            # Stage 8: Asset Selection
            logger.info("pipeline_stage_start", stage="asset_selection", project_id=input_data.project_id)
            result.assets = select_assets(
                spec_entities=result.architect.spec.entities,
                domain=result.intake.detected_domain,
                performance_budget=result.architect.spec.performance_budget.model_dump()
            )
            
            # Stage 9: Final Validation
            logger.info("pipeline_stage_start", stage="validation", project_id=input_data.project_id)
            result.validation = validate_simulation_spec(result.architect.spec.model_dump())
            
            if not result.validation.valid:
                result.status = "validation_failed"
                result.error = "Final validation failed"
                return result
            
            # Success
            result.spec = result.architect.spec
            result.scene_package = None
            result.status = "completed"
            
            logger.info("pipeline_completed", project_id=input_data.project_id, status=result.status)
            
        except (ValueError, KeyError, OSError) as e:
            logger.error("pipeline_failed", project_id=input_data.project_id, error=str(e))
            result.status = "failed"
            result.error = str(e)
        
        return result
    
    def get_template(self, site_type: str) -> Dict[str, Any]:
        """Get heritage template for site type."""
        return self.HERITAGE_TEMPLATES.get(site_type, self.HERITAGE_TEMPLATES["courtyard"])
    
    def list_templates(self) -> List[str]:
        """List available heritage templates."""
        return list(self.HERITAGE_TEMPLATES.keys())


# Global pipeline instance
heritage_pipeline = HeritagePipeline()


async def generate_heritage_spec(
    project_id: int,
    prompt: str,
    context: Dict[str, Any] = None,
    clarification_answers: Dict[str, str] = None
) -> PipelineResult:
    """Convenience function for heritage spec generation."""
    input_data = PipelineInput(
        project_id=project_id,
        prompt=prompt,
        context=context or {},
        clarification_answers=clarification_answers or {}
    )
    return await heritage_pipeline.run(input_data)

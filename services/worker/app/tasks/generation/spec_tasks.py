"""Worker spec task handlers (split from tasks/generation.py, no logic change)."""
import structlog

from app.core.queue import register_job_handler
from cymatic_shared.models import Project, ProjectStatus
from cymatic_shared.models import SimulationSpec as SimulationSpecModel, SpecStatus

from sqlalchemy import select, func, text
from cymatic_shared.models import GenerationRun
from cymatic_shared.model_enums import RunStatus, RunStage

# DB sessions resolve via the generation package namespace so tests
# can patch app.tasks.generation.AsyncSessionLocal.
from app.tasks import generation as _gen

logger = structlog.get_logger()


@register_job_handler("generate_spec")
async def generate_spec_task(payload: dict) -> dict:
    """Generate simulation specification from prompt using pipeline."""
    project_id = payload.get("project_id")
    prompt = payload.get("prompt")
    context = payload.get("context", {})
    clarification_answers = payload.get("clarification_answers", {})
    run_id = payload.get("run_id")
    
    logger.info("generate_spec_started", project_id=project_id)
    
    async with _gen.AsyncSessionLocal() as db:
        # Get project with row lock to prevent concurrent version assignment
        result = await db.execute(
            select(Project)
            .where(Project.id == project_id)
            .with_for_update()  # Lock the project row
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Update project status
        project.status = ProjectStatus.SPEC_GENERATING
        if run_id:
            run = await db.scalar(select(GenerationRun).where(
                GenerationRun.id == run_id, GenerationRun.project_id == project_id
            ))
            if run:
                run.status = RunStatus.GENERATING_SPEC
                run.stage = RunStage.SPEC
                run.progress = 35
        await db.commit()
    
    # Run appropriate pipeline based on domain (persist run failure on ANY error
    # so GET generation-runs never stays stuck at 35% generating_spec).
    try:
        if project.domain == "real_estate":
            from app.pipelines.real_estate import generate_real_estate_spec
            pipeline_result = await generate_real_estate_spec(
                project_id=project_id,
                prompt=prompt,
                context=context,
                clarification_answers=clarification_answers,
                expected_domain=project.domain,
            )
        elif project.domain == "heritage":
            from app.pipelines.heritage import generate_heritage_spec
            pipeline_result = await generate_heritage_spec(
                project_id=project_id,
                prompt=prompt,
                context=context,
                clarification_answers=clarification_answers,
                expected_domain=project.domain,
            )
        else:
            raise ValueError(f"Unknown domain: {project.domain}")
    except Exception as exc:
        async with _gen.AsyncSessionLocal() as db:
            if run_id:
                run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
                if run and run.status != "failed":
                    run.status = RunStatus.FAILED
                    run.stage = RunStage.SPEC
                    run.progress = 55
                    run.error_json = {"code": "pipeline_exception", "error": str(exc)[:1000]}
                    await db.commit()
        raise
    
    # Handle pipeline result
    if pipeline_result.status == "awaiting_clarification":
        # Return clarification questions
        result = {
            "status": "awaiting_clarification",
            "questions": [q.model_dump() for q in pipeline_result.clarification.questions] if pipeline_result.clarification else [],
            "current_answers": pipeline_result.clarification.updated_fields if pipeline_result.clarification else {},
            "completion": pipeline_result.clarification.completion_percentage if pipeline_result.clarification else 0
        }
        async with _gen.AsyncSessionLocal() as db:
            if run_id:
                run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
                if run:
                    run.status = RunStatus.NEEDS_CLARIFICATION
                    run.stage = RunStage.CLARIFICATION
                    run.progress = int(result["completion"] * 100)
                    run.clarification_json = result["current_answers"]
                    await db.commit()
        return result
    
    if pipeline_result.status != "completed" or not pipeline_result.spec:
        err = pipeline_result.error or f"Pipeline ended with status={pipeline_result.status}"
        async with _gen.AsyncSessionLocal() as db:
            if run_id:
                run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
                if run:
                    run.status = RunStatus.FAILED
                    run.stage = pipeline_result.status or "spec"
                    run.progress = 55
                    run.error_json = {
                        "code": f"pipeline_{pipeline_result.status}",
                        "error": err,
                    }
                    await db.commit()
        raise ValueError(f"Pipeline failed: {err}")
    
    # Validate the complete proposal before it can become trusted state.
    from app.agents.validation_agent import validate_simulation_spec
    validation_result = validate_simulation_spec(pipeline_result.spec.model_dump())
    if not validation_result.valid:
        errors = validation_result.errors
        async with _gen.AsyncSessionLocal() as db:
            if run_id:
                run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
                if run:
                    run.status = RunStatus.FAILED
                    run.stage = RunStage.VALIDATION
                    run.progress = 55
                    run.error_json = {"code": "spec_validation_failed", "errors": errors}
                    await db.commit()
        raise ValueError(f"Generated specification failed validation: {errors}")

    # Save spec to database with atomic version assignment
    async with _gen.AsyncSessionLocal() as db:
        spec = pipeline_result.spec

        # Atomic version assignment via transactional advisory lock (HIGH: SELECT max with FOR UPDATE illegal)
        # Previous FOR UPDATE on aggregate is invalid syntax in Postgres (cannot lock aggregate row).
        # Use pg_advisory_xact_lock keyed by project_id to serialize concurrent version increments.
        # Project row was already locked earlier, but that lock is released after commit; advisory lock holds for transaction.
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(project_id)})
        result = await db.execute(
            select(func.coalesce(func.max(SimulationSpecModel.version), 0) + 1)
            .where(SimulationSpecModel.project_id == project_id)
        )
        next_version = result.scalar_one()
        
        # Create spec record (serialize with alias for TS/frontend compatibility).
        # mode="json" is required: model_dump() leaves datetime objects as-is
        # and asyncpg cannot serialize those into the JSON column (live Taj
        # run died here with "Object of type datetime is not JSON serializable").
        db_spec = SimulationSpecModel(
            project_id=project_id,
            version=next_version,
            payload_json=spec.model_dump(by_alias=True, mode="json"),
            status=SpecStatus.VALID,
        )
        db.add(db_spec)
        
        # Update project status
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.SPEC_READY
        if run_id:
            run = await db.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
            if run:
                run.status = RunStatus.SPEC_READY
                run.stage = RunStage.VALIDATION
                run.progress = 60
                run.result_json = {
                    "spec_id": db_spec.id, "version": db_spec.version,
                    "validation": validation_result.model_dump(),
                }
        
        await db.commit()
        await db.refresh(db_spec)
        
        logger.info("generate_spec_completed", project_id=project_id, spec_id=db_spec.id, version=db_spec.version)
        
        return {
            "spec_id": db_spec.id,
            "version": db_spec.version,
            "pipeline_details": {
                "intake": pipeline_result.intake.model_dump() if pipeline_result.intake else None,
                "research": pipeline_result.research.model_dump() if pipeline_result.research else None,
                "domain_check_score": pipeline_result.domain_check.compliance_score if pipeline_result.domain_check else None,
                "validation_score": pipeline_result.validation.spec_score if pipeline_result.validation else None,
                "validation": validation_result.model_dump(),
            }
        }


@register_job_handler("validate_spec")
async def validate_spec_task(payload: dict) -> dict:
    """Validate simulation specification using validation agent."""
    spec_id = payload.get("spec_id")
    
    logger.info("validate_spec_started", spec_id=spec_id)
    
    async with _gen.AsyncSessionLocal() as db:
        result = await db.execute(select(SimulationSpecModel).where(SimulationSpecModel.id == spec_id))
        spec = result.scalar_one_or_none()
        if not spec:
            raise ValueError(f"Spec {spec_id} not found")
        
        spec.status = SpecStatus.VALIDATING
        await db.commit()
        
        # Run validation agent
        from app.agents.validation_agent import validate_simulation_spec
        validation_result = validate_simulation_spec(spec.payload_json)
        
        spec.status = SpecStatus.VALID if validation_result.valid else SpecStatus.INVALID
        await db.commit()
        
        logger.info("validate_spec_completed", spec_id=spec_id, valid=validation_result.valid, score=validation_result.spec_score)
        
        return validation_result.model_dump()



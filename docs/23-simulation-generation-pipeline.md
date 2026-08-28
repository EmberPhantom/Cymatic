# Simulation Generation Pipeline

The MVP generation workflow is deliberately renderer-neutral:

`Intake → Clarification → Spec Generation → Validation → Scene Package → Artifact Verification → Publish`

Each intake creates a durable `generation_runs` record. The record is scoped to the project and organization and remains available after a worker restart. Redis job status is execution state; the generation run is product state.

## API flow

1. `POST /v1/projects/{project_id}/intake` with `{ "prompt": "..." }`.
2. Persist the returned `run_id`.
3. If questions are returned, call `POST /v1/projects/{project_id}/clarify` with `run_id`, `answers`, and `current_intake`.
4. Call `POST /v1/projects/{project_id}/generate-spec` with `run_id`, `prompt`, and `clarification_answers`.
5. Poll the returned job or `GET /v1/projects/{project_id}/generation-runs/{run_id}`.
6. Once the spec is valid, call `POST /v1/projects/{project_id}/generate-scene`.
7. Once the scene package is verified and ready, call `POST /v1/projects/{project_id}/publish`.

Generation never publishes automatically. Scene generation only accepts a valid spec belonging to the same project. Ready packages are reused on retry for the same project/spec pair.

## Trust boundaries

Agent output is parsed into the shared `SimulationSpec` schema and passed through business validation before it is persisted as valid. Scene packages are schema-validated, uploaded to MinIO, size-verified, and recorded with a SHA-256 checksum before becoming ready.

Required assets must be available to the asset selector. Optional assets may use the selector's documented fallback behavior. Unity, WebRTC, and Android streaming consume the `cymatic_v1` package later; they are not part of this generation milestone.

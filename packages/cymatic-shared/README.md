# `cymatic-shared` — shared Python package (single source)

Imported by api/worker/llm-router (`-e` locally, `shared` build context in
Docker). Owns: schemas, validators, `JobQueue`, `MinIOClient`, agent
helpers, LLM client. Service `core/*` modules re-export from here —
never fork (see `docs/tech-debt.md` for the unification history).

Install: `pip install -e packages/cymatic-shared` (done by each
service's `requirements.txt`). Tests: `pytest packages/cymatic-shared`.

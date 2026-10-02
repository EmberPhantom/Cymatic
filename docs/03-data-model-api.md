# CYMATIC Data Model and API Design

## Core Design Rules

- All resources are tenant-scoped.
- All important state changes are auditable.
- Long-running generation tasks are asynchronous.
- Streaming sessions are separate from project records.
- AI actions are logged.

---

## Core Tables

### users
- id
- email
- name
- role
- organization_id
- created_at

### organizations
- id
- name
- plan
- settings_json
- created_at

### projects
- id
- organization_id
- name
- domain
- category
- status
- created_by
- created_at
- updated_at

### simulation_specs
- id
- project_id
- version
- payload_json
- status
- created_at

### assets
- id
- organization_id
- project_id
- type
- storage_key
- status
- created_at

### scene_packages
- id
- project_id
- spec_id
- storage_key
- status
- created_at

### stream_sessions
- id
- project_id
- user_id
- device_info_json
- started_at
- ended_at
- status

### runtime_events
- id
- stream_session_id
- event_type
- payload_json
- created_at

### agent_actions
- id
- stream_session_id
- agent_name
- action_type
- input_json
- output_json
- policy_result
- created_at

### voice_sessions
- id
- stream_session_id
- language
- stt_provider
- tts_provider
- transcript_text
- response_text
- created_at

### credit_ledger
- id
- organization_id
- event_type
- amount
- reference_id
- created_at

### audit_logs
- id
- organization_id
- actor_id
- action
- resource_type
- resource_id
- created_at

---

## API Design Principles

- RESTful versioned endpoints
- explicit tenant scoping
- schema validation
- async jobs for generation
- streaming session signaling endpoints
- usage and analytics endpoints

---

## Core Endpoints

### Auth
```text
POST /v1/auth/login
POST /v1/auth/logout
GET  /v1/auth/me
POST /v1/auth/refresh
```

### Organizations
```text
GET   /v1/organizations/me
PATCH /v1/organizations/me
GET   /v1/organizations/me/members
POST  /v1/organizations/me/members/invite
DELETE /v1/organizations/me/members/{user_id}
```

### Users
```text
GET   /v1/users
POST  /v1/users/invite
PATCH /v1/users/{id}
DELETE /v1/users/{id}
```

### Projects
```text
GET    /v1/projects
POST   /v1/projects
GET    /v1/projects/{id}
PATCH  /v1/projects/{id}
DELETE /v1/projects/{id}
GET    /v1/projects/{id}/versions
GET    /v1/projects/{id}/versions/{version_id}
```

### Generation
```text
POST /v1/projects/{id}/intake
POST /v1/projects/{id}/clarify
POST /v1/projects/{id}/generate-spec
POST /v1/projects/{id}/validate-spec
POST /v1/projects/{id}/generate-scene
POST /v1/projects/{id}/publish
GET    /v1/projects/{id}/specs
GET    /v1/projects/{id}/specs/{spec_id}
```

### Assets
```text
POST   /v1/assets/upload
GET    /v1/assets
GET    /v1/assets/{id}
DELETE /v1/assets/{id}
POST   /v1/assets/{id}/presign
```

### Streaming
```text
POST /v1/stream/sessions
GET  /v1/stream/sessions/{id}
POST /v1/stream/sessions/{id}/offer
POST /v1/stream/sessions/{id}/answer
POST /v1/stream/sessions/{id}/candidate
POST /v1/stream/sessions/{id}/input
POST /v1/stream/sessions/{id}/end
```

### Native render (Unity-free mobile endpoint)
```text
POST /v1/render/sessions                        # device registry + PUBLISHED check + scene_url
POST /v1/render/sessions/{id}/heartbeat         # PENDING->ACTIVE, sweeps stale sessions
POST /v1/render/sessions/{id}/end               # DISCONNECTED + analytics close
POST /v1/render/sessions/{id}/voice/audio       # multipart PCM/WAV -> STT -> copilot -> TTS
```
Rules: `require_creator` on create, org-scoped project, one active
session/user (409), `app_version >= MOBILE_MIN_APP_VERSION` (426),
revoked devices 403. Sessions share the `stream_sessions` table.

### Copilot / Voice
```text
POST /v1/stream/sessions/{id}/agent/message
POST /v1/stream/sessions/{id}/agent/action
POST /v1/stream/sessions/{id}/voice/transcript
```

### Analytics / Credits
```text
GET /v1/analytics/projects/{id}
GET /v1/analytics/sessions/{id}
GET /v1/analytics/organization
GET /v1/credits/balance
GET /v1/credits/usage
POST /v1/credits/adjust
GET /v1/credits/costs
```

---

## Important Event Types

```text
project_created
spec_generated
scene_generated
scene_published
stream_session_started
stream_session_ended
object_selected
navigation_point_changed
copilot_message_sent
voice_session_started
voice_session_completed
hand_tracking_enabled
hand_tracking_disabled
credits_consumed
```

---

## API Implementation Rules

1. Use Pydantic request/response schemas.
2. Validate tenant access on every request.
3. Use background workers for generation jobs.
4. Store generation status in DB.
5. Log AI provider usage and routing decisions.
6. Keep streaming signaling lightweight.
7. Do not expose provider secrets to frontend.

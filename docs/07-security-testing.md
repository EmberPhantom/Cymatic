# CYMATIC Security, Testing, and Acceptance Criteria

## Security Objectives

Protect:
- tenant data
- uploaded assets
- generated simulations
- AI prompts and outputs
- provider credentials
- session telemetry

---

## Authentication and Authorization

### MVP
- email/password authentication
- role-based access control

### Roles
- Owner
- Admin
- Creator
- Viewer
- Auditor

### Rules
- all endpoints must enforce tenant scoping
- all privileged actions must be role-checked
- all admin actions should be audited

---

## Tenant Isolation

Every important record must include organization/tenant ID.

Isolation required for:
- projects
- specs
- assets
- scene packages
- sessions
- analytics
- credits
- logs

---

## LLM Data Policy

### Free providers
Allowed only for:
- internal development
- non-sensitive demos
- non-tenant test prompts

Not allowed for:
- sensitive customer data
- confidential uploads
- regulated content
- production tenant workloads unless explicitly approved

### Approved providers
Use for:
- tenant-specific workloads
- sensitive project content
- enterprise pilots

---

## Redaction Policy

Before sending prompts to LLM providers:
- remove secrets
- remove unnecessary PII
- remove confidential file content unless authorized
- store sanitized logs only

---

## File Upload Security

Uploads must be:
- size-limited
- type-checked
- tenant-scoped
- processed in isolated workers
- scanned where practical

---

## Voice Privacy

Voice must be handled as sensitive user input.

Rules:
- push-to-talk only
- no continuous listening
- no wake word in MVP
- limited audio retention
- transcript storage controlled by settings

---

## IP Protection

Protect generated simulations with:
- signed scene packages
- role-based export controls
- encrypted storage
- no raw asset export by default
- secure stream session authorization

---

## Testing Strategy

### Unit Tests
Cover:
- schema validation
- API logic
- routing policies
- credit calculations
- permission checks

### Integration Tests
Cover:
- prompt-to-spec flow
- spec-to-scene flow
- asset upload pipeline
- session creation
- event logging

### End-to-End Tests
Cover:
- create project
- generate spec
- publish scene
- start stream session
- send input
- receive copilot response
- end session

### Device Tests
Cover:
- OnePlus 6T
- Redmi Note 8
- low-end fallback behavior

---

## Performance Tests

Measure:
- stream startup time
- frame stability
- input latency
- thermal behavior
- reconnection behavior
- memory usage

---

## Acceptance Criteria for MVP Release

The MVP is release-ready when:
1. real estate walkthrough generation works
2. heritage template demo works
3. true stereo streaming works
4. gaze/controller input works
5. voice copilot works
6. one concurrent stream is stable
7. usage is tracked
8. security basics are enforced
9. experimental modules do not break core experience
10. documentation is complete
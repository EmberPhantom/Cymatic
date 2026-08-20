# CYMATIC AI Agent System and LLM Router

## Agent Philosophy

Agents propose.
Trusted services validate and apply.

Agents must not directly mutate:
- database records
- Unity scenes
- runtime state
- provider configuration
- billing state

---

## Builder-Time Agents

### Intake Agent
- parses prompt
- detects domain
- extracts objective
- identifies missing fields

### Clarification Agent
- asks targeted follow-up questions
- suggests defaults
- records user responses

### Research Agent
- retrieves trusted references
- collects style guidance
- gathers asset candidates
- summarizes constraints

### Domain Expert Agent
- applies real estate/heritage rules
- checks spatial plausibility
- flags unrealistic outputs

### Simulation Architect Agent
- creates structured Simulation Specification
- defines entities, behaviors, navigation, and copilot policy

### Asset Agent
- selects assets
- validates mobile performance constraints
- prepares asset manifest

### Scene Composer Agent
- proposes spatial layout
- defines navigation points
- proposes lighting presets

### Validation Agent
- checks schema correctness
- checks missing objects
- checks broken navigation
- checks performance budget

---

## Runtime Agents

### Copilot Agent
Responsibilities:
- answer questions
- guide tour
- explain objects
- direct user attention
- respond to voice commands

Allowed tools:
- highlight object
- show label
- move user to navigation point
- open menu
- change material where permitted
- pause/resume tour
- play audio hint

### Analytics Agent
Responsibilities:
- summarize session
- detect user difficulty
- identify drop-off points
- suggest improvements

---

## LLM Router Architecture

### Recommended Approach
Use:
- LiteLLM or equivalent proxy as provider abstraction
- custom FastAPI policy layer on top

### Router Responsibilities
- model selection
- provider fallback
- rate limiting
- quota tracking
- usage logging
- sensitivity routing
- caching
- schema enforcement

---

## Supported Providers

### MVP Providers
- Groq
- OpenRouter
- NVIDIA NIM
- OpenAI
- Sarvam

### Local LLM
Not required for MVP.

---

## Routing Policies

### Task-Based Routing
| Task | Model Class |
|---|---|
| intent extraction | fast/small |
| spec generation | strong reasoning |
| validation | structured output reliable |
| copilot chat | low latency |
| embeddings | embedding model |
| STT | speech provider |
| TTS | speech provider |

### Sensitivity-Based Routing
| Data Type | Allowed Providers |
|---|---|
| internal non-sensitive | free providers allowed |
| tenant-sensitive | approved/private providers only |
| regulated/confidential | restricted routing required |

---

## Provider Policy Rules

1. Free providers are allowed only for non-sensitive workloads.
2. Sensitive tenant data must not be sent to free endpoints.
3. Every LLM call should include task metadata.
4. Every LLM call should log provider, model, latency, and token usage.
5. Fallback chains must be configured.
6. Cached responses should be used where safe.
7. Structured outputs must be validated.

---

## Voice Language Policy

- Support all Sarvam-supported languages where possible.
- Explicitly include Telugu.
- If Telugu or another language is unavailable via primary provider, use fallback provider.
- Language should be configurable per project/session.

---

## Agent Guardrails

Agents must not:
- invent unsafe instructions
- present hallucinations as facts
- bypass provider restrictions
- mutate runtime state directly
- access unauthorized tenant data
- escalate prompt-injection content

---

## LLM Router Data Model

### provider_configs
- provider name
- enabled
- priority
- rate limits
- supported tasks

### model_profiles
- profile name
- provider
- model id
- task types
- cost class
- latency class

### routing_policies
- task type
- sensitivity level
- preferred profile
- fallback profile

### usage_logs
- request id
- task type
- provider
- model
- tokens
- latency
- status
# CYMATIC Product Scope

## Product Definition

CYMATIC is a no-code platform that allows users to generate interactive simulations from natural language requirements.

The system:
- gathers user intent
- asks clarifying questions
- generates a structured simulation specification
- builds a simulation scene
- publishes it to a streaming runtime
- provides an AI copilot inside the experience
- tracks usage and session analytics

---

## MVP Objective

Deliver a working prototype/MVP that proves the following loop:

```text
Prompt -> Structured Spec -> Generated Scene -> Streamed VR Experience -> AI Copilot Assistance
```

---

## MVP Domains

### Primary Domain
Real estate

### Secondary Domain
Heritage visualization

### Future Domains
- medical
- hardware engineering
- prototyping
- education labs
- industrial training

The architecture must remain domain-generic, but implementation should focus on real estate and heritage first.

---

## MVP Use Cases

### Real Estate
- furnished apartment walkthrough
- furnished house walkthrough
- interior visualization
- guided client presentation
- material/lighting review

### Heritage
- heritage courtyard walkthrough
- palace hall walkthrough
- temple exterior preview
- historic interior room
- monument grounds preview

---

## MVP User Roles

### Creator
Creates and edits simulations.

Capabilities:
- enter prompt
- answer guided questions
- generate simulation
- manually edit scene
- publish simulation

### Viewer
Experiences the simulation in VR.

Capabilities:
- launch stream session
- navigate environment
- ask copilot questions
- select objects
- receive guidance

### Admin
Manages platform usage.

Capabilities:
- manage users
- manage credits
- inspect audit logs
- manage provider policies

---

## Core MVP Features

### Builder
- prompt input
- guided requirement collection
- structured spec generation
- scene generation
- basic manual editing
- AI prompt-based editing
- publish workflow

### Runtime
- on-device true stereo rendering (Filament SBS)
- gaze dwell interaction
- controller selection
- voice copilot
- text copilot
- contextual hints
- session logging

### AI
- builder agents
- runtime copilot
- LLM router
- fallback routing
- usage logging

---

## Explicit MVP Non-Goals

The following are not part of MVP:
- multiplayer
- public plugin marketplace
- full medical simulation
- hardware engineering simulation
- full CAD/BIM authoring
- certified building-code validation
- historically certified reconstruction
- standalone headset native support
- local LLM hosting
- full-body tracking
- accurate world-space hand physics

---

## MVP Success Criteria

The MVP is successful if:
1. a walkthrough can be generated from prompt
2. the generated scene can be published
3. the Android client can render a true stereo walkthrough on-device
4. gaze/controller input works reliably
5. voice copilot works
6. one concurrent stream is stable
7. usage can be tracked
8. the system is demoable to B2B stakeholders
# CYMATIC Demo Guide

## Overview
This guide walks through the complete demo flow for CYMATIC MVP, from prompt to VR experience with AI copilot.

## Prerequisites

### Hardware
- **Gaming Laptop**: Unity Render Server (Windows, NVIDIA GPU, 16GB+ RAM)
- **Laptop 2**: Backend Services (PostgreSQL, Redis, MinIO, FastAPI, Worker, LLM Router)
- **Android Phone**: OnePlus 6T (primary) or Redmi Note 8 (fallback)
- **VR Headset**: Phone-based VR headset (Google Cardboard compatible)
- **Bluetooth Controller**: Daydream-style or generic Bluetooth gamepad
- **Optional**: UVC Camera for hand tracking (e.g., Arducam 720p UVC)

### Software
- All services running via Docker Compose
- Unity Render Server built and running on Gaming Laptop
- Android App installed on phone
- API keys configured in `.env`

### Network
- All devices on same LAN
- Gaming Laptop IP known for signaling
- Ports: 8000 (API), 8001 (LLM Router), 8002 (Worker), 8080 (Signaling), 9000 (MinIO)

## Demo Scripts

### Scenario 1: Real Estate Walkthrough (5 minutes)

#### 1. Launch Builder (Web)
1. Open http://localhost:3000
2. Click "Get Started"
3. Enter prompt: *"Create a modern 3-bedroom apartment walkthrough with warm lighting and a guided tour"*
4. Click "Generate"

#### 2. Clarification Phase
1. System asks follow-up questions:
   - "What architectural style? (Modern/Traditional/Contemporary/Minimalist)"
   - "How many bedrooms/bathrooms?"
   - "Square footage?"
   - "Budget range?"
2. Answer: "Modern, 3 bedrooms, 2 bathrooms, 1500 sqft, $500K-1M"

#### 3. Generation
1. Click "Generate Specification"
2. Watch progress: Intake → Research → Architect → Composer → Validation
2. View generated spec preview
3. Click "Publish"

#### 4. VR Experience
1. Put phone in VR headset
2. Launch CYMATIC Android app
3. Select project → "Start VR Session"
4. Experience:
   - Stereo streaming starts
   - Gaze navigation (look at navigation points)
   - Controller selection (press trigger)
   - Voice copilot: "Show me the kitchen" (hold PTT button)
   - Copilot highlights kitchen, explains features
   - Navigate through apartment

### Scenario 2: Heritage Walkthrough (5 minutes)

#### 1. Launch Builder
1. New project
2. Prompt: *"Create a heritage temple courtyard walkthrough with guided narration in Telugu"*

#### 2. Clarification
1. Site type: "Temple (South Indian)"
2. Historical period: "Chola Dynasty"
3. Key POIs: "Gopuram, Mandapa, Garbhagriha, Temple Tank"
4. Narration: Yes, with Telugu support

#### 3. Generation & Publish
1. Generate → Validate → Publish

#### 4. VR Experience
1. Enter VR
2. Experience:
   - Radial navigation around courtyard
   - Copilot narration in English/Telugu
   - Gaze at POIs for details
   - Voice questions: "What is the garbhagriha?"
   - Telugu response: "గర్భగృహం అనేది దేవాలయంలో glavni విగ్రహం ఉన్న స్థలం"

## Demo Checklist

### Pre-Demo (30 mins before)
- [ ] All Docker services running (`docker compose ps`)
- [ ] Unity Render Server running on Gaming Laptop
- [ ] Android app installed and tested
- [ ] Bluetooth controller paired
- [ ] Phone in VR headset, calibrated
- [ ] API keys in `.env` (Groq, OpenRouter, Sarvam)
- [ ] MinIO bucket created (`cymatic`)
- [ ] Database migrated (`alembic upgrade head`)
- [ ] Demo scripts printed

### During Demo
- [ ] Monitor streaming stats (FPS, latency, bitrate)
- [ ] Watch thermal levels on phone
- [ ] Have backup phone ready
- [ ] Keep demo under 10 minutes per scenario

### Post-Demo
- [ ] Collect feedback
- [ ] Note any issues
- [ ] Save session logs for analysis

## Troubleshooting

### Streaming Issues
| Symptom | Cause | Fix |
|---------|-------|-----|
| No video | Signaling failed | Check signaling URL, firewall |
| Black screen | Scene not loaded | Check MinIO URL, scene package |
| Low FPS | High poly count | Reduce quality, check thermal |
| High latency | Network congestion | Reduce bitrate, check WiFi |
| Audio echo | Mic/speaker loop | Use headphones, mute when not speaking |

### Voice Copilot Issues
| Symptom | Cause | Fix |
|---------|-------|-----|
| No response | STT failed | Check Sarvam API key, audio format |
| Wrong language | Language detection | Explicitly set language in request |
| TTS not playing | Audio format | Check base64 decoding, sample rate |

### Hand Tracking Issues
| Symptom | Cause | Fix |
|---------|-------|-----|
| Not detected | No UVC camera | Check USB connection, dmesg |
| Jittery hands | Low confidence | Increase min confidence threshold |
| Wrong gestures | Lighting | Improve lighting, check camera angle |

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Stream FPS | ≥30 FPS | Unity stats |
| Motion-to-photon | <100ms | Frame timestamp |
| End-to-end latency | <150ms | Round-trip |
| Voice response | <2s | STT+LLM+TTS |
| Session startup | <10s | Start to stream |
| Thermal throttling | None | Phone temp <45°C |

## API Keys Required

```env
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
NVIDIA_NIM_API_KEY=...
OPENAI_API_KEY=sk-...
SARVAM_API_KEY=...
```

## Support Contacts
- Backend/API: [backend-team@cymatic.dev]
- Unity/Streaming: [unity-team@cymatic.dev]
- Android/Client: [android-team@cymatic.dev]
- ML/AI: [ml-team@cymatic.dev]

## Demo Data
- Sample project IDs: Pre-create 2-3 projects
- Test user: demo@cymatic.dev / demo123
- Pre-generated specs for quick demo
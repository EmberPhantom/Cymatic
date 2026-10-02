# CYMATIC Viewer (mobile-browser walkthrough, :8090)

Lightweight Vite + Three.js SPA: login → pick a published project →
auto-fly walkthrough of the `cymatic_v1` scene package. No SSR, no
builder UI — a preview/fallback next to the native Android renderer.

## Layout

- `src/main.ts` — login → picker → walkthrough bootstrap
- `src/api.ts`, `src/auth.ts` — API + JWT refresh (`localStorage`)
- `src/scene.ts` — package → THREE.Scene (primitives; Z-flip included)
- `src/navigation.ts` — path legs at 1.2 m/s with dwell stops

## Contracts

- Reads only: `GET /v1/projects`, `GET .../scene-package/view`
  (published projects only, server-side JSON — no bucket CORS needed).
- Build-time `VITE_API_URL` (defaults to `http://localhost:8000`).

## Build / test

```bash
npm install && npm run build        # runner installs prod-only deps
npm run type-check
```

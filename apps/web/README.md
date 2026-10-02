# CYMATIC Web Builder (Next.js 14, :3000)

No-code builder UI: prompt → intake → clarify → plan → spec → validate →
scene → publish, plus project dashboard, asset browser, spec editor,
and the stream page.

## Layout

- `src/app/` — App Router (`(auth)`, `(dashboard)`, `api/` proxy)
- `src/components/` — `builder/`, `spec/`, `scene/`, `pipeline/`, `ui/`
- `src/hooks/` — data hooks per domain (`use-intake`, `use-generate-spec`, …)
- `src/lib/` — `api.ts` (axios + refresh), `errors.ts` (message normalization),
  `config.ts`, `routes.ts`, validations
- `src/stores/` — zustand auth store

## Contracts

- Same-origin `/api/*` proxies to the backend; `intake`/`clarify` call
  `NEXT_PUBLIC_API_URL` directly (long-LLM-call workaround).
- Auth: HttpOnly cookies in browser; errors via `getErrorMessage`.

## Build / test

```bash
npm ci --legacy-peer-deps && npm run build
npm run type-check && npx vitest run   # colocated *.test.ts
npx playwright test                    # e2e (chromium)
```

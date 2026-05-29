# @roadside/web — Unified customer + provider web app

**Status:** Placeholder. Scaffolded in Week 2 of the v2 plan (`V2_PLAN.md`).

**What lives here when built:**
- One Vite + React 18 + TypeScript + Tailwind SPA serving both customer and provider roles
- Role-toggle landing page (`/`)
- Customer flow: onboarding → SOS report → live tracking → history
- Provider flow: dashboard → job acceptance → status progression
- Deployed to `app.roadsideagent.com` via Vercel
- Investor-friendly desktop layout; mobile users get the native app instead

**Shared dependencies from `packages/`:**
- `@roadside/ui` — Tailwind config + tokens + shared React components
- `@roadside/api-client` — axios + WebSocket hooks generated from the backend OpenAPI
- `@roadside/types` — shared TypeScript types
- `@roadside/i18n` — translation strings (English-only at v2.0)

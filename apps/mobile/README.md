# RoadSide Mobile — Customer app (Flutter)

**Status:** Placeholder. Scaffolded in Week 4 of the v2 plan (`V2_PLAN.md`).

**Stack:** Flutter 3.41+ (already installed at `C:\Users\HP\flutter_windows_3.41.9-stable`).

**Why Flutter (locked decision 2026-05-29):**
- User already has the Flutter SDK installed
- Pixel-perfect UI control and smoother animations than React Native
- **Trade-off accepted:** no OTA JS bundle updates — every fix requires App Store / Play Store re-submission (1–14 day Apple review window). Plan around this with feature flags + staged rollouts.

**What lives here when built:**
- Customer-only mobile (provider mobile is v2.1)
- Apple + Google + Facebook social sign-on (Apple Sign-in mandatory by store rules)
- Background GPS (foreground only, polite battery) — only requested when an incident is active
- Push notifications via FCM (Android) + APNs (iOS): ASSIGNED, EN_ROUTE, ARRIVED, COMPLETED
- Camera + voice capture for incident reports
- Universal links / app links → `roadsideagent.com` (Week 4)

**Code sharing with web:**
- Cannot share React/TS code (Dart is a separate language)
- API contracts re-implemented in Dart using `openapi-generator-cli` against the FastAPI OpenAPI schema
- Design tokens duplicated by hand from `packages/ui` (color hex strings, spacing scale, typography names)

**Not** under the npm workspace — this folder is owned by Flutter/Dart tooling.

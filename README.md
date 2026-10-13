# SkillBridge V0.1

> Discover, understand, manage, and sync all your AI Skills.

SkillBridge is a local-first AI Skills visual management tool launched from an Agent Skill. It discovers AI agents on your computer, scans their installed Skills, and presents a dashboard.

## Status

- [x] Phase 1: Project directory initialization
- [x] Phase 1: Backend base structure
- [x] Phase 1: `BaseAdapter` contract
- [x] Phase 1: Windows Agent Scanner
- [x] Phase 2: Unified Skill data model
- [x] Phase 2: Skill Scanner
- [x] Phase 2: SKILL.md Parser
- [x] Phase 2: Skill source detection
- [x] Phase 2: Rule-based summary generation
- [x] Phase 2: Cache system
- [x] Phase 2: Skills API
- [x] Phase 3: React + TypeScript + Vite + Tailwind + Motion UI
- [x] Phase 3: Dashboard / Skills / Skill Detail pages
- [x] Phase 3: Backend static file serving
- [x] Phase 3: Dashboard auto open browser
- [x] Phase 4A: Open Skill folder
- [x] Phase 4A: Open SKILL.md
- [x] Phase 4A: Enable / Disable Skill
- [x] Phase 4A: Safe uninstall to local trash
- [x] Phase 4A: Frontend management buttons
- [x] Phase 5A: Preflight safety check system
- [x] Phase 5A: Skill Detail Sync Check dialog
- [x] Phase 5B: Safe Sync + Temporary Install + Validation + Atomic Commit
- [x] Phase 5B: Sync API and Sync dialog flow
- [x] Phase 5C: Sync history persistence
- [x] Phase 5C: Batch sync to multiple Agents
- [x] Phase 5C: Sync progress / polling UI
- [x] Phase 5C: Sync History page
- [x] Phase 6A: Central Skill Library
- [x] Phase 6A: Import to Library
- [x] Phase 6A: Library deployment status
- [x] Phase 6A: Library → Agent Safe Deploy
- [x] Phase 6A: Library UI pages
- [x] Phase 6C: Frontend i18n (zh-CN / en-US)
- [x] Phase 6C: Language persistence
- [x] Phase 6C: Bilingual Skill summaries
- [x] Phase 6C: Summary cache migration
- [x] Mutual Harness sync: opt-in, SKILL.md-only, static compatibility preflight
- [ ] Phase 6B: Marketplace / remote library / advanced conflict resolution

## Quick start

```bash
cd ui
npm install
npm run build
cd ..
python backend/main.py dashboard
```

Language is persisted in `localStorage` under `skillbridge.language`.

## i18n architecture

- `ui/src/i18n/index.ts`
- `ui/src/i18n/locales/zh-CN.json`
- `ui/src/i18n/locales/en-US.json`

## Summary architecture

- `backend/core/summary/manager.py`
- `backend/core/summary/rule_provider.py`
- `backend/core/summary/ai_provider.py` (placeholder)
- Skill model now contains `summaries: { "zh-CN": string, "en-US": string }`
- Cache entries now store `summaries`; old `summary` string is kept for compatibility.

## API endpoints

### Mutual Harness sync

On each app launch, SkillBridge runs a background, read-only compatibility precheck for the installed Harnesses and keeps the default all-Harness plan in memory. Opening the sync dialog reuses this warmed result; choosing a different subset runs a fresh plan using the warmed static-check cache. No files are changed during startup checks.

Files are written only after you click Sync. Mutual sync copies only `SKILL.md`. A Skill author must explicitly opt in by adding this standard metadata map to its frontmatter:

```yaml
metadata:
  skillbridge-sync: allow
```

Missing permission, uncertain Harness support/version, or local file references require review; different existing `SKILL.md` versions are never overwritten. Static preflight is not a guarantee that the Skill will behave identically at runtime.

### Read

- `GET /api/environment`
- `GET /api/agents`
- `GET /api/skills`
- `GET /api/skills/<id>`
- `GET /api/rescan`
- `GET /api/sync/mutual/warmup`

### Library

- `GET /api/library`
- `GET /api/library/skills/<id>`
- `POST /api/library/import`
- `POST /api/library/skills/<id>/deploy`
- `DELETE /api/library/skills/<id>`

### Management / Sync

- `POST /api/skills/<id>/open-folder`
- `POST /api/skills/<id>/open-file`
- `POST /api/skills/<id>/enable`
- `POST /api/skills/<id>/disable`
- `DELETE /api/skills/<id>`
- `POST /api/skills/<id>/preflight`
- `POST /api/skills/<id>/sync`
- `POST /api/skills/<id>/batch-sync`
- `POST /api/sync/mutual/plan`
- `POST /api/sync/mutual` (requires a current reviewed `planId`)
- `GET /api/sync/{transaction_id}`
- `GET /api/sync/history`

## Design rules

- Local First: all scanning/reading stays local.
- Server binds to `127.0.0.1` only.
- No `node_modules` in packaged Skill.
- Frontend is prebuilt into `ui/dist`.
- Library import is non-destructive.
- Library removal never uninstalls Agent copies.
- Library → Agent deployment reuses Safe Sync.
- UI strings are fully i18n-based; no hardcoded user-facing copy.

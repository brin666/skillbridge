---
name: skillbridge
description: Launch SkillBridge, a local-first visual dashboard for discovering, understanding, managing, and safely syncing AI Agent Skills on your computer.
whenToUse: Use when the user asks to open SkillBridge, view their installed AI agents and skills, inspect skill sources, manage or safely synchronize skills across Codex, Claude Code, Qwen Code, TRAE, CodeBuddy, Lingma/Qoder CN, Hermes, and other supported agents.
metadata:
  skillbridge:
    version: 0.1.0
    localOnly: true
    defaultCommand: python backend/main.py dashboard
---

# SkillBridge

SkillBridge is a local-first AI Skills control center. It discovers AI agents installed on this computer, scans the Skills they have installed, and presents a clear dashboard for understanding and safely managing them.

## Phase 6C status

- Full frontend i18n (zh-CN / en-US)
- One-click language switching with `localStorage` persistence
- Bilingual Skill summaries (`summaries.zh-CN` / `summaries.en-US`)
- Summary cache migration from single `summary` to `summaries`
- Rule-based summary provider; AI provider placeholder
- Major API errors now include stable error codes

Marketplace, GitHub online search, cloud sync, account system, team collaboration, auto update, and AI recommendation are intentionally not implemented yet.

## Usage

```bash
cd skillbridge
cd ui && npm install && npm run build && cd ..
python backend/main.py dashboard
```

## Safety

- Binds only to `127.0.0.1` when the local server is running.
- Never uploads skill files, user directories, agent configs, local paths, or environment variables.
- Import to Library is a copy; it never moves or deletes the original Agent Skill.
- Removing from Library only affects the Library copy; deployed Agent copies remain untouched.
- Deploy from Library reuses Preflight + Temporary Install + Validation + Atomic Commit + Rollback.

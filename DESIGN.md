# SkillBridge UI direction

<!-- documented from the shipped UI -->

## Surface

SkillBridge is an operate-mode local control center. The interface helps a developer read local Agent/Skill state, inspect one Skill, and move into a preflight-led sync operation.

## Visual world

The UI uses a local index / operations ledger metaphor: a deep indigo navigation rail anchors the workspace, while the content area is a cool white workbench with hairline dividers. Cobalt is reserved for primary actions and current navigation, green for healthy local state, and amber/red for warnings and destructive actions. Monospace is limited to paths and Skill identifiers.

## Layout

- Persistent left rail on desktop; the rail becomes a horizontal navigation strip below 820px.
- Dashboard first viewport: environment overview and scan action, health meter, four source-derived metrics, Agent matrix, Library status, then the Skill index.
- Skills uses an indexed list rather than a uniform card grid, with search, sort and category tabs.
- Skill details use a two-column reading/action layout; actions move above content on narrow screens.
- Loading, empty, error, disabled, warning and success states use the same surface, button, status-dot and notice vocabulary.

## Interaction language

Buttons use semantic labels and SVG line icons. Hover/focus states alter surface and border contrast, not layout. Sync remains a protected flow: choose targets, run preflight, review warnings, then start sync. All existing API routes and bilingual copy remain in place.

## Responsive rules

At 820px the sidebar becomes a scrollable horizontal navigation row and dashboard columns stack. At 560px filters stack, list metadata can wrap, and detail side actions move above the main content.

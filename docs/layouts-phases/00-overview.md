# Django Layouts — Implementation Phases

> Read [`docs/layouts-plan.md`](../layouts-plan.md) before working on any phase. It contains all design decisions, the full API surface, and the rationale for every choice. This overview and the individual phase files are scoped work plans, not design documents.

## Principle

Each phase produces a **self-contained, working system**. A project could ship after any phase. Later phases add capability without breaking anything built earlier.

## Phases at a Glance

| Phase | Name | Depends on | Rough complexity |
|---|---|---|---|
| [1](./01-sync-core.md) | Synchronous core | — | High |
| [2](./02-async.md) | Async rendering | Phase 1 | Low |
| [3](./03-queues.md) | Render queues | Phase 2 | Medium |
| [4](./04-caching.md) | Panel caching | Phase 2 | Low |
| [5](./05-partial-detection.md) | Partial detection + LayoutMixin | Phase 1 | Low–Medium |
| [6](./06-wagtail.md) | Wagtail + layout inheritance | Phase 1 | Low |

Phases 3–6 are independent of each other once Phase 2 is done and can be tackled in any order or in parallel.

## For Agents

Before starting any phase:
1. Read this overview.
2. Read the phase file in full.
3. **Discuss scope, approach, and any ambiguities with the user before writing code.** The phase files are intentionally not fully prescriptive — there is room to refine implementation details.
4. Follow the TDD cycle in `AGENTS.md`: red → green → refactor.
5. Run `just ci` before marking a phase complete.

## What "Done" Means for a Phase

- All described behaviours are implemented and tested (unit tests covering happy paths and edge cases).
- `just ci` passes (ruff, mypy, djlint, no missing migrations, all tests green).
- The public API surface matches the plan exactly — no additions, no renames.
- A brief note is left for the next agent describing anything discovered during implementation that affects subsequent phases.

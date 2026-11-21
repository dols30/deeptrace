<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# DeepTrace frontend rules

Read the root [`AGENTS.md`](../AGENTS.md) first. Design rules: [`docs/DESIGN_SYSTEM.md`](../docs/DESIGN_SYSTEM.md). API contracts: [`docs/API.md`](../docs/API.md).

- **Data access:** call the backend only through `lib/api.ts` (analyze + legacy reports) or `lib/workflow.ts` (`send()` helper). Do not add Next.js API routes or a second fetch layer. Throw/handle `SESSION_EXPIRED` the same way existing callers do (`auth.expire()`).
- **Types mirror backend schemas.** When a backend response changes, update the TS interface in `lib/` in the same change.
- **Authorization is backend-owned.** Role checks in components (e.g. `DashboardShell` nav, `ReportView` buttons) only hide UI.
- **Score language:** say "Model score" / "screening score"; show `calibrated_probability` only as "Estimated probability: Not available" while it is `null`; always show threshold-validation status; include `<Terms/>` where scores appear. Never fuse or rank detectors into one value.
- **Detector identity:** use `task` from `ComponentResult` when available. Workflow findings have no `task`, and `detectorTask()` in `workspace/findings-inspector.tsx` infers it from `model_name`. Reuse it instead of adding another mapping.
- **Styling:** add classes to `app/globals.css`, reuse existing primitives and tokens, respect the global `prefers-reduced-motion` override, and use the existing breakpoints (1180/980/900/720/700).
- **Components:** client components start with `'use client'`; pages under `app/` stay thin and compose a shell (`DashboardShell` or `SiteHeader`/`SiteFooter`) plus a component from `components/`. Guided-tour anchors use `data-tour`. Their copy lives in `components/guide/tour-copy.ts`.
- **Checks:** `npm test`, `npm run typecheck`, `npm run build` (all use `--webpack`). Tests are colocated `*.test.tsx` (Vitest + Testing Library, jsdom).

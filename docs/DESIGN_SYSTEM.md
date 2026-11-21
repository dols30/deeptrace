# Design system

DeepTrace should read as **professional digital-forensics / investigative software**: evidence first, calm, dense where analysts need density, explicit about uncertainty. It should not read as a generic AI SaaS marketing site.

All styling lives in `frontend/app/globals.css` (no CSS modules, Tailwind, or UI kit). Components use plain class names. Reuse classes and tokens before adding new ones.

## Two surfaces

| Surface | Where | Character today | Direction |
| --- | --- | --- | --- |
| **Public / marketing** | `/`, `/about`, `/docs` (`SiteHeader` + `SiteFooter`); `/signin` has its own split layout (`.signin-page`) | System typography, plain descriptions of actual checks, restrained borders and surfaces. `/how-it-works` and `/security` redirect home | Keep copy useful and readable. No simulated output or decorative analysis animations |
| **Workspace** | `/detector`, `/queue`, `/analyses/*`, `/reports/*`, `/audit`, `/settings`, `/admin/users`, `/account` (`DashboardShell`) | Light canvas `#f3f5f9`, white panels with 1px `#e0e5ee` borders, dark navy sidebar `#11182a`, indigo accent | This is the reference for new product UI |

## Tokens (`:root` in `globals.css`)

| Purpose | Token / value |
| --- | --- |
| Text | `--ink #242933`, `--muted #6b7280`; secondary text commonly `#667085` |
| Surfaces | `--paper`/`--surface #fff`; workspace canvas `#f3f5f9`; sidebar `#11182a` |
| Lines | `--line #e5e7eb`; workspace borders `#e0e5ee` / `#d7dce5` |
| Accent | `--accent #5865f2`, `--accent-deep #4354e8`, `--accent-soft #eef0fe`; dark accent for filters/chat `#24327a` |
| Status | `--warn #b45309`, `--danger #b91c1c` |
| Type | `--sans` Apple system font (`-apple-system` / SF Pro on Apple platforms), Segoe UI fallback; `--display` and legacy `--serif` alias it. `--mono` is system mono for IDs and timestamps. No font downloads |
| Layout | `--page 90rem`, `--narrow 48rem`, `--gutter clamp(1.25rem, 3vw, 4rem)`; root type scales from 16 to 20 CSS px with viewport width |
| Motion | `--motion-fast 160ms`, `--motion-base 280ms`, `--motion-slow 480ms`, `--ease-out cubic-bezier(.22,1,.36,1)`, `--ease-in-out cubic-bezier(.45,0,.2,1)` |

Many rules still use literal hex values. When touching a rule, prefer the token if one matches; do not add new near-duplicate colors.

## Visual principles

Prefer:

- **Evidence-first hierarchy.** Analysis opens on Officer summary: plain-language screening results, coverage gaps, media, flagged timestamps, and human assessments. Technical details contains model scores, thresholds, versions, processing notes, attribution, file hashes, and the original automated draft. Neither view may label a recording authentic or manipulated as a model determination. Media and findings lead; explanation and documentation follow (e.g. `ReportView` puts detector cards before observations, and methods inside a `<details>`).
- **One question per card.** Each detector card states its task ("Face manipulation", "AI-generated video", "Synthetic / spoofed speech"), its model score, and its threshold-validation status. Never combine detectors into one number or one gauge.
- **Restrained color.** Neutral surfaces; indigo for interaction and selection; status color only where it carries meaning.
- **Subtle borders over shadows.** 1px borders; shadows, if any, very low alpha (`#1725540c`-style).
- **Readable technical data.** Mono for hashes, IDs, timestamps (`clock()` → `mm:ss.s`), and scores shown to two decimals or as `formatModelScore` percentages.
- **Intentional density** in the workspace (findings list, timelines, attribution facts) with consistent 8–16px gaps.
- **Consistent radii:** 8–12px for controls and panels, 999px for pills/badges, 50% for dots. Avoid adding new large radii (20–30px are marketing-only).

Avoid:

- New gradients, glow, `backdrop-filter`, or glassmorphism in the workspace (the active sidebar link gradient is the existing exception; don't spread it).
- Decorative or looping animation outside explicit "analysis in progress" states.
- Generic AI-dashboard tropes: confidence gauges, "AI score" rings, "consensus" meters, sparkle icons.
- Copy that implies certainty: no "probability", "confidence", "fake", "authentic", or "verified" for model output.

The homepage uses plain descriptions of the actual checks and review workflow, with explicitly labeled illustrative detector and frame examples requested for the homepage. Its example scores are static and separate; never present them as a real analysis or animate simulated processing. Keep help tours available through Guide without opening them automatically.

Keep interface labels at least `.875rem` (14 CSS px at the minimum root size). Body text uses `1rem` or larger. Bound gutters so very wide monitors do not shrink the usable content area. Render waveforms at their displayed size and device pixel ratio, and redraw on resize and theme changes.

### Status and meaning colors

| Meaning | Current treatment |
| --- | --- |
| Detector functional | `.status.functional` — accent text on `--accent-soft` (neutral, not "good") |
| Detector error | `.status.error` — `--danger` on `#fee2e2` |
| Detector unavailable | `.status.unavailable` — `--warn` on `#ffedd5` |
| Review signals present | `.result-banner.has-signals` — amber `#d97706` / `#fff7ed` (not red: signals are not conclusions) |
| Observation severity | `.severity.low/.medium` amber, `.severity.high` danger |
| Attribution heatmap | red `rgba(196,48,43,v)` overlay, opacity controlled by the user |
| Audio occlusion | teal `#0f5c62` (score drops when masked) / amber `#8a5a12` (score rises) |
| Report section origin | `.origin-ai` purple `#5b3cc4`, `.origin-human` green `#0b6b4d` |
| Development / experimental | `.mock-banner`, `.experimental-warning` — amber notices |

Green must never signal "authentic". There is currently no green "clear" state for detectors; keep it that way unless validated thresholds exist (`operational_status`).

## Motion system

Motion communicates **progress, state change, causality, and hierarchy** — not decoration.

| Situation | Convention |
| --- | --- |
| Hover | Color/background/border change only, `--motion-fast` (buttons transition at `.15s`). No lift/scale on dense workspace items |
| Press | No custom animation; rely on focus ring and state change |
| Page / panel entrance | At most one `fx-enter`-style fade + 12px rise (`--motion-slow`, `--ease-out`). No staggered cascades in the workspace |
| Loading (data fetch) | `.empty-panel` with `.loading-orb` (`signal-pulse`) and an `aria-live` message |
| Analysis in progress | The upload scan overlay (`.scan-visual`, `.scan-beam`, `.scan-progress`) is the one place for continuous motion. Its stage text is timer-driven, not backend progress — never present it as measured progress or add fake precision |
| Success / error | Text change in an `aria-live` region or `role="alert"`; no celebratory animation |
| State transitions | Prefer `transform` and `opacity`; avoid animating layout properties |

Rules:

- `prefers-reduced-motion: reduce` is honored globally: `globals.css` disables **all** animations and transitions and smooth scrolling. Do not override this with `!important` or JS-driven animation that ignores it.
- Use the motion tokens instead of new ad-hoc durations.
- Never run more than one attention-seeking animation in the same viewport.

## Components and primitives

Reuse before creating.

**Layout:** `DashboardShell` (authenticated shell: top bar, role-filtered sidebar, `CaseChat` on `/analyses/*`), `PageFrame` (vertical stack wrapper), `SiteHeader` / `SiteFooter` (public pages), `BrandLogo`.

**Workflow:** `Screening` (upload), `ReportView` (advisory report), `AnalysisWorkspace` composed of `workspace/CaseCommand`, `MediaCanvas`, `BookmarkRail`, `FindingsInspector`, `ActivityNotes`, `ScreeningDraft`; `ReportReview`; `QueueView` / `AuditView` / `SettingsView` / `UsersView` (`workflow-home.tsx`); `SavedReports`; `ProfilePanel`.

**Shared UI:** `Terms` (glossary of Model score / Decision threshold / Estimated probability / Attribution — include it wherever scores are shown), `GuidedTour` + `GuideButton` (anchors via `data-tour="…"`, copy in `guide/tour-copy.ts`), `CaseChat`.

**CSS primitives:** `.primary-button`, `.secondary-button`, `.text-button`, `.primary-link`; `.empty-panel`, `.loading-orb`, `.route-gate`; `.section-heading`, `.card-label`, `.micro-label`, `.pane-head`; `.status.*`, `.severity.*`, `.workflow-badge`, `.result-banner`; `.form-error`; `.stack`; `.work-stat`, `.work-filters`.

Wording helpers live in code: `formatModelScore` (`lib/api.ts`), `clock`, `STATUS_LABEL`, `ROLE_LABEL`, `LIMITATION` (`lib/workflow.ts`). Use them instead of reformatting inline.

## Responsive behavior

Desktop-first `max-width` queries. Breakpoints in use:

| Width | Effect (examples) |
| --- | --- |
| 1180px | `.case-grid` collapses to one column (media above findings) |
| 980px | Marketing hero and security layouts stack; account grid 2-up |
| 900px | Public top nav hidden; work tables drop columns; review layout stacks; stats 2-up |
| 720px / 700px | Sidebar becomes a horizontal scroller without labels; work rows show 2 columns; face compare and attribution facts stack; chat panel height capped |

Use these existing breakpoints rather than introducing new ones. Grids use `minmax(0, …)` to prevent overflow from long hashes/filenames; keep `overflow-wrap: break-word` on technical values.

## Accessibility

Preserve and extend the existing patterns:

- **Focus:** global `:focus-visible` outline (2px `--accent`, 3px offset) on buttons, links, summaries, and the drop zone; textarea focus rings. Never remove outlines without a visible replacement.
- **Semantics:** real `<button>`, `<form>`, `<fieldset>/<legend>` for dispositions, `<dl>` for facts, `<details>/<summary>` for secondary info, `<nav aria-label>` in the shell, `<ol>` for findings and timelines.
- **Live regions:** `aria-live="polite"` for loading and save state; `role="alert"` for errors; `aria-busy` on the upload form.
- **ARIA:** `aria-pressed` on toggle-like chart bars, `aria-expanded` on the chat toggle, `aria-label` on icon-only controls and charts, `aria-hidden` on decorative scan visuals; `HeroSequence` exposes one `role="img"` description.
- **Keyboard:** guided tour is a `role="dialog"` dismissible with Escape; result panels receive programmatic focus (`ReportView` focuses its heading).
- **Contrast:** keep body text at `--ink`/`#667085` or darker on white. Pale grays like `#98a2b3` are for de-emphasized meta text only.
- **Reduced motion:** see Motion system.

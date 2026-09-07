# Task Plan: Knowledge Upload Mock Frontend

## Goal
Build a modular, multi-page enterprise knowledge-operations SPA under Prometheus/upload_mock where every visible action has a meaningful simulated workflow backed by shared mock state.

## Next Step
Inspect the existing job, router, store, and component contracts, then design the manual-review domain state and page integration.

## Current Phase
Phase 11

## Phases

### Phase 1: Project Discovery
- [x] Understand user intent and target directory
- [x] Determine whether an upload frontend currently exists
- [x] Trace the ingestion and release lifecycle
- [x] Extract CRM roles, terminology, constraints, and operational states
- [x] Document findings
- **Status:** complete

### Phase 2: Product & UI Design
- [x] Define target user and primary workflow
- [x] Map backend concepts to page sections and states
- [x] Choose a restrained enterprise visual system
- [x] Define interaction and responsive behavior
- **Status:** complete

### Phase 3: Implementation
- [x] Create self-contained mock frontend in Prometheus/upload_mock
- [x] Implement functional upload/configuration/review interactions
- [x] Preserve scope and avoid business backend changes
- **Status:** complete

### Phase 4: Browser Verification
- [x] Serve the mock locally
- [x] Verify primary workflow and UI states with ego-browser
- [x] Check desktop and mobile layouts via browser geometry and semantic rendering
- [x] Investigate discovered anomalies and re-test
- **Status:** complete

### Phase 5: Delivery
- [x] Explain current upload reality and design rationale
- [x] Provide local URL and file references
- [x] Report verification evidence and any mock limitations
- **Status:** complete

### Phase 6: Multi-Page Expansion Analysis
- [x] Audit the current prototype for monolithic code and placeholder interactions
- [x] Check the repository for an existing frontend framework/toolchain
- [x] Define page boundaries, shared domain state, and cross-page workflows
- [x] Select a low-dependency modular architecture
- **Status:** complete

### Phase 7: Modular Application Foundation
- [x] Convert index.html into a reusable application shell and route outlet
- [x] Add hash routing, central in-memory store, reset-on-refresh mock data, and mock API layer
- [x] Add shared components for tables, filters, badges, drawers, dialogs, forms, pagination, and toasts
- [x] Split styles into tokens, layout, components, and page modules
- **Status:** complete

### Phase 8: Business Pages
- [x] Implement Operations Overview
- [x] Implement Knowledge Sources and source onboarding
- [x] Implement Ingestion Jobs and execution/recovery details
- [x] Implement Version Releases, comparison, activation, and rollback
- [x] Implement Quality Evaluation datasets, runs, gates, and reports
- [x] Implement Permission Audit and evidence export
- [x] Implement Environment Settings and connector checks
- **Status:** complete

### Phase 9: Cross-Page Enterprise Workflows
- [x] Connect source creation to ingestion task creation
- [x] Connect successful ingestion to candidate version and quality gate
- [x] Connect passed evaluation to release activation and rollback
- [x] Record every mutating action in audit events and notifications
- [x] Add loading, empty, failure, retry, confirm, and permission-denied states
- **Status:** complete

### Phase 10: Exhaustive Browser QA
- [x] Create an inventory of every clickable and editable control
- [x] Exercise every navigation page and critical state transition with ego-browser
- [x] Verify reload persistence, reset behavior, desktop/mobile layout, and accessibility
- [x] Confirm zero placeholder-only buttons and zero runtime errors
- **Status:** complete

### Phase 11: Manual Review Workbench Design
- [x] Inspect failed-job actions, router contracts, and shared UI primitives
- [x] Define review-case data, decisions, validation, and task-state transitions
- [x] Define a dense side-by-side review layout for desktop and mobile
- **Status:** complete

### Phase 12: Manual Review Workbench Implementation
- [x] Add seeded review cases and mock API actions
- [x] Add the review route and modular page
- [x] Connect failed-job actions, completion status, audit, and retry gating
- [x] Add responsive workbench styles and reset-on-refresh behavior
- **Status:** complete

### Phase 13: Manual Review Browser QA
- [x] Exercise all three review decisions and validation states
- [x] Verify review completion unlocks checkpoint retry and produces audit evidence
- [x] Verify desktop/mobile geometry, refresh reset, and zero runtime errors
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Inspect before designing | The mock should visualize the repository's actual ingestion and release semantics. |
| Treat this as a CRM operations tool | The audience needs dense, predictable workflows rather than a marketing landing page. |
| Design the UI as a knowledge operations console | The repository models governed ingestion and safe index releases rather than generic file storage. |
| Keep the mock dependency-free | Static HTML/CSS/JS avoids changing the Python service dependency surface. |
| Use native ES modules instead of adding React/Vue/Vite | The repository has no Node build chain, while the existing Prometheus frontend already establishes an ES-module pattern; this keeps startup to a static server and avoids dependency/network risk. |
| Use a hash-router SPA | Every sidebar item gets a real URL/view without requiring server-side fallback routing. |
| Keep one normalized shared store | Sources, jobs, versions, evaluations, audits, notifications, and settings must remain consistent across pages. |
| Keep mock state in memory only | Page navigation preserves workflow state, while a browser refresh restores the full seed dataset for repeatable learning. |
| Simulate APIs asynchronously | Loading, failure, retry, optimistic restrictions, and confirmation states require Promise-based mock service behavior rather than direct DOM mutation. |
| Keep manual review under Ingestion Jobs | Review is remediation for a specific blocked run, not an independent top-level navigation domain. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Planning patch context mismatch | Re-read the active planning files and applied a smaller patch against the current content. |
| First local server start was sandbox-blocked | Requested scoped approval and restarted the static server. |
| First ego-browser navigation reached an internal auth page and screenshot timed out | Verified task-space isolation; will confirm the server is responsive and navigate the existing task space to localhost explicitly. |
| ego-browser screenshot timed out three times, including direct CDP | Stopped repeating the failing action; switched to semantic interaction plus DOM geometry/overflow validation. |
| Mobile sidebar appeared offscreen immediately after open | Confirmed CSS rule match; waiting for browser animation frames produced transform 0 and x=0, so no product defect existed. |
| zsh rejected an unmatched `vite.config.*` probe | Replaced the shell glob with quoted exact-name `find` predicates; confirmed no frontend package/build configuration exists. |
| Two malformed `functions.exec` orchestration snippets failed before tool execution | Stopped using the faulty wrapper and ran one ordinary read-only command; no files or processes were affected. |
| Browser remained on the boot screen although ES modules loaded | The app subscribed to store updates but not route updates; registered `subscribeRoute` before `startRouter` so the initial route renders. |
| A deep-linked job drawer reopened after every store update and intercepted row actions | Added one-time query consumption guards for job, version, and quality deep links. |
| Filter typing was interrupted and a reopened popover immediately closed | Debounced search-driven rerenders and centralized popover dismiss-listener cleanup. |
| Mobile sidebar transition stayed at its offscreen interpolation value in the isolated background browser | Removed the non-essential transform transition so open/close state is deterministic for browser automation and reduced-motion environments. |
| Final asset probe used zsh's special `path` variable and temporarily hid `curl` inside that subprocess | Renamed the loop variable to `asset`; no project files or running services were affected. |

# Task Plan: RAG Enterprise Evaluation Asset V1

## Goal
Replace the five-case placeholder with a compact but complete, high-fidelity fictional advertising-CRM evaluation asset and a deterministic offline regression workflow.

## Next Step
Learner roadmap delivered; begin with Stage 1 when the user is ready.

## Current Phase
Phase 1

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Audit the current dataset, schema, metrics, tests, corpus, and documentation claims
- [x] Document constraints and gaps in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define the fictional advertising-CRM knowledge snapshot and source IDs
- [x] Define the rich case/prediction contracts and evaluation slices
- [x] Fix the acceptance criteria and file structure
- **Status:** complete

### Phase 3: Implementation
- [x] Replace the five-case dataset with the versioned golden set
- [x] Add evidence corpus, dataset card, annotation guide, split manifest, and examples
- [x] Upgrade schema, metrics, runner, release gate, CLI, README, and project evaluation docs
- [x] Add schema, metrics, runner, and asset-consistency tests
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Run focused evaluation tests and full unit suite
- [x] Verify counts, coverage, source references, version/ACL constraints, and no PII-like values
- [x] Generate and inspect a sample regression report
- [x] Document measured results
- **Status:** complete

### Phase 5: Delivery
- [x] Review final diff without disturbing unrelated changes
- [x] Explain what is simulated, how to use it, and what is not yet a model-quality result
- **Status:** complete

### Phase 6: Learner Roadmap
- [x] Add an ordered evaluation learning roadmap under `evaluation/学习/`
- [x] Map every evaluation artifact to learning goals, exercises, and interview questions
- [x] Verify links and Markdown structure
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Build one coherent fictional business snapshot instead of unrelated questions | High fidelity comes from consistent roles, policies, versions, states, and evidence, not brand names |
| Keep all identities and business records explicitly fictional | Educational realism must not be misrepresented as private Baidu information |
| Use a compact 64-case V1 across eight primary categories | Eight cases per category is inspectable while still exercising every major failure mode |
| Separate dataset labels from system predictions | Prevents labels leaking into runtime and supports repeatable offline regression |
| Gate on deterministic metrics; keep model judging optional | CI must run without an external LLM or production service |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Existing README says a runner "should" exist, but none exists | Implement a real prediction-to-report runner and test it |

# Task Plan: Auth.py Learning Walkthrough

## Goal
Explain rag_service/auth.py to a beginner line by line, while connecting every abstraction to its callers, configuration, tests, and role in the RAG request lifecycle.

## Next Step
Trace imports, constructors, method calls, configuration, and tests related to auth.py.

## Current Phase
Phase 1

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Read auth.py in full
- [x] Identify its two authorization paths
- [x] Document initial findings
- **Status:** in_progress

### Phase 2: Call-Graph Reconstruction
- [ ] Find imports and constructors of auth classes
- [ ] Find verify/resolve call sites
- [ ] Inspect related configuration and request handlers
- [ ] Inspect focused tests for intended behavior
- **Status:** pending

### Phase 3: Teaching Structure
- [ ] Order methods by learning dependency rather than source order
- [ ] Build a request-flow mental model
- [ ] Prepare line-by-line explanation with concrete examples
- **Status:** pending

### Phase 4: Accuracy Verification
- [ ] Cross-check explanations against tests and runtime wiring
- [ ] Confirm line references and distinguish facts from inference
- **Status:** pending

### Phase 5: Delivery
- [ ] Present roadmap first
- [ ] Explain code progressively and line by line
- [ ] Give exercises and next project-reading step
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Teach data/contracts before implementations | Beginners need to know what flows through the module before learning validation details. |
| Separate normal authentication from recovery re-authorization | They serve different lifecycle stages and have different failure semantics. |

## Errors Encountered
| Error | Resolution |
|-------|------------|

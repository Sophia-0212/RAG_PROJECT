# Progress Log

## Session: 2026-09-05

### Current Status
- **Phase:** 3 - Implementation
- **Started:** 2026-09-05

### Actions Taken
- Initialized an isolated implementation plan after the earlier learning-document plan completed.
- Audited the current evaluation files, tests, README, release gate, and demo knowledge documents.
- Confirmed the core gap: five placeholder cases and metric helpers exist, but there is no coherent evidence corpus or executable quality-regression runner.
- Fixed the V1 target at 64 cases across eight primary categories, with explicit fictional-data provenance and deterministic offline scoring.
- Defined three splits: 16 visible development cases, 40 locked regression cases, and 8 security challenge cases.
- Defined the machine contract around identity, as-of time, expected action/route, versioned evidence references, fact anchors, forbidden evidence/facts, and annotation provenance.
- Chose a frozen evaluation corpus separate from the evolving demo ingestion corpus so labels remain reproducible.
- Replaced the five-case smoke file with 64 adjudicated high-fidelity cases: eight cases in each of eight primary categories.
- Verified the intended split distribution: development 16, locked 40, security 8; actions: answer 44, refuse 16, clarify 4.
- Added a 14-document frozen corpus with active, retired, restricted, and quarantined sources; all 37 dataset evidence references resolve to the manifest.
- Upgraded the evaluation schema and deterministic metric primitives and added a prediction scoring runner.
- Added an asset validator that checks corpus files, evidence references, effective-time windows, answer-side ACLs, governed splits, and adjudication status.
- The validator exposed two realistic least-privilege gaps; added a contract-status view for operations and granted finance access only to non-restricted field/tier definitions needed for settlement work.
- Completed asset validation after resolving a prompt-injection case that incorrectly depended on a commercial document outside the operator's ACL.
- Added offline regression CLI, a 14-rule release gate, package data, and 16 focused tests; all focused tests pass.
- Audited documentation and found stale claims that the repository has only five cases as well as simulated 2,400-case results that must be distinguished from the implemented V1 evidence.
- Measured the released label density: 91 required facts, 58 relevant evidence references, and 24 forbidden evidence references; 48 SME-synthetic and 16 adversarial cases.
- Captured SHA-256 identities for the dataset and corpus manifest for the governed release manifest.
- Added Dataset Card, annotation guide, prediction contract, changelog, and six worked CRM evaluation examples.
- Updated README and simulated-project evaluation docs so the 64-case implemented asset is not confused with the planned 2,400-case narrative.
- Added clarification-content and refusal-reason scoring plus dedicated ACL, prompt-injection, and temporal-version hard gates.
- Full `.venv` unit suite: 141 passed, 10 external-state integration tests skipped by configuration.
- Focused evaluation suite after final asset checks: 18 passed.
- End-to-end CLI smoke over 64 temporary oracle predictions produced all governed slices and passed all 19 gates; this validates the evaluator only, not model quality.
- `git diff --check` passed and stale references to the removed five-case dataset remain only in the changelog.
- Final compile, release fingerprint, and diff sanity checks passed. Implementation is ready for handoff.

## Session: Evaluation Learning Roadmap

### Current Status
- **Phase:** 6 - Learner Roadmap

### Actions Taken
- Restored the completed evaluation-asset plan and inventoried the current `evaluation/学习/` materials.
- Chose a `00_` roadmap index so the existing theory and worked-example documents remain the detailed chapters.
- Added `evaluation/学习/00_企业级RAG评测集学习路线图.md` with the end-to-end mental model, directory map, ten learning stages, creation and annotation workflows, exercises, interview checks, and a fourteen-day schedule.
- Verified the 364-line Markdown file, required learning topics, and heading structure.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
| Initial patch expected the wrong generated template headings | Read the generated files and patched against their actual structure |

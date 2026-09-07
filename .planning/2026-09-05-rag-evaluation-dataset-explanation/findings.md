# Findings & Decisions

## Requirements
- Inspect `Prometheus/` and `test/` in the mock enterprise project.
- Explain what a RAG evaluation dataset is and why it exists.
- Use the STAR method, stay close to CRM/RAG work, and do not create the mock dataset yet.

## Research Findings
- `evaluation/datasets/crm_smoke_v1.jsonl` exists and contains 5 cases: four ordinary CRM knowledge questions and one sensitive password-export refusal case. The repository therefore has a smoke dataset, but not the simulated 2,400-case enterprise Golden Set.
- `evaluation/schema.py` defines the current ground-truth fields: case/version/question, expected and forbidden source IDs, expected facts, expected route, refusal flag, and tags.
- `test/008_7. 模拟评测体系.md` describes a target 2,400-case Golden Set split into eight buckets, with 600 development cases and 1,800 locked test cases. All numbers are explicitly simulated.
- `Prometheus/task/04-评测体系.md` gives three realistic evaluation-work demands: add coverage before a new CRM scenario launches, audit annotator agreement, and run weekly regression after knowledge updates.
- `test/002_1` establishes the mock scale: 4,600 RAG queries/day, 126,400 source documents, 1.86M chunks, 190 DAU, and 9 peak QPS. It explicitly says all reported outcomes are simulated.
- `test/010_9` contains online SLO/telemetry, not an offline evaluation dataset. Prometheus answers operational questions such as latency, availability, backlog, and failures; an evaluation set answers semantic correctness, retrieval quality, groundedness, refusal, and security questions.
- Implemented metrics are currently `recall_at_k`, hit rate, reciprocal rank, citation precision/recall, and ACL leakage rate. The release gate expects recall@5 >= 0.80, MRR >= 0.60, citation precision >= 0.90, citation recall >= 0.80, refusal accuracy = 1.00, and ACL leakage = 0.
- The existing unit tests validate metric mathematics and schema constraints; they do not execute the actual RAG service against the five cases and aggregate a report.
- Prometheus mock scenarios model online runtime behavior: normal load, LLM latency jitter, and LLM outage/circuit breaker behavior. They do not provide questions, expected documents, expected facts, or semantic labels.
- A real evaluation program has at least three distinct evidence layers: versioned offline Golden Set, production monitoring/A-B metrics, and state/fault-injection tests. The simulation docs already describe all three, but only a tiny smoke set and foundational evaluation utilities are implemented for the semantic layer.
- README explicitly says "An evaluation runner should write" the metrics JSON. No semantic runner script/entrypoint exists in `pyproject.toml`; only the gate CLI exists. This confirms a major implementation gap: the project can load cases and calculate individual metrics, but cannot yet execute the RAG system over the dataset and produce the release report.
- CI runs schema/metric/gate unit tests but does not run the CRM smoke cases through the RAG pipeline, so the current release gate is not yet an actual model/retrieval quality gate.
- The five smoke questions do point at real mock knowledge files under `datas/md`, making them usable seeds rather than placeholder-only rows.
- Prometheus dashboard explicitly labels itself simulated and exposes runtime dimensions such as QPS, success rate, in-flight work, latency distribution, rejection reasons, duplicate submissions, and recovery outcomes. A semantically wrong but HTTP-successful answer can look healthy on all of those charts.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Build one versioned asset manifest around cases, corpus/index snapshot, annotation guideline, splits, and evaluator versions | These jointly determine reproducibility |
| Preserve the documented eight scenario buckets and 600/1,800 grouped split as the target mock baseline | It matches the existing project narrative while preventing source/template leakage |
| Require hard gates for ACL leakage, high-risk refusal, and effective-version correctness | Aggregate quality averages can hide catastrophic CRM/security failures |
| Run PR smoke, nightly targeted, weekly full, and pre-release candidate-vs-baseline evaluation | Balances feedback speed, model cost, and regression confidence |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-

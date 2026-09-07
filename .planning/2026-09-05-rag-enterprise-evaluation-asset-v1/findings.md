# Findings & Decisions

## Requirements
- Delete the existing unprofessional evaluation set and replace it with a small, complete, enterprise-style asset.
- Make the fictional advertising-CRM business cases as realistic and internally consistent as possible.
- Include concrete business examples that build intuition.

## Research Findings
- `evaluation/datasets/crm_smoke_v1.jsonl` contains only five shallow cases.
- The schema lacks identity, ACL, effective time, source version, graded relevance, history, ambiguity labels, provenance, and split governance.
- Metric helpers exist, but there is no runner that turns per-case predictions into an auditable report.
- The release gate therefore depends on metrics manufactured outside the repository.
- The three `datas/md` documents cannot support meaningful version, permission, multi-hop, ambiguity, or injection evaluation.
- `test/008_7. 模拟评测体系.md` describes a 2,400-case target, but repository evidence currently supports only five cases.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Freeze a separate evaluation corpus | Makes evidence and labels reproducible even when demo ingestion documents evolve |
| Cover eight primary categories and eight business domains | Prevents a good average from hiding a failed risk slice |
| Use visible development, locked regression, and security challenge splits | Supports tuning without contaminating final acceptance cases |
| Require source/version/section provenance on every expected fact | Makes adjudication reproducible and catches obsolete-policy answers |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| The user requests realism close to an internal Baidu CRM system, but no private materials were provided | Create a coherent fictional large-advertiser CRM world and label it clearly; do not present invented facts as Baidu internals |

## Resources
- `evaluation/学习/01_企业级评测数据资产与标注方法.md`
- `test/008_7. 模拟评测体系.md`
- `Prometheus/task/04-评测体系.md`
- Current `evaluation/` code and `datas/md/` demo corpus

## Learning Roadmap Decision

- Teach from business truth to code execution: purpose -> corpus -> case labels -> annotation -> schema -> metrics -> runner -> gate -> interview narrative.
- Keep quality evaluation separate from latency, capacity, and state-backend load testing.
- Every learning phase must end with a concrete artifact-reading exercise and an interview-ready explanation.

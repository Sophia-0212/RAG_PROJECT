# Findings & Decisions

## Source Requirements

- The tool is used by retrieval engineers to reproduce a reported query and inspect intermediate retrieval results.
- The minimum useful stages are Dense/Milvus recall, BM25 recall, RRF fusion, and CrossEncoder reranking.
- Each stage needs ranked candidates and stage-specific scores so engineers can locate whether recall, fusion, or reranking caused the failure.
- Representative source-card cases cover lexical false positives, ambiguous short queries/query rewriting, long-tail reranker weakness, business-line prefiltering, and unstable sparse-recall degradation.

## UX Decisions

- The first viewport should be the actual diagnostic workbench, not a landing page.
- Left rail: incident presets and runtime context.
- Main area: query editor, controls, diagnostics summary, and four-stage candidate lists.
- Detail rail: selected candidate excerpt, score/rank movement, matched terms, tenant/ACL/version metadata, and an engineering conclusion.
- Mock runs should be deterministic, reversible, and visibly labeled as simulations.

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-

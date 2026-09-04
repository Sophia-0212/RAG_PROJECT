# Findings

## Initial State
- Repository path: `/Users/lixiaofei05/Desktop/workspace/RAG企业知识库项目/RAG_PROJECT`
- Git branch: `main`, tracking `origin/main`.
- Worktree is dirty. Existing modified/added/deleted files must be preserved.
- Visible top-level areas include `agent`, `documents`, `graph`, `graph2`, `llm_models`, `tools`, `utils`, `langfuse`, `docs`, `datas`, `test`, `.milvus`, and `.venv`.

## Repository Index
- Primary language: Python.
- No `README`, `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`, or Poetry lockfile was found in the repository root.
- No `AGENTS.md` exists in the repository or its immediate parent tree.
- `main.py` is the apparent root entrypoint.
- Core packages/files:
  - `agent/rag_agent.py`: agent-oriented RAG implementation.
  - `documents/`: Markdown parsing, Milvus access, and ingestion.
  - `graph/`: first graph workflow and its nodes/state.
  - `graph2/`: second, more decomposed graph workflow with routing, retrieval, grading, query transformation, web search, and answer generation.
  - `llm_models/`: chat-model and embedding-model construction.
  - `tools/`: retriever and reranker helpers.
  - `utils/`: environment, logging, and printing helpers.
  - `langfuse/docker-compose.yml`: local observability stack configuration.
  - `test/recall_eval/`: retrieval/generation evaluation scripts, fixtures, and result JSON files.
- Data/assets:
  - `datas/md/` contains three CRM knowledge-base Markdown documents.
  - `datas/layout-parser-paper.pdf` is a sample/source PDF.
  - `test/recall_eval/测试文档集12篇/` contains a 12-document Chinese CRM evaluation corpus.
  - Graph diagrams are stored as PNG files.
- Local/runtime directories include `.venv`, `.milvus`, `logs`, and Python cache directories.
- A `.env` file exists; only variable names will be inspected, never secret values.

## Architecture
- `CLAUDE.md` documents the intended architecture: environment/model setup -> Markdown parsing -> Milvus storage/ingestion -> retrieval tools -> agent and two independent LangGraph pipelines.
- The architecture document may lag the staged worktree changes. Actual source is authoritative.
- `main.py` is still the default PyCharm sample and is not an application entrypoint in practice.
- Declared runtime integrations inferred from imports:
  - LangChain core/community/openai/experimental and LangGraph.
  - Milvus through `langchain_milvus` and `pymilvus`.
  - Local Hugging Face embeddings and `sentence_transformers.CrossEncoder` reranking.
  - Langfuse tracing, Tavily web search, Loguru logging, python-dotenv, Unstructured Markdown parsing, and Pydantic.
- `.env` defines names for OpenAI, DeepSeek, Tavily, Langfuse, and Hugging Face endpoint configuration. Secret values were not recorded.
- `.gitignore` excludes `.env`, Langfuse local environment/volumes, `.venv`, `.milvus`, caches, IDE files, and logs.
- Existing worktree layers:
  - Staged: agent/parser/Milvus changes, Graph 1 and Graph 2 changes, a new direct-answer node, reranking implementation, and rerank evaluation artifacts.
  - Unstaged: deletion of seven Markdown reports/notes under `test/`.
- Actual configuration/model layer:
  - `utils/env_utils.py` loads `.env` with override enabled, forces `HF_HUB_OFFLINE=1` unless already set, maps `LANGFUSE_BASE_URL` to `LANGFUSE_HOST`, defaults Milvus to `http://127.0.0.1:19530`, and hardcodes collection `t_collection01`.
  - `llm_models/all_llm.py` constructs a zero-temperature `ChatOpenAI` client for model `gpt-5.5` through the internal `oneapi-comate.baidu-int.com` gateway; Tavily returns at most two results.
  - `openai_embedding` calls Baidu Qianfan's OpenAI-compatible endpoint using model name `bge-large-zh` and is used only for semantic chunking.
  - `bge_embedding` is local `BAAI/bge-small-zh-v1.5`, CPU, normalized, and supplies 512-dimensional dense Milvus vectors.
- Document ingestion:
  - Unstructured parses Markdown as elements with the fast strategy.
  - Title elements are accumulated with descendants; metadata category is normalized to `content`; merged blocks over 5,000 characters are split with `SemanticChunker`.
  - `documents/write_milvus.py` uses a parser process and a writer process joined by a bounded queue. Its source directory is now repository-relative `datas/md`.
  - Running the ingestion script calls `create_collection()` first. That method releases/drops any existing `t_collection01`, creates a schema, BM25 sparse function/index, and HNSW/IP dense index, then the writer connects and inserts batches.
- Retrieval/reranking:
  - `tools/retriever_tools.py` connects to Milvus at import time and builds a hybrid similarity retriever with RRF, `k=16`, score threshold `0.1`, and `category=content` filtering.
  - `tools/reranker_tools.py` loads `BAAI/bge-reranker-base` through `CrossEncoder` at import time, scores query/document pairs, and returns the top 4 by default.
  - The retriever tool is described for CRM knowledge covering SOP, product functions, troubleshooting, and objection handling.
- Agent path:
  - `agent/rag_agent.py` builds a tool-calling agent with in-memory history keyed by `session_id` and Langfuse callback metadata.
  - The module still executes a real demo query and prints its answer at import time.
- Graph 1 (`graph/`) current flow:
  - State is an append-only `messages` list using LangGraph's `add_messages` reducer.
  - `START -> agent`; the LLM decides whether to call the CRM retriever. No tool call ends immediately.
  - Tool calls go to `retrieve`; the returned artifact supplies original `Document` objects.
  - Retrieved candidates are reranked to top 4, then each document receives an LLM yes/no relevance grade.
  - Any surviving documents are joined into tool-message content and sent to `generate`; otherwise `rewrite -> agent` repeats without a retry limit.
  - `MemorySaver` plus one UUID `thread_id` supports a multi-turn CLI loop; Langfuse tags the session as `graph1`.
- Graph 2 (`graph2/`) current flow:
  - State fields are `question`, `transform_count`, `hallucination_count`, `generation`, and `documents`; it is compiled without a checkpointer.
  - The start router emits one of `vectorstore`, `web_search`, or new `direct_answer` based on CRM scope and whether external information is required.
  - `direct_answer` answers greetings/small talk and ends without retrieval or generation grading.
  - Vectorstore retrieval performs RRF hybrid recall of 16, CrossEncoder reranking to 4, and per-document LLM relevance filtering.
  - If no documents remain, query transformation/retrieval repeats while `transform_count < 2`; after that it falls back to web search.
  - Web search returns at most two Tavily results and then uses the shared RAG generation node.
  - Generated answers are graded first for grounding, then usefulness. Grounding failures retry generation subject to `MAX_HALLUCINATION_RETRIES=2`; exhaustion and non-useful answers route through query transformation and retrieval.
  - The CLI creates a fresh Langfuse session per question and tags it `graph2`; unlike Graph 1 it has no conversational memory.
- Graph 2 generation details:
  - Web search concatenates result `content` fields into one `Document` and reuses the same RAG answer/grading path.
  - Direct-answer routing bypasses retrieval, grounding checks, and usefulness checks.
  - Each call to the shared generation node increments `hallucination_count`; the grounding decision compares the persisted count against 2.
  - Hallucination grading receives the `documents` object(s) and generated text; answer grading receives question and generated text.
- Current staged feature direction is CRM-focused, replacing earlier semiconductor/chip routing text.

## Runtime And Tests
- Dependency metadata is not committed in a conventional package manifest, so imports and the existing virtual environment must be used to reconstruct dependencies.
- The project description warns about import-time external calls/connections in some modules; static reading is preferred during indexing.
- `main.py` only prints a sample greeting and does not launch either RAG flow.
- Operational entry scripts currently are module `__main__` blocks, notably `documents/markdown_parser.py`, `documents/milvus_db.py`, `documents/write_milvus.py`, `graph/graph1.py`, and `graph2/graph_2.py`.
- Importing graph/agent modules may trigger Milvus connection, local embedding/reranker model loading, or real LLM calls; indexing remains static/read-only.
- `graph/graph1.py` and `graph2/graph_2.py` both contain unguarded top-level CLI loops, so importing either module blocks for terminal input.
- Existing virtual environment:
  - Python 3.11.15.
  - Key installed versions include LangChain 1.3.17, LangGraph 1.2.11, Langfuse 3.15.0, langchain-milvus 0.4.0, PyMilvus 3.0.1, OpenAI 3.3.1, sentence-transformers 6.0.0, Transformers 5.15.1, Torch 2.13.0, Unstructured 0.27.1, and Pydantic 2.13.4.
  - The environment is locally reconstructable only from `pip list`; the project does not currently pin it in source control.
- Langfuse local deployment:
  - `langfuse/docker-compose.yml` defines Langfuse web/worker plus Postgres, ClickHouse, Redis, and MinIO.
  - Langfuse web maps host port 3001 to container port 3000, matching the application default `LANGFUSE_BASE_URL`.
  - Compose defaults include placeholder/development credentials marked `CHANGEME`; deployment requires environment hardening outside local development.
- Evaluation suite (`test/recall_eval/`):
  - This is script-driven integration/evaluation code, not a pytest unit-test suite.
  - `build_test_collection.py` destructively rebuilds the isolated `interview_recall_test` collection from 12 CRM Markdown fixtures, retaining only `category=content` chunks. It does not touch production collection `t_collection01`.
  - The original evaluation uses 24 questions; V2 and rerank evaluations use 40 questions across factual, multi-hop, negation, and colloquial categories.
  - `run_recall_eval_v2.py` measures partial/full recall, MRR, NDCG, redundancy, and Graph1/Graph2 LLM-filter precision.
  - `run_generation_eval.py` reuses saved filtered chunks and LLM-grades correctness, faithfulness, and question relevance against reference answers.
  - New `run_rerank_eval.py` isolates retrieval-layer effects by comparing RRF top 4 against RRF top 16 plus CrossEncoder top 4, without LLM filtering.
  - V2 question distribution is 24 factual, 4 multi-hop, 9 negation, and 3 colloquial; only one question has multiple ground-truth source documents.
- Knowledge-domain map:
  - Production sample documents cover CRM lead/opportunity/customer/integration features, sales SOP and objections, team funnel reporting, renewal/churn, and troubleshooting for accounts, ERP synchronization, notifications, dashboards, and approvals.
  - The 12-document evaluation corpus broadens this to price/feature/service/contract objections, customer success/renewal, reporting/permissions, integration/security, login/SSO, import/export/sync, mobile/performance, and team KPI processes.
- Saved experiment summaries:
  - Initial 24-question run: both graphs recall 1.0; Graph1 precision 0.4479 vs Graph2 0.6771.
  - V2 40-question run: retrieval/Graph1/Graph2 full recall 1.0; Graph1 precision 0.4938 vs Graph2 0.7479.
  - Generation run: Graph1/Graph2 correctness 0.9858/0.9828, faithfulness 0.9797/0.9797, relevance 0.9635/0.9493.
  - New rerank run: partial/full recall remain 1.0; MRR improves 0.9458 -> 0.9875, reported NDCG 1.4619 -> 1.5111, precision 0.4938 -> 0.5; elapsed 36.8 seconds.
- Interpretation caveat: prior Graph1/Graph2 evaluation artifacts predate the staged changes that add per-document filtering and reranking to Graph1/Graph2, so they are historical baselines rather than current-code validation.
- Metric caveat: saved NDCG values exceed 1.0. The implementation awards relevance to every returned chunk from a ground-truth source, while ideal DCG is capped by the number of unique ground-truth source files; duplicate relevant chunks can therefore make DCG exceed IDCG. Treat these NDCG values as implementation-specific and not standard normalized DCG.
- Repository history is short and focused: initial baseline, local Milvus/Qianfan adaptation, CRM/DUCC migration, then CRM evaluation additions. Current staged work is the next reranking/routing iteration.

## Quick Navigation
- Environment, endpoints, collection name: `utils/env_utils.py`
- Chat model and Tavily: `llm_models/all_llm.py`
- Chunking and retrieval embeddings: `llm_models/embeddings_model.py`
- Markdown parse/merge/chunk behavior: `documents/markdown_parser.py`
- Milvus schema, BM25 analyzer, indexes, connection: `documents/milvus_db.py`
- Destructive collection rebuild and multiprocessing ingestion: `documents/write_milvus.py`
- Hybrid retriever parameters/tool wrapper: `tools/retriever_tools.py`
- CrossEncoder scoring/top-N: `tools/reranker_tools.py`
- Tool-calling agent and session history: `agent/rag_agent.py`
- Graph 1 orchestration/relevance gate/CLI: `graph/graph1.py`
- Graph 2 orchestration/routing/retry policy/CLI: `graph2/graph_2.py`
- Graph 2 node/chain details: remaining files under `graph2/`
- Evaluation methodology and current rerank comparison: `test/recall_eval/*.py` and result JSON files
- Conceptual/interview documentation: `docs/interview_prep.md` and `test/langgraph/langgraph核心概念笔记.md`

## Debugging Hotspots
- Destructive operations: production/test collection builders drop existing collections before recreation.
- Import side effects: eager Milvus connection and model loading; `rag_agent.py` executes an external query; graph modules enter CLI loops.
- Loop bounds: Graph 1 rewrite has no cap. Graph 2 caps immediate grounding retries, but usefulness/transform/retrieve cycles can still continue without a global step limit, and counters persist through partial state updates.
- Performance: relevance grading is synchronous and sequential per document after reranking.
- State/persistence: agent history is in-process only; Graph 1 memory is in-process; Graph 2 has no checkpointer.
- Reproducibility: no committed dependency lock/manifest and evaluations depend on Milvus plus external LLM/embedding services.
- Documentation drift: `CLAUDE.md` and `docs/interview_prep.md` describe older model, endpoint, source path, and top-k/filter behavior in places.
- Evaluation interpretation: historical graph metrics are stale for the staged implementation; NDCG calculation is not conventionally normalized when several chunks map to one relevant source.

## Validation Performed
- Read-only AST parsing succeeded for all 46 Python files with zero syntax errors.
- No integration test was run because doing so would require local Milvus/model availability and external API calls, and some setup scripts rebuild collections destructively.

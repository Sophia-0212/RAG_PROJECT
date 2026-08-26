# RAG_PROJECT — 企业知识库 RAG 系统

LangChain/LangGraph 实现的检索增强生成系统，聚焦半导体/芯片领域知识库。Milvus 混合检索（dense + sparse BM25）。

## 架构分层

```
utils/env_utils.py (配置)
  → llm_models/all_llm.py (LLM), llm_models/embeddings_model.py (Embedding x2)
  → documents/markdown_parser.py (解析+切块)
  → documents/milvus_db.py (schema + 存储)
  → documents/write_milvus.py (批量入库脚本)
  → tools/retriever_tools.py (检索工具封装)
  → agent/rag_agent.py (带历史的 tool-calling agent)
  → graph/、graph2/ (两条独立 LangGraph pipeline)
```

### utils/
- `env_utils.py` — `.env` 加载，`OPENAI_API_KEY`/`DEEPSEEK_API_KEY`。`MILVUS_URI`（硬编码 `http://1.95.116.112:19530`）、`COLLECTION_NAME`（硬编码 `t_collection01`）不走环境变量。
- `log_utils.py` — `log`，loguru 单例，全局共用。
- `print_utils.py` — `_print_event`，pretty-print LangGraph 事件流；当前**未被任何 graph 调用**。

### llm_models/
- `all_llm.py` — `llm = ChatOpenAI(model='gpt-4o-mini', base_url="https://xiaoai.plus/v1")`（走代理）；`web_search_tool = TavilySearchResults(max_results=2)`。DeepSeek 备选方案注释保留未启用。
- `embeddings_model.py` — `openai_embedding`（语义切块用，OpenAI 代理）、`bge_embedding`（Milvus 存储用，本地 `BAAI/bge-small-zh-v1.5`，CPU）。两者**不是同一个**，别混用。

### documents/
- `markdown_parser.py` — `MarkdownParser`。`parse_markdown_to_documents()`：`UnstructuredMarkdownLoader(mode='elements')` 解析 → `merge_title_content()` 按标题层级合并父子内容块 → `text_chunker()` 对 >5000 字符的合并块用 `SemanticChunker` 二次语义切分。
- `milvus_db.py` — `MilvusVectorSave`。Schema 含 `dense`（FLOAT_VECTOR dim=512）+ `sparse`（SPARSE_FLOAT_VECTOR，BM25 Function 从 `text` 生成，jieba 分词），索引 `SPARSE_INVERTED_INDEX`（BM25/DAAT_MAXSCORE）+ `HNSW`（IP）。`create_collection()` 若已存在同名 collection 会**先 drop 再重建**（有损）。
- `write_milvus.py` — 双进程管道：`file_parser_process`（解析 md 目录，20 条/批入队）+ `milvus_writer_process`（出队写 Milvus）。`__main__` 里 `md_dir` 是**硬编码 Windows 路径**，当前跑不了，需改成本机路径才能用。

### tools/
- `retriever_tools.py` — 模块级 `mv = MilvusVectorSave(); mv.create_connection()`，**import 即连接 Milvus**。`retriever_tool` 限定 `filter={"category": "content"}`，rrf ranker，k=4。

### agent/
- `rag_agent.py` — `create_tool_calling_agent` + `RunnableWithMessageHistory`（session_id 维度内存历史）。⚠️ 模块顶层有硬编码 demo query（`'什么是EUV光刻机？'`），**import 该文件即会真实调用一次 LLM**。

## 两条 Graph Pipeline（相互独立，未共享代码）

### graph/（graph1.py）— 简单 agentic RAG
State: `AgentState{messages}`（消息列表，`MemorySaver` 支持多轮，CLI 用 `thread_id`）。

流程：`agent` → (`tools_condition`) → 有工具调用则 `retrieve`，否则直接 `END`
→ `retrieve` → (`grade_documents` 本地条件边) → `generate`（相关）/ `rewrite`（不相关）
→ `rewrite` → 回 `agent`（重试，**无次数上限**）
→ `generate` → `END`

### graph2/（graph_2.py）— Self-RAG（更复杂，带路由/纠错）
State: `GraphState{question, transform_count, generation, documents}`（无 checkpointer，单轮）。

流程：`START` → (`route_question`) → `web_search` 或 `retrieve`
→ `web_search` → 直接 `generate`（跳过 grading）
→ `retrieve` → `grade_documents` → (`decide_to_generate`)：
  - 有文档 → `generate`
  - 无文档 & `transform_count < 2` → `transform_query` → 回 `retrieve`
  - 无文档 & `transform_count >= 2` → 升级 `web_search`
→ `generate` → (`grade_generation_v_documents_and_question`)：
  - hallucination 检测不过 → **退回 `generate` 自身（⚠️ 无重试上限，有死循环风险）**
  - 通过但答案不切题（`not useful`）→ `transform_query` → 回 `retrieve`
  - 通过且切题（`useful`）→ `END`

## 已知问题（未修复，仅记录）

- `main.py` 是 PyCharm 占位模板，未接入实际流程
- `agent/rag_agent.py` import 时有副作用（真实 LLM 调用），引入时需注意
- `write_milvus.py` 的 `md_dir` 硬编码 Windows 路径，本机不可直接运行
- `print_utils.py`、`draw_png.py` 未被 graph1/graph2 实际调用，是孤立的调试工具
- graph1 与 graph2 各自独立实现（各自的 llm 调用、grading chain），无共享抽象，重复度高
- `milvus_db.py` `create_collection()` 对已存在同名 collection 会先 drop 再重建，调用前确认不是生产 collection

## 数据目录

- `datas/md/*.md` — 源知识文档（faq/tech report/troubleshooting 等）
- `datas/output/*.json` — 解析中间产物（按文件编号命名，如 `10_100.json`）
- `datas/layout-parser-paper.pdf` — 原始 PDF 样例

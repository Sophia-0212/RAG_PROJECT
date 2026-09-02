# RAG_PROJECT 面试复习笔记

对应简历项目：CRM智能助手企业级RAG检索增强引擎。技术栈 Python / LangChain / LangGraph / Milvus / BGE Embedding / BM25 / Loguru / multiprocessing。

---

## 目录

1. [整体架构](#1-整体架构)
2. [文档解析与切块流水线](#2-文档解析与切块流水线)
3. [Milvus 混合检索方案（Dense+Sparse+RRF）](#3-milvus-混合检索方案densesparsErrf)
4. [双进程批量入库流水线](#4-双进程批量入库流水线)
5. [检索工具封装 + Agent 多轮对话](#5-检索工具封装--agent-多轮对话)
6. [Graph1：简单工具调用型 RAG](#6-graph1简单工具调用型-rag)
7. [Graph2：Self-RAG 自纠错流程](#7-graph2self-rag-自纠错流程)
8. [已知问题（面试可能被追问的坑）](#8-已知问题面试可能被追问的坑)
9. [高频面试问答（QA）](#9-高频面试问答qa)

---

## 1. 整体架构

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

**分层职责**：

| 层 | 文件 | 职责 |
|---|---|---|
| 配置层 | `utils/env_utils.py` | `.env` 加载，API Key、Milvus 连接串、collection 名 |
| 模型层 | `llm_models/all_llm.py`、`embeddings_model.py` | LLM 实例、两套 Embedding（语义切块用 / 存储检索用）、web 搜索工具 |
| 数据处理层 | `documents/markdown_parser.py` | Markdown 解析 → 标题层级合并 → 语义二次切块 |
| 存储层 | `documents/milvus_db.py` | Milvus schema 定义（dense+sparse 双字段）、连接、写入 |
| 批处理层 | `documents/write_milvus.py` | 双进程管道，批量增量写入 |
| 工具层 | `tools/retriever_tools.py` | 把 Milvus retriever 封装成 LangChain Tool |
| Agent 层 | `agent/rag_agent.py` | tool-calling agent + 会话历史管理 |
| 编排层 | `graph/`、`graph2/` | 两条独立 LangGraph pipeline，无共享代码 |

**为什么这样分层**：模型/配置/存储/检索/编排解耦，任意一层可以独立替换（比如换 LLM 只改 `all_llm.py`，换向量库只改 `milvus_db.py`），符合关注点分离。缺点是 graph1 与 graph2 各自重复实现了 grading chain、llm 调用逻辑，没有共享抽象。

---

## 2. 文档解析与切块流水线

文件：[markdown_parser.py](../documents/markdown_parser.py)

### 2.1 三步流程

```python
def parse_markdown_to_documents(self, md_file: str) -> List[Document]:
    documents = self.parse_markdown(md_file)          # 1. 解析
    merged_documents = self.merge_title_content(documents)  # 2. 标题层级合并
    chunk_documents = self.text_chunker(merged_documents)   # 3. 语义二次切块
    return chunk_documents
```

**Step 1 — 解析（`parse_markdown`）**

用 `UnstructuredMarkdownLoader(mode='elements', strategy='fast')` 把一份 md 文件拆成"元素级"的 Document 列表——每个标题、每段正文都是独立的 Document，带 `category`（`Title`/`NarrativeText`/...）、`parent_id`、`element_id` 等 metadata，天然保留文档的树状结构信息。

**Step 2 — 标题层级合并（`merge_title_content`）**

这是全项目最核心、最容易被问到的算法逻辑。目的：把"标题 + 挂在它下面的正文"合并成一个语义完整的 chunk，而不是让标题和内容各自成为孤立的碎片。

```python
def merge_title_content(self, datas: List[Document]) -> List[Document]:
    merged_data = []
    parent_dict = {}  # key=当前父document的element_id, value=父document对象
    for document in datas:
        metadata = document.metadata
        parent_id = metadata.get('parent_id', None)
        category = metadata.get('category', None)
        element_id = metadata.get('element_id', None)

        if category == 'NarrativeText' and parent_id is None:  # 无父的正文，直接保留
            merged_data.append(document)
        if category == 'Title':
            document.metadata['title'] = document.page_content
            if parent_id in parent_dict:      # 标题自己也有父标题（多级标题）
                document.page_content = parent_dict[parent_id].page_content + ' -> ' + document.page_content
            parent_dict[element_id] = document  # 用自己的element_id注册为"父节点"
        if category != 'Title' and parent_id:   # 正文挂到父标题下
            parent_dict[parent_id].page_content += ' ' + document.page_content
            parent_dict[parent_id].metadata['category'] = 'content'

    merged_data.extend(parent_dict.values())
    return merged_data
```

逐条讲清楚：
- `parent_dict` 以 `element_id` 为 key，缓存"当前正在累积内容的标题节点"。
- 遇到 `Title`：把标题内容记进 `metadata['title']`；如果这个标题本身还有父标题（多级标题嵌套），就把父标题内容用 `->` 拼接上去，实现层级路径（如 `产品概述 -> 计费模块 -> 套餐说明`）；然后把自己注册进 `parent_dict`，等待后续正文往里追加。
- 遇到非 Title 且有 `parent_id`：说明这是某个标题下的正文段落，直接把内容 append 到对应父节点的 `page_content` 上，并把该父节点的 `category` 标记为 `content`（区别于纯 `Title`）。
- 最后把 `parent_dict` 里所有累积完的父节点（即"标题+它下面所有正文"合并后的完整块）作为最终结果输出。

**为什么这么设计**：如果不合并，检索到的可能只是一个孤零零的标题（没有实际内容）或一段没有上下文标题的正文，两者都会降低生成质量。合并后每个 chunk = "完整的一节内容"，语义自足。

**Step 3 — 语义二次切块（`text_chunker`）**

```python
def text_chunker(self, datas: List[Document]) -> List[Document]:
    new_docs = []
    for d in datas:
        if len(d.page_content) > 5000:  # 超过阈值才二次切分
            new_docs.extend(self.text_splitter.split_documents([d]))
            continue
        new_docs.append(d)
    return new_docs
```

用 `SemanticChunker(openai_embedding, breakpoint_threshold_type="percentile")`：只有当 Step 2 合并后的块超过 5000 字符才触发（说明这一节内容特别长），基于**句子间 embedding 相似度的断点**做二次切分，而不是固定长度硬切——避免把一个完整语义单元从中间切断。

> 面试点：为什么不对所有文档都做语义切分？—— 语义切分需要调用 embedding API，成本高、耗时长；只对超长块做，兼顾成本与切块质量。

**用的 Embedding**：这里用的是 `openai_embedding`（`llm_models/embeddings_model.py` 里基于千帆网关的 `bge-large-zh`），**不是**存储进 Milvus 用的 `bge_embedding`（本地 `BAAI/bge-small-zh-v1.5`）。两者模型、维度、部署方式都不同，混用会导致向量空间不一致——这是简历里"两个 Embedding 模型各司其职"的具体体现。

---

## 3. Milvus 混合检索方案（Dense+Sparse+RRF）

文件：[milvus_db.py](../documents/milvus_db.py)、[retriever_tools.py](../tools/retriever_tools.py)

### 3.1 Collection Schema

```python
schema.add_field('id', DataType.INT64, is_primary=True, auto_id=True)
schema.add_field('text', DataType.VARCHAR, max_length=6000,
                  enable_analyzer=True,
                  analyzer_params={"tokenizer": "jieba", "filter": ["cnalphanumonly"]})
schema.add_field('category', ...)
schema.add_field('source', ...)
schema.add_field('filename', ...)
schema.add_field('filetype', ...)
schema.add_field('title', ...)
schema.add_field('category_depth', DataType.INT64)
schema.add_field('sparse', DataType.SPARSE_FLOAT_VECTOR, is_function_output=True)
schema.add_field('dense', DataType.FLOAT_VECTOR, dim=512)
```

关键点：
- `text` 字段开启 `enable_analyzer`，用 **jieba 分词器**对中文文本切词（`cnalphanumonly` filter 过滤非中文/字母数字字符）——这是 sparse 向量能正确处理中文关键词的前提。
- `sparse` 字段 `is_function_output=True`：它不是手动传入的，而是由下面的 BM25 Function **自动从 `text` 字段生成**。
- `dense` 维度 512（对应 BGE 模型的输出维度）。

### 3.2 BM25 Function（Sparse 侧）

```python
bm25_function = Function(
    name="text_bm25_emb",
    input_field_names=["text"],
    output_field_names=["sparse"],
    function_type=FunctionType.BM25,
)
schema.add_function(bm25_function)
```

Milvus 2.5+ 的内置能力：不需要自己算 TF-IDF/BM25 分数，写入 `text` 时 Milvus 自动跑 BM25 生成稀疏向量存进 `sparse` 字段。**面试重点**：BM25 本质是关键词精确匹配打分（考虑词频 TF + 逆文档频率 IDF），擅长专业术语、系统操作步骤这类"关键词必须精确命中"的场景；Dense 向量擅长语义相似（同义改写、口语化提问）。两者互补。

### 3.3 索引配置

```python
# sparse: 倒排索引
index_params.add_index(
    field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25",
    params={"inverted_index_algo": "DAAT_MAXSCORE", "bm25_k1": 1.2, "bm25_b": 0.75}
)
# dense: HNSW
index_params.add_index(
    field_name="dense", index_type=IndexType.HNSW, metric_type=MetricType.IP,
    params={"M": 16, "efConstruction": 64}
)
```

- **Sparse**：`SPARSE_INVERTED_INDEX` + `DAAT_MAXSCORE` 算法（Document-At-A-Time，用 MaxScore 剪枝加速倒排索引检索）。`bm25_k1=1.2`（词频饱和度参数，越大词频影响越大）、`bm25_b=0.75`（文档长度归一化参数，标准默认值）。
- **Dense**：`HNSW`（Hierarchical Navigable Small World，近似最近邻图索引）+ `IP`（内积，配合归一化向量等价于 cosine 相似度）。`M=16`（每个节点的邻接边数，越大精度越高但内存越大）、`efConstruction=64`（建图时的搜索范围，影响建图质量与耗时）。

**建表的"有损"重建逻辑**（面试要主动提及的坑）：

```python
if COLLECTION_NAME in client.list_collections():
    client.release_collection(collection_name=COLLECTION_NAME)
    client.drop_index(...)  # 先删两个索引
    client.drop_collection(collection_name=COLLECTION_NAME)  # 再删表
client.create_collection(...)
```

`create_collection()` 如果表已存在会先 `release → drop_index → drop_collection` 再重建——**即调用一次就把旧数据全部清空**。这是已知风险点，生产环境调用前必须确认不是正在使用的 collection。

### 3.4 RRF 混合检索（retriever_tools.py）

```python
mv = MilvusVectorSave()
mv.create_connection()
retriever = mv.vector_store_saved.as_retriever(
    search_type='similarity',
    search_kwargs={
        "k": 4,
        "score_threshold": 0.1,
        "ranker_type": "rrf",
        "ranker_params": {"k": 100},
        'filter': {"category": "content"}
    }
)
```

- `ranker_type: "rrf"`：**Reciprocal Rank Fusion**——dense 检索和 sparse(BM25) 检索各自独立跑出一个排序列表，RRF 按 `score = Σ 1/(k + rank_i)` 把两路排名融合成一个最终排序（而不是直接比较两种量纲不同的分数）。`ranker_params.k=100` 是平滑常数，越大排名差异的影响越平缓。
- `score_threshold: 0.1`：过滤掉相似度过低的结果。
- `filter: {"category": "content"}`：只检索 `category=content` 的块（对应 Step 2 合并后的"标题+正文"完整块），排除掉零散的孤立 Title 节点。
- **模块级副作用**：`mv.create_connection()` 在 import 这个文件时就执行——意味着任何 import 这个模块的代码都会立刻真实连接 Milvus。这是需要在面试中主动指出的设计问题（更好的做法是懒加载/依赖注入）。

> 面试高频追问：为什么不用 alpha 加权（`score = α*dense + (1-α)*sparse`）而用 RRF？—— dense 和 sparse 的原始分数量纲不同（cosine 相似度 [-1,1] vs BM25 分数无固定范围），直接加权需要精细调参且不稳定；RRF 只依赖排名顺序，不依赖具体分数大小，更鲁棒、免调参。

---

## 4. 双进程批量入库流水线

文件：[write_milvus.py](../documents/write_milvus.py)

### 4.1 架构：生产者-消费者模型

```
file_parser_process (进程1: 生产者)          milvus_writer_process (进程2: 消费者)
  扫描 md_dir 下所有 .md 文件                    从队列 get() 数据
  逐个 parse_markdown_to_documents()             阻塞等待
  攒够 batch_size(20) 条 → put 进队列    -->      mv.add_documents(batch)
  最后剩余的也 put 一次                            累计计数、打日志
  发送 None 作为终止信号                          收到 None 则 break 退出
```

```python
docs_queue = Queue(maxsize=queue_maxsize)  # maxsize=20，防止内存溢出
parser_proc = multiprocessing.Process(target=file_parser_process, args=(md_dir, docs_queue))
writer_proc = multiprocessing.Process(target=milvus_writer_process, args=(docs_queue,))
parser_proc.start(); writer_proc.start()
parser_proc.join(); writer_proc.join()
```

**设计要点**：
1. **解耦**：解析（CPU 密集，尤其语义切块要调 embedding API）和写入（IO 密集，网络请求 Milvus）拆成两个独立进程并行执行，避免互相阻塞——解析下一批的同时，上一批已经在写入。
2. **有界队列**（`maxsize=20`）：防止解析速度远快于写入速度时，未写入的数据在内存里无限堆积导致 OOM。队列满时 `put()` 会阻塞解析进程，形成自然的**反压（backpressure）**。
3. **哨兵值终止**：用 `None` 作为"数据结束"的信号，写入进程收到 `None` 就跳出循环——这是 multiprocessing 队列场景的常见终止模式（因为进程间无法直接共享布尔标志位，用队列本身传递终止信号最简单可靠）。
4. **单文件失败不影响其他文件**：`file_parser_process` 内部 `try/except` 包住单个文件的解析，某个文件解析失败只记日志，继续处理下一个文件。

**已知问题**：`__main__` 里 `md_dir` 是硬编码路径（原为 Windows 路径，当前项目已改为基于 `__file__` 的相对路径 `datas/md`，但要注意这只是解决了路径问题，没有解决可配置性问题——生产环境更应该做成命令行参数或环境变量）。

> 面试可能追问：为什么不用线程而用多进程？—— Python GIL 限制多线程无法真正并行跑 CPU 密集任务（如语义切块时的向量计算/大量字符串处理）；用多进程能利用多核，且 `write_milvus.py` 场景是"解析"和"写入"两个不同性质的重任务，进程级隔离也更稳（一个进程崩溃不影响另一个）。

---

## 5. 检索工具封装 + Agent 多轮对话

文件：[retriever_tools.py](../tools/retriever_tools.py)、[rag_agent.py](../agent/rag_agent.py)

### 5.1 封装成 LangChain Tool

```python
retriever_tool = create_retriever_tool(
    retriever,
    'rag_retriever',
    '搜索并返回关于 "CRM系统" 的信息, 内容涵盖：销售SOP流程、产品功能模块、系统操作与故障排查、客户异议处理话术等'
)
```

`create_retriever_tool` 把一个 LangChain `Retriever` 包装成 `Tool` 对象，核心是那段**工具描述（description）**——LLM 是靠这段描述文本来判断"这个问题该不该调用这个工具"的，描述写得越精准（覆盖实际知识库的内容范围），LLM 路由决策越准。

### 5.2 Agent + 会话历史

```python
agent = create_tool_calling_agent(llm, [retriever_tool], prompt)
executor = AgentExecutor(agent=agent, tools=[retriever_tool])

store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

agent_with_history = RunnableWithMessageHistory(
    executor, get_session_history,
    input_messages_key='input', history_messages_key='chat_history'
)
```

- `create_tool_calling_agent`：基于 LLM 的原生 function-calling 能力构建 agent（不同于早期基于 ReAct 文本解析的 agent，更稳定，依赖模型本身结构化输出工具调用参数）。
- `RunnableWithMessageHistory` + `get_session_history`：以 `session_id` 为 key 在内存字典 `store` 里维护每个会话的历史消息——支撑"销售/客服连续追问"场景（比如先问"XX功能怎么用"，接着问"那报错了怎么办"，第二轮能带上第一轮上下文）。
- **局限**：`store` 是进程内内存字典，进程重启历史全丢，也无法在多实例部署间共享——生产环境应换成 Redis/DB 持久化的 `BaseChatMessageHistory` 实现。

**已知副作用问题**：文件顶层有硬编码 demo 调用（`agent_with_history.invoke({...'客户对价格有异议该怎么处理？'...})`），意味着 `import agent.rag_agent` 这一行代码就会真实触发一次 LLM 调用+Milvus 检索——这是典型的"模块导入不应有副作用"反例，面试可以主动提出这是需要改进的地方（应该包在 `if __name__ == '__main__':` 里）。

---

## 6. Graph1：简单工具调用型 RAG

文件：[graph/graph1.py](../graph/graph1.py)，配套节点：`agent_node.py`、`generate_node.py`、`rewrite_node.py`、`graph_state1.py`

### 6.1 State 定义

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # add_messages: 追加而非覆盖

class Grade(BaseModel):
    binary_score: str  # 'yes' / 'no'
```

State 只有一个字段 `messages`，用 LangGraph 内置的 `add_messages` reducer——每个节点返回的消息会**追加**到列表末尾而不是覆盖整个 state，这是 LangGraph 处理对话历史的标准模式。

### 6.2 流程图

```
START → agent → [tools_condition]
                    ├─ 有工具调用 → retrieve → [grade_documents]
                    │                              ├─ 相关 → generate → END
                    │                              └─ 不相关 → rewrite → agent (循环，无次数上限)
                    └─ 无工具调用 → END
```

```python
workflow.add_node('agent', agent_node)
workflow.add_node('retrieve', ToolNode([retriever_tool]))  # LangGraph内置ToolNode
workflow.add_node('rewrite', rewrite)
workflow.add_node('generate', generate)

workflow.add_edge(START, 'agent')
workflow.add_conditional_edges('agent', tools_condition, {'tools': 'retrieve', END: END})
workflow.add_conditional_edges('retrieve', grade_documents)  # 无显式map，用返回值字符串匹配节点名
workflow.add_edge('rewrite', 'agent')
workflow.add_edge('generate', END)
```

**各节点做什么**：
- `agent_node`：`llm.bind_tools([retriever_tool])`，只看最后一条消息 `messages[-1]`（不是全部历史）来决定是否调用工具。
- `retrieve`：用 LangGraph **内置的** `ToolNode`，不用自己写检索逻辑，框架自动执行 agent 决定调用的工具。
- `grade_documents`（定义在 `graph1.py` 内部，不是独立节点，是条件边函数）：取最后一条消息（工具返回的检索结果）+ 最后一条人类消息，让 LLM 结构化输出 `Grade.binary_score` 判断相关性，返回字符串 `"generate"` 或 `"rewrite"` 直接对应节点名。
- `rewrite`：把原问题重新表述后再丢回 `agent` 节点重新走一遍（可能触发新的检索）。
- `generate`：取最后一条消息内容（检索结果）作为 context，配合原始问题生成最终回答。

**核心风险点（面试必提）**：`rewrite → agent` 这条回边**没有循环次数上限**。如果 LLM 反复判断检索结果不相关，理论上会无限循环 `agent → retrieve → grade(no) → rewrite → agent → ...`，存在死循环/无限重试的风险，也没有兜底策略（比如兜底走 web 搜索）。对比 graph2 就有 `transform_count` 计数器和上限。

### 6.3 checkpointer 与多轮对话

```python
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)
config = {"configurable": {"thread_id": thread_id}, ...}
```

用 `MemorySaver`（内存态 checkpointer）+ `thread_id` 让同一个 `thread_id` 的多次 `graph.stream()` 调用共享 state（即 `messages` 列表持续累积），实现多轮对话。这是 graph1 独有的能力——graph2 没有 checkpointer，每次调用都是全新单轮。

---

## 7. Graph2：Self-RAG 自纠错流程

文件：[graph2/graph_2.py](../graph2/graph_2.py)，配套节点/链：`retriever_node.py`、`grade_documents_node.py`、`grader_chain.py`、`generate_node2.py`、`grade_hallucinations_chain.py`、`grade_answer_chain.py`、`transform_query_node.py`、`web_search_node.py`、`query_route_chain.py`、`graph_state2.py`

这是简历里"更复杂的路由+自纠错链路"，比 graph1 多了 4 层评估：**问题路由 → 文档相关性 → 幻觉检测 → 答案匹配度**。

### 7.1 State 定义

```python
class GraphState(TypedDict):
    question: str
    transform_count: int   # 查询重写次数，有上限控制（关键：graph1没有这个）
    generation: str
    documents: List[Document]
```

注意这里是**普通字段覆盖**，不是 graph1 的消息追加模式——因为 graph2 走的是结构化状态机流程，不是对话消息流。

### 7.2 完整流程图

```
START → [route_question] → web_search 或 retrieve
                              │
              web_search ─────┴──→ generate（跳过grading，直接生成）
                              │
              retrieve → grade_documents → [decide_to_generate]
                                              ├─ 有相关文档 → generate
                                              ├─ 无文档 & transform_count<2 → transform_query → retrieve（回去重新检索）
                                              └─ 无文档 & transform_count>=2 → web_search（兜底）
                              │
              generate → [grade_generation_v_documents_and_question]
                              ├─ not supported（幻觉）→ generate（重试，⚠️无上限）
                              ├─ not useful（答案不切题）→ transform_query → retrieve
                              └─ useful → END
```

### 7.3 四层评估逐一拆解

**① 问题路由（`route_question` / `query_route_chain.py`）**

```python
class RouteQuery(BaseModel):
    datasource: Literal["vectorstore", "web_search"]

structured_llm_router = llm.with_structured_output(RouteQuery)
system = """...向量知识库包含与半导体材料，芯片制造，光刻技术相关的文档。
对于这些主题的问题请使用向量知识库，其他情况使用网络搜索。"""
```

用 `with_structured_output` 强制 LLM 输出枚举值（`Literal` 类型），比让 LLM 自由文本输出再解析更稳定可靠。**注意**：这段 system prompt 写的是"半导体/芯片/光刻"（项目原始 demo 领域），如果要迁移到 CRM 场景（简历里说的"销售SOP/产品功能/故障排查"），这段 prompt 需要同步改成 CRM 相关描述，否则路由会全部导向 web_search——**这是实际项目适配时最容易漏改的地方，也是简历真实性的一个细节，面试可以提前想好怎么解释**。

**② 文档相关性评分（`grade_documents_node.py` + `grader_chain.py`）**

```python
for d in documents:
    score = retrieval_grader_chain.invoke({"question": question, "document": d.page_content})
    if score.binary_score == "yes":
        filtered_docs.append(d)
```

**逐篇文档单独打分过滤**（不是整体打包判断一次），这样能精确剔除检索到的 k 篇里混进来的不相关文档，只保留真正相关的用于生成。这是 graph2 比 graph1 更精细的地方——graph1 的 `grade_documents` 是对整批检索结果统一判断相关/不相关。

**③ 幻觉检测（`grade_generation_v_documents_and_question` + `grade_hallucinations_chain.py`）**

```python
score = hallucination_grader_chain.invoke({"documents": documents, "generation": generation})
if score.binary_score == "yes":  # 生成内容基于文档
    # 继续检查答案匹配度
else:
    return "not supported"  # 退回generate重试
```

判断"生成的回答是不是凭空编的，有没有事实依据于检索到的文档"——这是 Self-RAG 论文里的核心思想：generation 必须能在 documents 里找到支撑，否则算幻觉。

**④ 答案匹配度（`answer_grader_chain.py`）**

```python
score = answer_grader_chain.invoke({"question": question, "generation": generation})
if score.binary_score == "yes":
    return "useful"
else:
    return "not useful"  # 答案没跑题但没真正解决问题 → 重写查询再检索
```

即使回答没有幻觉（有依据），也可能没有真正**回答用户的问题**（比如答非所问）——这一步专门检查这个。

### 7.4 `decide_to_generate` 的三分支与循环保护

```python
def decide_to_generate(state):
    filtered_documents = state["documents"]
    transform_count = state.get("transform_count", 0)
    if not filtered_documents:
        if transform_count >= 2:
            return "web_search"       # 兜底：重写了2次还没有相关文档，直接走web搜索
        return "transform_query"      # 重写查询，回retrieve重新检索
    else:
        return "generate"
```

`transform_count` 是**有上限的重试计数器**（≥2 次转 web_search 兜底），这是 graph2 明显优于 graph1 的设计——graph1 的 `rewrite → agent` 循环完全没有这种保护。

**但要注意一个不对称的坑**：`transform_count` 只在"文档检索环节"（`decide_to_generate`）有上限保护；但在"生成结果幻觉检测"分支（`grade_generation_v_documents_and_question` 返回 `"not supported"` 时退回 `generate` 自身重试）**没有任何计数或上限**——如果 LLM 持续判定自己的输出有幻觉，这里存在无限重试风险。这是简历项目里唯一的、也是面试官最可能挖出来问的"设计不完善之处"，建议主动坦白并给出改进方向（比如给 `generate` 也加一个重试计数字段，超过阈值就直接返回"抱歉未找到确切答案"）。

### 7.5 web_search 分支跳过 grading

```python
workflow.add_edge("web_search", "generate")  # 直接到generate，不经过grade_documents
```

Web 搜索结果被认为是"已经具备一定可信度的外部信息"，不需要再走文档相关性打分这一层（因为 web_search 本身通过 query 已经是针对性检索），直接进入生成环节。

---

## 8. 已知问题（面试可能被追问的坑）

按优先级从高到低：

| 问题 | 位置 | 影响 | 面试应对话术 |
|---|---|---|---|
| `generate` 幻觉重试无上限 | `graph2/graph_2.py` `not supported` 分支 | 死循环风险 | "已知的边界情况，实际生产会加计数器+阈值兜底，类似 transform_count 的做法" |
| `rewrite→agent` 无上限 | `graph/graph1.py` | 死循环风险 | 同上，graph1 是更早期/更简单的版本，用于验证基础工具调用链路 |
| import 时副作用（真实LLM调用/连接Milvus） | `agent/rag_agent.py`、`tools/retriever_tools.py` | 单测困难、启动变慢、意外耗费 token | "早期开发阶段遗留的验证代码，生产化时会挪到 `if __name__=='__main__'` 或改为懒加载/依赖注入" |
| `create_collection` 有损重建 | `documents/milvus_db.py` | 误删生产数据 | "已知风险点，调用前必须核对 collection 不是线上使用中的" |
| graph1/graph2 无共享抽象 | 全局 | 重复代码（各自的 grading chain、llm 调用） | "两条 pipeline 是探索不同 RAG 范式（简单工具调用 vs Self-RAG）的独立验证，验证完可以抽取共享的 grading/generate 基础组件" |
| Self-RAG 路由 prompt 仍是半导体领域文案 | `graph2/query_route_chain.py` | 迁移到 CRM 场景需要同步改 prompt 措辞 | "领域迁移时 prompt 与 collection 数据要同步切换，这是简历项目落地 CRM 场景的必要改动点" |
| `write_milvus.py` 硬编码路径 | `__main__` 里的 `md_dir` | 不同环境需要改代码才能跑 | "生产环境应做成 CLI 参数或环境变量配置" |
| 会话历史存内存字典 | `agent/rag_agent.py` `store={}` | 重启丢失、多实例不共享 | "验证阶段用内存态，生产要换 Redis 或 DB 持久化的 ChatMessageHistory 实现" |

---

## 9. 高频面试问答（QA）

**Q1：为什么要用 Dense+Sparse 混合检索，而不是只用向量检索？**

A：纯向量（dense）检索擅长语义相似，但对专业术语、型号名、操作步骤这类需要**精确关键词命中**的内容召回率不够（embedding 会把语义相近但关键词不同的内容也检出来，反而稀释精确匹配）。BM25(sparse) 擅长关键词精确匹配。两路并行检索后用 RRF 融合排名，既保留语义泛化能力，又不丢失关键词精确度，尤其适合 CRM 场景里"系统操作步骤"、"产品功能名词"这类查询。

**Q2：RRF 和直接加权融合分数比，优势在哪？**

A：dense 的相似度分数（如 cosine，范围 [-1,1]）和 BM25 的分数（理论无固定上界）量纲完全不同，直接加权 `α*dense_score + (1-α)*sparse_score` 需要反复调 α 且不同 query 下最优 α 可能不同。RRF 只依据两路各自的**排名位次**（不看具体分数值），用 `1/(k+rank)` 转换再求和，天然消除了量纲问题，更鲁棒、无需调参。

**Q3：Markdown 解析为什么要按标题层级合并，而不是直接按固定长度切块？**

A：固定长度切块（如每 500 字符切一段）会在任意位置切断语义单元，导致检索出的 chunk 上下文残缺（比如一句话被切成两半分到两个 chunk）。按标题层级合并保证每个 chunk 是"一个完整的语义单元"（标题+对应内容），检索到的内容天然自洽。超长的再用语义相似度做二次切分，而不是硬切，进一步保证语义连续性。

**Q4：Self-RAG（graph2）比简单 RAG（graph1）多做了什么？**

A：graph1 只有一层"检索文档相关性"判断；graph2 有四层：① 问题路由（判断该走知识库还是 web 搜索）② 文档相关性逐篇过滤 ③ 生成内容幻觉检测（是否基于检索文档）④ 答案匹配度检测（是否真正回答了问题）。并且 graph2 对"检索不到文档"这条路径有计数器兜底（重试 2 次后转 web 搜索），比 graph1 的无限重试更健壮。

**Q5：为什么两条 embedding 模型不能混用？**

A：`openai_embedding`（千帆网关 `bge-large-zh`）用于语义切块阶段（`SemanticChunker` 判断句子相似度断点），`bge_embedding`（本地 `BAAI/bge-small-zh-v1.5`）用于最终写入 Milvus 的向量表示。两者模型结构、参数、输出维度都不同（512 维 dense 字段是按后者配置的），如果拿切块用的 embedding 去做检索，向量空间不匹配，相似度计算完全没有意义。用两个模型是因为职责不同：一个只是"辅助判断哪里该断句"，一个是"最终要被检索命中的语义表示"，没有必要绑定同一个模型，可以根据场景各自选型（比如本地模型省去网络调用延迟，适合高频批量写入）。

**Q6：项目里哪里体现了"工程化"而不只是写 demo？**

A：① 双进程解耦（解析/写入）+ 有界队列反压，应对大批量文档入库；② Milvus schema 层面设计了 dense+sparse 双索引及混合排序，不是简单调用一个向量库 SDK；③ 用 LangGraph 显式建模了带条件分支的状态机（而不是一个线性 chain），支持路由、重试、兜底等真实业务需要的控制流；④ 会话维度的历史管理支撑多轮追问，贴合客服/销售连续对话的真实场景。

**Q7：如果让你现在改进这个项目，你会先做什么？**

A：优先修复两处无上限循环风险（graph2 幻觉重试、graph1 rewrite 循环），加计数器兜底；其次把 import 时的副作用代码收敛掉（真实 LLM 调用/Milvus 连接不应该在模块加载时触发），改善可测试性；然后把会话历史从内存字典换成持久化存储。如果有更多时间，会抽取 graph1/graph2 之间重复的 grading chain 逻辑做成共享组件。

**Q8：BM25 的 k1、b 参数分别是什么含义？**

A：`k1`（本项目设为 1.2）控制词频饱和度——词出现次数越多贡献分数越高，但 `k1` 决定这个增长的饱和速度，`k1` 越大，词频对分数的边际贡献越持续；`b`（本项目 0.75，也是经验默认值）控制文档长度归一化的强度——`b` 越大，长文档里的词频权重会被压得更低（防止长文档因为词多而"虚高"排名）。

**Q9：HNSW 索引里 M 和 efConstruction 分别影响什么？**

A：`M`（本项目 16）是图中每个节点保留的邻接边数，越大检索精度越高但索引占用内存也越大；`efConstruction`（本项目 64）是建图阶段的候选搜索范围，越大建出来的图质量越好（后续检索更准）但建索引耗时更长。两者都是"精度 vs 资源/时间"的权衡参数。

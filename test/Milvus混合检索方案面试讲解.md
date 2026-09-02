# Milvus 混合检索（Dense + Sparse + RRF）— 面试讲解

对应简历表述：

> 参与开发基于 Milvus 设计并实现 Dense+Sparse 混合检索方案：Dense 向量使用本地 BGE 模型生成语义向量，Sparse 侧基于 BM25 从文本生成关键词向量，两路并行检索后用 RRF 算法融合排序，提升专业术语、系统操作步骤等关键词场景的召回准确率。

## 1. 为什么要 Dense+Sparse 混合，不只用向量检索

单纯 dense 向量检索的弱点：语义向量对"专业术语/系统操作步骤/产品型号"这类**低频、精确匹配型 query** 召回不稳定——语义模型倾向捕捉整体语义相似度，对字面精确命中不敏感。例如"CRM工单状态从待处理改成已关闭要走哪个按钮"，这种偏"关键词+操作步骤"的问题，BM25 关键词检索命中率反而更高。

做法：两路并行，dense 抓语义相关性，sparse(BM25) 抓关键词精确匹配，再融合，取长补短。

## 2. Dense 侧：本地 BGE 模型

[llm_models/embeddings_model.py](../llm_models/embeddings_model.py) 里有两个 embedding 模型，**不是同一个**，用途不同：

- `openai_embedding`：走千帆网关代理，**只用于文档切块阶段**（`markdown_parser.py` 里的 `SemanticChunker` 语义分割断点判断），对 >5000 字符的合并内容块做二次语义切分
- `bge_embedding`：本地 `BAAI/bge-small-zh-v1.5`，CPU 跑，**专门用于 Milvus 存储/检索的向量化**（dense 字段）

面试要点：为什么存储侧选本地 BGE 而不是继续用代理模型？——中文语料场景下 BGE 系列对中文语义表征效果好，且本地部署不依赖外部 API 调用延迟和成本，适合大批量文档入库场景。

## 3. Sparse 侧：Milvus 内置 BM25 Function，不是外部实现

关键代码 [documents/milvus_db.py:35-41](../documents/milvus_db.py#L35-L41)：

```python
bm25_function = Function(
    name="text_bm25_emb",
    input_field_names=["text"],
    output_field_names=["sparse"],
    function_type=FunctionType.BM25,
)
```

不是自己写 BM25 算法，而是用 Milvus 2.4+ 内置的 **Function 机制**——schema 定义时把 `text` 字段声明为 `is_function_output` 的 sparse 向量来源，Milvus 存储时自动跑 BM25 算法把文本转成稀疏向量。

分词器：`jieba` tokenizer + `cnalphanumonly` 过滤（[milvus_db.py:24-25](../documents/milvus_db.py#L24-L25)，保留中文/字母/数字）。

索引：`SPARSE_INVERTED_INDEX` + `DAAT_MAXSCORE` 算法（[milvus_db.py:45-56](../documents/milvus_db.py#L45-L56)），`bm25_k1=1.2, bm25_b=0.75` 是标准 BM25 默认调参（k1 控制词频饱和度，b 控制文档长度归一化）。

面试要点：为什么不自己实现 BM25 再转成向量存？——用数据库内置 Function 省掉了"应用层计算 sparse 向量再写入"的一步，检索时 dense 和 sparse 可以在同一次 Milvus 查询里并行算分，减少应用层与数据库间的往返，也保证两路检索原子一致。

## 4. 融合排序：RRF (Reciprocal Rank Fusion)

[tools/retriever_tools.py:6-14](../tools/retriever_tools.py#L6-L14)：

```python
search_kwargs={
    "k": 4,
    "score_threshold": 0.1,
    "ranker_type": "rrf",
    "ranker_params": {"k": 100},
    'filter': {"category": "content"}
}
```

核心思路：不直接比较 dense 的相似度分数和 sparse 的 BM25 分数（两者量纲完全不同，没法直接加权融合），而是取两路各自召回结果里的**排名**（rank），公式大致是 `score = Σ 1/(k + rank_i)`，`k=100` 是平滑常数防止排名靠前的项过度主导。这样即使 dense 分数和 sparse 分数尺度不一致，也能公平融合排序。

面试要点：为什么选 RRF 而不是加权求和(weighted sum)？——加权求和需要人工调 dense/sparse 权重比例，且两边分数分布不同（cosine [-1,1] vs BM25 无上界），归一化本身就是麻烦事；RRF 只依赖排名不依赖分数值，天然免疫量纲问题，是业界混合检索的标准做法（Milvus/Elasticsearch 都内置支持）。

## 5. 检索精筛：category 过滤

`filter={"category": "content"}` 是二次过滤——Milvus schema 里存了 markdown 解析后的 `category`（比如 `Title`/`content` 等 unstructured 解析出的元素类型），检索时只召回正文内容块，排除标题等结构性元素，避免噪声进入最终排序。

## 6. Milvus 提供的检索能力全景（不用自己开发底层算法）

**Dense 向量检索**（ANN，近似最近邻）
- 索引类型：`HNSW`（本项目用）、`IVF_FLAT`、`IVF_SQ8`、`IVF_PQ`、`DiskANN`、`FLAT` 等
- 度量方式：`IP`（本项目用，内积）、`L2`、`COSINE`

**Sparse 向量检索**
- 数据类型：`SPARSE_FLOAT_VECTOR`
- 索引类型：`SPARSE_INVERTED_INDEX`（本项目用）、`SPARSE_WAND`
- 算法：`DAAT_MAXSCORE`（本项目用）、`DAAT_WAND`、`TAAT_NAIVE`

**混合检索**（Hybrid Search）
- 多向量字段并行查询后用 `ranker` 融合——`rrf`（本项目用）或 `weighted`
- API 层是 `client.hybrid_search()`，本项目通过 `langchain_milvus` 封装间接调用

Sparse 向量的生成有两条路，Milvus 都支持：
1. 自己算好再存（外部生成 sparse embedding，比如 splade 模型离线算好插入）
2. Milvus 内置 Function 自动生成（本项目走这条路，见第 3 节）

算法层（BM25 打分公式、HNSW 索引构建、RRF 融合排名）都是 Milvus 原生能力，零自研。项目实际贡献在**方案选型和参数设计**：为什么选 BM25 Function 而不是外部 splade、为什么 RRF 而不是 weighted、jieba 分词器怎么配、`k1/b` 怎么调、category 过滤怎么设计。

面试如实讲：贡献在选型和调参，不在算法本身实现，别夸大成"自己实现了BM25"，容易被追问底层原理时露馅。

## 7. "混合检索"与"Dense+Sparse检索"是同一件事，不是两个选项

**Hybrid Search = Dense检索 + Sparse检索 + RRF融合**，三个词说的是同一件事的三个层面，不是互斥的三种方案。

- Dense 向量检索：其中一路，`bge_embedding` 算语义向量，`HNSW` 索引
- Sparse 向量检索：另一路，Milvus BM25 Function 算关键词向量，`SPARSE_INVERTED_INDEX` 索引
- RRF：把两路各自召回的排序结果**融合**成最终排序的算法

"混合检索"指的就是"同时用 dense+sparse 两路并跑，再融合"这整个动作。RRF 是混合检索里的融合策略选项之一（另一选项是 `weighted`）。

触发机制：[documents/milvus_db.py:80-88](../documents/milvus_db.py#L80-L88) 里 `vector_field=['dense', 'sparse']` 声明了两个向量字段，一次检索传了多个 `vector_field`，Milvus 底层就自动跑 dense 一路 + sparse 一路，再按 `ranker_type` 指定方式融合返回结果。

## 一句话总结（面试可直接说）

> 用 Milvus 原生的 BM25 Function 在同一 collection 里同时维护 dense/sparse 双索引，检索时通过 RRF 做排名层融合而非分数层融合，规避了跨模态分数不可比的问题，同时用本地 BGE 模型保证中文语义向量质量，兼顾语义相关性和关键词精确匹配两种召回场景。

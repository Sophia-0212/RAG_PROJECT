# 文档相关性判断：Graph1 vs Graph2 对比

延续Q3上下文（文档相关性打分/延迟/兜底），分开讲两条pipeline各自的实现，最后对比。配套基础概念见 [langgraph/langgraph核心概念笔记.md](./langgraph/langgraph核心概念笔记.md)。

---

## Graph1 的文档相关性判断

文件位置：`graph/graph1.py`，函数`grade_documents`（**条件边函数**，不是独立node，直接写在`graph1.py`里）。

```python
def grade_documents(state) -> Literal["generate", "rewrite"]:
    llm_with_structured = llm.with_structured_output(Grade)

    prompt = PromptTemplate(
        template="""你是一个评估检索文档与用户问题相关性的评分器。
            这是检索到的文档：\n\n {context} \n\n
            这是用户的问题：{question} \n
            如果文档包含与用户问题相关的关键词或语义含义，则评为相关。
            给出二元评分 'yes' 或 'no' 来表示文档是否与问题相关。""",
        input_variables=["context", "question"],
    )
    chain = prompt | llm_with_structured

    messages = state["messages"]
    last_message = messages[-1]              # ToolNode返回的那条消息
    question = get_last_human_message(messages).content
    docs = last_message.content               # 整批检索结果，拼成的一段文本

    scored_result = chain.invoke({"question": question, "context": docs})
    score = scored_result.binary_score

    if score == "yes":
        return "generate"
    else:
        return "rewrite"
```

**关键点**：

- `last_message.content`——这是LangGraph内置`ToolNode`执行完检索工具后塞进`messages`列表的那条`ToolMessage`，它的`content`是检索到的k=4个chunk拼接后的整个字符串（Milvus retriever的输出被序列化成一段文本）。
- 打分是**整批一次性判断**：4个chunk合在一起，一次LLM调用，一个yes/no，代表"这批结果整体相关不相关"。
- 只有两个出口：`generate`（相关，直接生成）或`rewrite`（不相关，把问题重新表述后送回`agent`节点，`agent`可能再次触发检索）。
- `rewrite→agent`这条回边**没有次数上限**，理论上可以无限循环。
- 用的state是`messages`列表（`add_messages`追加模式），没有专门的`documents`字段，检索结果就混在消息历史里。

---

## Graph2 的文档相关性判断

文件位置：`graph2/grade_documents_node.py`（**独立node**）+ `graph2/grader_chain.py`（打分链定义）。

```python
# grader_chain.py
class GradeDocuments(BaseModel):
    binary_score: str = Field(description="文档是否与问题相关，取值为'yes'或'no'")

structured_llm_grader = llm.with_structured_output(GradeDocuments)
system = """你是一个评估检索文档与用户问题相关性的评分器。
    如果文档包含与用户问题相关的关键词或语义含义，则评为相关。
    不需要非常严格的测试，目的是过滤掉错误的检索结果。
    给出'yes'或'no'的二元评分来表示文档是否与问题相关。"""
grade_prompt = ChatPromptTemplate.from_messages([
    ("system", system),
    ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
])
retrieval_grader_chain = grade_prompt | structured_llm_grader
```

```python
# grade_documents_node.py
def grade_documents(state):
    question = state["question"]
    documents = state["documents"]        # List[Document]，独立字段，不混在messages里

    filtered_docs = []
    for d in documents:                     # 逐chunk遍历
        score = retrieval_grader_chain.invoke(
            {"question": question, "document": d.page_content}
        )
        if score.binary_score == "yes":
            filtered_docs.append(d)
        else:
            continue
    return {"documents": filtered_docs, "question": question}
```

**关键点**：

- `state["documents"]`是`List[Document]`，是State（`GraphState` TypedDict）里的**独立结构化字段**，不像graph1那样混在`messages`里。
- 打分是**逐chunk单独判断**：for循环4次，每个chunk各自调一次LLM，各自输出yes/no，相关的留进`filtered_docs`，不相关的直接扔。
- 打完分之后不是直接决定`generate`/`rewrite`两个出口，而是把过滤后的`filtered_docs`（可能是空、可能部分、可能全部保留）交给下一个决策函数`decide_to_generate`处理：

```python
def decide_to_generate(state):
    filtered_documents = state["documents"]
    transform_count = state.get("transform_count", 0)
    if not filtered_documents:
        if transform_count >= 2:
            return "web_search"      # 兜底
        return "transform_query"      # 重写问题，有限重试
    else:
        return "generate"
```

- 三个出口（`generate`/`transform_query`/`web_search`），且`transform_query`这条回边**有计数器`transform_count`上限**（≥2转兜底），不会无限循环。

---

## 对比

| 维度 | Graph1 | Graph2 |
|---|---|---|
| 打分粒度 | 整批一次判断（4个chunk拼一起打一个分） | 逐chunk单独判断（4次独立LLM调用，各自yes/no） |
| 打分结果承载方式 | 混在`messages`列表里（`ToolMessage.content`是拼接字符串） | State里独立的`documents: List[Document]`字段，结构化保留 |
| 精细程度 | 粗——只要整批里有一部分不相关就可能拖累整体判断，或者反过来部分不相关的chunk也可能被一起放过 | 细——能精确剔除4个里混进来的不相关chunk，只保留真正相关的 |
| 不相关时的出口 | 只有1个：`rewrite`（重写问题回`agent`重新走） | 3个分支：`transform_query`（重写重试，有限次）/`web_search`（兜底）/`generate`（还有剩余相关chunk则生成） |
| 循环保护 | 无上限，`rewrite→agent`可能无限循环 | 有`transform_count`计数器，≥2次转`web_search`兜底 |
| LLM调用次数（打分这一步） | 1次（整批） | k次（k=4，逐chunk各1次） |
| 延迟代价 | 低（1次调用） | 高（4次串行调用，且是同步for循环，无并发优化） |
| 设计定位 | 更简单的验证性实现，用于跑通基础"检索→判断→生成/重写"闭环 | Self-RAG范式的精细实现，用更多LLM调用换更高的过滤精度和更完善的兜底策略 |

一句话总结这组对比：**graph1用1次LLM调用换低延迟、粗粒度、无兜底；graph2用k次LLM调用换高精度、细粒度、有限重试+兜底，本质是准确率与延迟之间不同的工程取舍**，这也是Self-RAG论文相比普通RAG-Agent范式多付出的成本所在。

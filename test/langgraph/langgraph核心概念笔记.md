# LangGraph 常用内置函数 & 概念笔记

结合本项目 graph1（简单工具调用型RAG）、graph2（Self-RAG）的实际用法整理，附带问答记录。配套可运行demo：[test_langgraph_node_vs_edge.py](./../test_langgraph_node_vs_edge.py)

---

## 目录

1. [核心概念：独立node vs 条件边函数](#1-核心概念独立node-vs-条件边函数)
2. [项目里已用到的内置函数/类](#2-项目里已用到的内置函数类)
3. [消息类型体系：HumanMessage / AIMessage / ToolMessage](#3-消息类型体系humanmessage--aimessage--toolmessage)
4. [LangGraph生态常用但项目未用到的高级特性](#4-langgraph生态常用但项目未用到的高级特性)
5. [问答记录（Q&A Log）](#5-问答记录qa-log)

---

## 1. 核心概念：独立node vs 条件边函数

| | 独立node | 条件边函数 |
|---|---|---|
| 注册方式 | `add_node(name, func)` | `add_conditional_edges(from_node, func, [mapping])` |
| 返回值类型 | `dict`（更新state的字段） | `str`（下一个节点名） |
| 对state的影响 | 修改/追加 | 只读，不修改 |
| 图上的表现 | 一个方框（干活的地方） | 方框之间的分叉箭头（选路的地方） |
| 职责 | 执行具体业务逻辑（调LLM、查数据库、调工具） | 只做路由判断，回答"接下来去哪" |

**本项目对照**：

- graph2把"打分"和"路由决策"拆成两步：`grade_documents`（真node，改`state.documents`）→ `decide_to_generate`（条件边函数，只读`state.documents`做路由）
- graph1把两步合并成一步：`grade_documents`（条件边函数，自己打分自己决定路由，不是node，从没被`add_node`注册过）

**判断依据**：看函数有没有被传给`add_node()`，以及它的返回类型——返回`dict`就是node，返回`str`（节点名）就是条件边函数。两个项目里都叫`grade_documents`的函数，角色完全不同，容易搞混。

---

## 2. 项目里已用到的内置函数/类

### 2.1 `tools_condition`

```python
from langgraph.prebuilt import tools_condition
workflow.add_conditional_edges('agent', tools_condition, {'tools': 'retrieve', END: END})
```

- 类别：条件边函数（LangGraph内置）
- 逻辑：检查`state["messages"][-1]`（最后一条`AIMessage`）有没有非空的`tool_calls`字段——有则返回字符串`"tools"`，没有则返回`END`
- 只做判断，不执行任何工具调用
- 返回的字符串要配合`add_conditional_edges`第三个参数（映射表）才能实际跳转到某个node：`{'tools': 'retrieve', END: END}`表示"收到'tools'就去retrieve节点，收到END就结束"
- 用途：graph1里判断agent是否要调用检索工具

### 2.2 `ToolNode`

```python
from langgraph.prebuilt import ToolNode
workflow.add_node('retrieve', ToolNode([retriever_tool]))
```

- 类别：node类（不是函数，是一个可调用对象/callable class）
- `ToolNode([retriever_tool])`：实例化，构造参数是"这个执行器手上有权调用的工具列表"
- 内部逻辑：读`state["messages"][-1].tool_calls`，按`name`字段匹配到对应工具，执行它（比如`retriever_tool.invoke(参数)`），把结果包装成`ToolMessage`，返回`{"messages": [tool_message]}`
- 本质也是"会修改state的独立node"，只是具体行为（执行工具+包装结果）是LangGraph帮你写好的，不用自己实现
- 用途：graph1里真正执行Milvus检索的地方

### 2.3 `add_messages`

```python
from langgraph.graph import add_messages
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

- 类别：state字段的reducer（不是node/边函数）
- 作用：配合`Annotated`标注某个字段，node返回该字段时执行"追加"而非"覆盖"整个列表
- 还会自动处理消息去重、按`id`合并更新等细节
- 用途：graph1的`messages`字段靠它持续累积对话历史（用户问题、AI的工具调用请求、工具返回结果、AI的最终回答，都追加进同一个列表）

### 2.4 `MemorySaver`

```python
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)
```

- 类别：checkpointer（状态持久化器）
- 作用：配合`thread_id`（在`config={"configurable": {"thread_id": xxx}}`里传入）让同一个对话线程的多次`graph.stream()`调用共享state
- 存内存态，进程重启即丢失；生产环境可换`SqliteSaver`/`PostgresSaver`等持久化实现
- 用途：graph1借此实现多轮对话记忆（graph2没有配置checkpointer，每次调用都是全新单轮，没有跨轮记忆）

### 2.5 `START` / `END`

```python
from langgraph.constants import START, END
```

- 类别：常量（固定的节点名哨兵值），不是函数
- `START`：图的入口标记，`workflow.add_edge(START, 'agent')`表示"从这里开始执行"
- `END`：图的终点标记，`workflow.add_edge('generate', END)`或条件边函数里`return END`表示"流程到此结束"

---

## 3. 消息类型体系：HumanMessage / AIMessage / ToolMessage

三种类型代表三个不同的"发言者角色"，**互斥**（一条消息只能是其中一种类型）：

```python
HumanMessage(content="客户对价格有异议怎么处理")     # 用户说的话
AIMessage(content="...", tool_calls=[...])          # LLM说的话（可能是纯文本回答，也可能是工具调用请求）
ToolMessage(content="...", tool_call_id="...")       # 工具执行完，返回的结果
```

### 3.1 `tool_calls`是`AIMessage`的字段，不是独立消息类型

现代LLM的function calling能力：LLM输出不再只是纯文本，还可以是"文本 + 结构化的工具调用请求"。`bind_tools()`之后，LLM自己判断"要不要调用工具"：

```python
# 形态1：LLM决定直接回答，tool_calls为空
AIMessage(content="您好，处理话术是...", tool_calls=[])

# 形态2：LLM决定先调用工具查资料，content基本为空
AIMessage(content="", tool_calls=[
    {"name": "rag_retriever", "args": {"query": "客户价格异议处理"}, "id": "call_abc123"}
])
```

一次完整问答里，`AIMessage`会出现两次、形态不同：第一次是"调用指令"形态，第二次（看到检索结果后）才是"文字回答"形态。

### 3.2 `ToolMessage`与`tool_calls`是"请求-响应"配对关系

`AIMessage.tool_calls`里每一项有个`id`；执行完对应工具后产出的`ToolMessage`带上同样的`tool_call_id`，用于配对：

```python
# 请求方
AIMessage(content="", tool_calls=[{"name": "rag_retriever", "args": {...}, "id": "call_abc123"}])

# 响应方，用tool_call_id对号
ToolMessage(content="检索到的文本...", tool_call_id="call_abc123")
```

### 3.3 完整链路示意（graph1场景）

```
HumanMessage           用户提问（角色：用户）
     ↓
AIMessage(tool_calls=[...])   LLM决定要查资料（角色：AI，内容性质="调用指令"）
     ↓
ToolNode 执行该指令，真正调用 retriever_tool.invoke()
     ↓
ToolMessage             工具返回的检索结果（角色：工具，回应上面的tool_calls）
     ↓
AIMessage(content="根据检索结果...")   LLM给出最终文字回答（角色：AI，内容性质="回答"）
```

`state["messages"][-1]`在链路不同阶段取到的是不同类型的消息——在`grade_documents`这一步，取到的正是`ToolNode`刚产出的`ToolMessage`。

---

## 4. LangGraph生态常用但项目未用到的高级特性

| 名字 | 类别 | 作用 |
|---|---|---|
| `interrupt` / `Command`（`langgraph.types`） | 人工介入机制 | node内部调用`interrupt(value)`暂停图执行，等外部输入后用`Command(resume=xxx)`恢复。CRM场景"敏感回复需人工确认"可以用这个 |
| `Send`（`langgraph.types`） | 动态并行分发 | 条件边函数里用，根据列表动态生成N个并行子任务，各自带不同参数发去同一个node（map-reduce模式）。可用来实现"4个chunk并发打分"而不是现在的串行for循环 |
| `RetryPolicy`（`langgraph.types`） | node级容错 | `add_node('generate', generate, retry=RetryPolicy(max_attempts=3))`，给单个node配置网络超时等临时性错误的自动重试，跟业务层"重写查询重试"是两个概念 |
| `interrupt_before` / `interrupt_after`（compile参数） | 声明式人工介入 | `workflow.compile(interrupt_before=["generate"])`，跑到指定node前/后自动暂停，不需要在node内部写`interrupt()` |
| `get_state()` / `update_state()` | 运行时state读写 | 配合checkpointer，运行时/运行后手动查看或修改当前state，调试和人工纠偏常用 |

---

## 5. 问答记录（Q&A Log）

### Q: 条件边函数和独立node有什么区别？

已在[第1节](#1-核心概念独立node-vs-条件边函数)详细整理，核心：返回`dict`且修改state = node；返回`str`（节点名）且只读state = 条件边函数。

### Q: `state["messages"][-1]`是什么意思？

Python基础语法，不是LangGraph特有：
- `state["messages"]`：字典取值，取出key为`"messages"`对应的value（一个list）
- `[-1]`：负数索引，取列表最后一个元素（`-1`=倒数第一，`-2`=倒数第二）
- 合起来：取消息列表里最新追加进去的那一条
- 用`-1`而不是具体数字下标的原因：消息列表长度是动态变化的（随对话轮数、工具调用次数增长），`-1`永远稳定指向"当前最新"，不用关心列表到底多长

### Q: 检查`tool_calls`字段——AIMessage不应该是AI消息吗，怎么会有tool_calls？

误区：把"AI说的话"想成只有"纯文本回答"一种形态。实际上现代LLM的function calling能力让`AIMessage`可以携带两种内容之一：纯文本回答，或者"我要调用哪个工具"的结构化请求（`tool_calls`字段）。这两种情况下发言者都是AI，只是内容性质不同（回答 vs 调用指令）。`tool_calls`不是工具执行后留下的痕迹，是**LLM自己主动生成的请求**，`ToolNode`收到这个请求后才会真正去执行工具、产出独立的`ToolMessage`。

### Q: 所以`ToolMessage`和`tool_calls`之前理解混淆了？

确认修正：
- `tool_calls`：字段，长在`AIMessage`身上（一个属性，值是list）
- `ToolMessage`：类，独立的消息类型（跟`HumanMessage`/`AIMessage`互斥的第三种类型）
- 关系：`tool_calls`列表里每项有`id`，工具执行完产出的`ToolMessage`带上同样的`tool_call_id`用于配对，是"请求-响应"关系，不是同一个东西的两种叫法

### Q: `tools_condition`判断有`tool_calls`后为什么返回字符串"tools"，而不是直接去调用工具？

核心：**判断"要不要调用工具"和"真正调用工具"是两个不同职责，LangGraph拆给两个不同角色**：
- `tools_condition`（条件边函数）：只做判断题，回答"接下来去哪"，返回一个字符串，不知道、也不关心工具具体怎么执行
- 字符串本身不会触发任何动作，要配合`add_conditional_edges`的第三个参数（映射表`{'tools': 'retrieve', ...}`）才能让LangGraph框架知道"收到'tools'这个信号，就跳转去执行'retrieve'节点"
- `ToolNode`（真正的node）：才是执行工具、产出`ToolMessage`的地方

类比：`tools_condition`是红绿灯判断逻辑（只决定亮什么信号），映射表是路牌（信号对应哪个方向），`ToolNode`是目的地本身（车真开到这里才发生"检索"这个动作）。这样拆分是单一职责原则的体现——路由判断逻辑和具体业务执行逻辑解耦，以后想换工具只需要改`ToolNode`构造参数，不需要碰路由函数。

### Q: `ToolNode([retriever_tool])`这行代码怎么理解？

拆两步：
1. `ToolNode([retriever_tool])`——实例化一个`ToolNode`对象，构造参数是"这个执行器手上有权调用的工具列表"（造一个"工具执行器"）
2. `workflow.add_node('retrieve', ...)`——把这个执行器注册进图，取名`'retrieve'`，图里其他地方（比如条件边函数的映射表）用这个名字就能跳转过来执行它

`ToolNode`实例本身是可调用对象（实现了`__call__`），接收state、返回dict，跟普通函数node在`add_node`眼里是等价的——`add_node`第二个参数只要求"可调用、接收state返回dict"，不要求必须是`def`定义的函数。跑到这个节点时，实际发生：读上一条`AIMessage.tool_calls`，按`name`找到`retriever_tool`，执行`retriever_tool.invoke(参数)`，包装结果成`ToolMessage`，返回`{"messages": [tool_message]}`。

### Q: `agent_node`里 `model = llm.bind_tools([retriever_tool])` 是不是"这个node专门调用retriever_tool"？

```python
def agent_node(state: AgentState):
    messages = state["messages"]
    model = llm.bind_tools([retriever_tool])
    response = model.invoke([messages[-1]])   # 只看最后一条
    return {"messages": [response]}            # 追加进列表
```

不是。`bind_tools`只是把工具的描述信息（名字/参数schema/description文本）告诉LLM，让LLM"知道自己有这个工具可选"，本身不执行任何调用。**调不调用是LLM自己推理判断的**，`agent_node`只是把这个判断结果（`tool_calls`字段是否非空）产出成一条`AIMessage`。真正执行检索是下一步`ToolNode`的活，`agent_node`本身不查Milvus。

`response = model.invoke([messages[-1]])`里"最后一条"是不是新加的、在哪加的，要分两种情况：
- **第一轮**：图执行前，`inputs = {"messages": [("user", question)]}`已经把用户提问放进去了（不是`agent_node`自己加的，是进图之前加的）。此时列表只有1个元素，`messages[-1]`就是这条`HumanMessage`。
- **循环回来的轮次**（比如从`rewrite`节点回到`agent`）：`rewrite`节点执行完`return {"messages": [response]}`，新消息通过`add_messages`追加到列表末尾，然后沿`add_edge('rewrite', 'agent')`跳回`agent_node`，这时`messages[-1]`取到的就是`rewrite`刚追加的那条。

所以"最后一条"具体是谁取决于当前处于流程哪一步，这也是为什么用`-1`而不是固定下标——`agent_node`会被反复进入，每次"最新的一条"都不同。

`agent_node`本身**既读又写**：读`messages[-1]`作为LLM输入，写`return {"messages": [response]}`把LLM的决策结果（可能带`tool_calls`，也可能是纯文本）追加进列表——每次执行完列表长度都+1，只是它加的是"LLM的决策结果"，不是"检索结果"（检索结果是下一步`ToolNode`产出的）。

**已知局限（记入问题清单）**：`model.invoke([messages[-1]])`只传了`[messages[-1]]`（只包一个元素的新列表），**不是完整历史`messages`**。也就是graph1的`agent_node`每次调用LLM时，LLM看不到更早的对话历史，只看"当前最新这一条"。这跟`rag_agent.py`里`RunnableWithMessageHistory`（支持多轮记忆）是不同机制——graph1这里虽然靠`MemorySaver`把历史存进了state，但`agent_node`调用LLM时并没有把完整历史喂给它，多轮场景下LLM在决策"要不要调用工具"这一步实际是"失忆"的。

### Q: 之前没看到代码里写`add_messages(...)`，它在哪里被调用的？

`add_messages`不是在node函数体内手动调用的函数，是在**定义state结构时**跟字段绑定好的"自动合并规则"：

```python
# graph/graph_state1.py
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

`Annotated[list[BaseMessage], add_messages]`的意思：messages字段类型是`list[BaseMessage]`，但每次有node返回这个字段的新值时，不要直接覆盖，要用`add_messages`函数处理（声明式注册，不是手动调用）。

**没有这个标注会怎样**：如果写成`messages: list[BaseMessage]`（没有`Annotated`），`agent_node`里`return {"messages": [response]}`执行完，LangGraph默认行为是**直接覆盖**整个字段——之前累积的所有历史（用户提问、之前的AIMessage、ToolMessage）全部丢失，多轮对话和检索历史没法维持。

**真正执行合并的是LangGraph框架本身**，发生在业务代码返回之后、下一个node被调用之前（大致顺序：node返回dict → 框架检查该字段是否绑定了reducer → 框架自动执行`add_messages(旧列表, 新值)` → 写回state → 传给下一个node）。业务代码（`agent_node`/`rewrite`/`generate`）从头到尾只需要`return {"messages": [xxx]}`，不用关心合并逻辑，这是reducer机制刻意设计成让业务代码保持简洁的地方。

### Q: 用户自行梳理agent_node流程，是否正确？

用户总结：*"第一步取出messages数组，第二步给这个node阶段的大模型绑定了一个retriever_tool，可以用也可以不用，第三步是拿出messages数组最新的一条喂给大模型，大模型自己决定要不要调用retriever_tool，最后大模型给出的回答会被add_messages进入列表。"*

确认：四步理解完全正确，无需纠正。对应代码逐句：`messages = state["messages"]`（取出）→ `model = llm.bind_tools([retriever_tool])`（绑定可选工具）→ `response = model.invoke([messages[-1]])`（喂最后一条，LLM自主决策）→ `return {"messages": [response]}`（触发`add_messages`追加，因为`AgentState`里该字段绑定了这个reducer）。

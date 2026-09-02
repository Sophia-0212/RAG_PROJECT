"""
召回率评测：对比graph1（整批判断）与graph2（逐chunk过滤）在文档相关性判断上的实际效果差异。

评测口径：
- 检索层（Milvus RRF混合检索）两条pipeline完全一样，用同一个retriever，k=4
- 差异只在"文档相关性判断"这一层：
    graph1: 4个chunk拼接成一段文本，整体打1次分，yes则4个全部保留，no则4个全部丢弃
    graph2: 4个chunk逐个单独打分，yes的留下，no的丢弃，形成子集

指标：
- Recall@k    = 检索到的chunk里，命中ground_truth_source文档的数量 / 1（假设每题只有1篇标准答案文档，命中记1，未命中记0，再对chunk去重按文档判断）
- Precision@k = 检索到的chunk里，来自ground_truth_source文档的chunk数 / 检索返回的chunk总数（这里衡量"过滤后剩下的chunk里有多少是真正对的"）

因为两条pipeline的"过滤"逻辑发生在Milvus检索之后，所以：
- 检索阶段命中的1次Milvus召回结果是共享的（避免因为检索本身的随机性造成两条pipeline输入不一致）
- graph1/graph2分别对这份共享的检索结果做不同的过滤处理，得到各自最终保留的chunk集合
- 用最终保留的chunk集合分别计算Recall@k和Precision@k
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_milvus import Milvus, BM25BuiltInFunction

from llm_models.all_llm import llm
from llm_models.embeddings_model import bge_embedding
from utils.env_utils import MILVUS_URI
from utils.log_utils import log

from eval_questions import EVAL_QUESTIONS

TEST_COLLECTION_NAME = "interview_recall_test"
K = 4


# ---------- 构造检索器（复刻 tools/retriever_tools.py 的配置） ----------
def build_retriever():
    vector_store = Milvus(
        embedding_function=bge_embedding,
        collection_name=TEST_COLLECTION_NAME,
        builtin_function=BM25BuiltInFunction(),
        vector_field=['dense', 'sparse'],
        consistency_level="Strong",
        auto_id=True,
        connection_args={"uri": MILVUS_URI}
    )
    retriever = vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={
            "k": K,
            "score_threshold": 0.1,
            "ranker_type": "rrf",
            "ranker_params": {"k": 100},
            'filter': {"category": "content"}
        }
    )
    return retriever


# ---------- graph1的判断逻辑：整批打分 ----------
class Grade(BaseModel):
    binary_score: str = Field(description="相关性评分 'yes' 或 'no'")


def graph1_filter(question: str, docs: list) -> list:
    """复刻 graph/graph1.py 的 grade_documents：整批拼接，打1次分，yes全留 no全弃"""
    if not docs:
        return []
    llm_with_structured = llm.with_structured_output(Grade)
    prompt = PromptTemplate(
        template="""你是一个评估检索文档与用户问题相关性的评分器。

            这是检索到的文档：

 {context}


            这是用户的问题：{question}

            如果文档包含与用户问题相关的关键词或语义含义，则评为相关。
            给出二元评分 'yes' 或 'no' 来表示文档是否与问题相关。""",
        input_variables=["context", "question"],
    )
    chain = prompt | llm_with_structured
    context = "\n\n".join(d.page_content for d in docs)
    result = chain.invoke({"question": question, "context": context})
    return docs if result.binary_score == "yes" else []


# ---------- graph2的判断逻辑：逐chunk打分 ----------
class GradeDocuments(BaseModel):
    binary_score: str = Field(description="文档是否与问题相关，取值为'yes'或'no'")


def graph2_filter(question: str, docs: list) -> list:
    """复刻 graph2/grade_documents_node.py + grader_chain.py：逐chunk单独打分"""
    if not docs:
        return []
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

    filtered = []
    for d in docs:
        score = retrieval_grader_chain.invoke({"question": question, "document": d.page_content})
        if score.binary_score == "yes":
            filtered.append(d)
    return filtered


def doc_source_filename(doc) -> str:
    """从Document的metadata里提取文件名，兼容不同字段命名"""
    meta = doc.metadata
    for key in ("filename", "source", "file_name"):
        if key in meta and meta[key]:
            return os.path.basename(meta[key])
    return ""


def evaluate():
    retriever = build_retriever()

    per_question_results = []
    t_start = time.time()

    for q in EVAL_QUESTIONS:
        qid = q["id"]
        question = q["question"]
        gt_source = q["ground_truth_source"]

        # 1. 共享的Milvus检索结果（两条pipeline共用同一次检索，避免检索随机性造成不公平对比）
        retrieved_docs = retriever.invoke(question)
        retrieved_sources = [doc_source_filename(d) for d in retrieved_docs]
        retrieval_hit = gt_source in retrieved_sources  # 检索层本身是否召回了标准答案文档

        # 2. graph1: 整批打分过滤
        g1_docs = graph1_filter(question, retrieved_docs)
        g1_sources = [doc_source_filename(d) for d in g1_docs]
        g1_recall_hit = gt_source in g1_sources
        g1_precision = (sum(1 for s in g1_sources if s == gt_source) / len(g1_sources)) if g1_sources else 0.0

        # 3. graph2: 逐chunk打分过滤
        g2_docs = graph2_filter(question, retrieved_docs)
        g2_sources = [doc_source_filename(d) for d in g2_docs]
        g2_recall_hit = gt_source in g2_sources
        g2_precision = (sum(1 for s in g2_sources if s == gt_source) / len(g2_sources)) if g2_sources else 0.0

        row = {
            "id": qid,
            "question": question,
            "ground_truth_source": gt_source,
            "retrieval_hit": retrieval_hit,
            "retrieved_sources": retrieved_sources,
            "graph1_recall_hit": g1_recall_hit,
            "graph1_kept_count": len(g1_docs),
            "graph1_precision": round(g1_precision, 3),
            "graph2_recall_hit": g2_recall_hit,
            "graph2_kept_count": len(g2_docs),
            "graph2_precision": round(g2_precision, 3),
        }
        per_question_results.append(row)
        print(f"[{qid:02d}] {question[:30]}... | 检索命中:{retrieval_hit} | "
              f"graph1(留{len(g1_docs)},recall={g1_recall_hit},prec={g1_precision:.2f}) | "
              f"graph2(留{len(g2_docs)},recall={g2_recall_hit},prec={g2_precision:.2f})")

    elapsed = time.time() - t_start

    # ---------- 汇总统计 ----------
    n = len(per_question_results)
    retrieval_recall = sum(r["retrieval_hit"] for r in per_question_results) / n
    g1_recall = sum(r["graph1_recall_hit"] for r in per_question_results) / n
    g2_recall = sum(r["graph2_recall_hit"] for r in per_question_results) / n
    g1_precision_avg = sum(r["graph1_precision"] for r in per_question_results) / n
    g2_precision_avg = sum(r["graph2_precision"] for r in per_question_results) / n

    summary = {
        "total_questions": n,
        "elapsed_seconds": round(elapsed, 1),
        "milvus_retrieval_recall_at_k": round(retrieval_recall, 4),
        "graph1_recall_at_k": round(g1_recall, 4),
        "graph2_recall_at_k": round(g2_recall, 4),
        "graph1_precision_at_k": round(g1_precision_avg, 4),
        "graph2_precision_at_k": round(g2_precision_avg, 4),
        "recall_delta_graph2_minus_graph1": round(g2_recall - g1_recall, 4),
        "precision_delta_graph2_minus_graph1": round(g2_precision_avg - g1_precision_avg, 4),
    }

    print("\n" + "=" * 70)
    print("汇总结果")
    print("=" * 70)
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # 保存详细结果到JSON，供后续写报告用
    out_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": per_question_results}, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {out_path}")

    return summary, per_question_results


if __name__ == "__main__":
    evaluate()

"""
召回率评测 v2：对比graph1（整批判断）与graph2（逐chunk过滤）。
相比v1的改进：
1. 用40题评测集（eval_questions_v2.py），覆盖factual/multi_hop/negation/colloquial四种类型
2. ground_truth_source支持多篇文档（多跳题）
3. 新增排序质量指标：MRR、NDCG@k
4. 新增冗余率指标：检索结果里重复/高度相似内容的比例（用简单的chunk来源文档重复计数近似）
5. Recall/Precision计算改为"文档级去重命中"，多跳题按"所有ground truth文档都命中"算完全命中，按"至少命中一篇"算部分命中

检索层与过滤层的职责边界跟v1一致：
- Milvus检索（RRF混合检索，k=4）两条pipeline共享
- graph1: 整批打分，yes全留/no全弃
- graph2: 逐chunk打分，各自去留
"""
import os
import sys
import json
import time
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_milvus import Milvus, BM25BuiltInFunction

from llm_models.all_llm import llm
from llm_models.embeddings_model import bge_embedding
from utils.env_utils import MILVUS_URI
from utils.log_utils import log

from eval_questions_v2 import EVAL_QUESTIONS

TEST_COLLECTION_NAME = "interview_recall_test"
K = 4


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


class Grade(BaseModel):
    binary_score: str = Field(description="相关性评分 'yes' 或 'no'")


def graph1_filter(question: str, docs: list) -> list:
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


class GradeDocuments(BaseModel):
    binary_score: str = Field(description="文档是否与问题相关，取值为'yes'或'no'")


def graph2_filter(question: str, docs: list) -> list:
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
    meta = doc.metadata
    for key in ("filename", "source", "file_name"):
        if key in meta and meta[key]:
            return os.path.basename(meta[key])
    return ""


# ---------- 排序质量指标 ----------
def compute_mrr(ranked_sources: list, gt_sources: set) -> float:
    """Mean Reciprocal Rank: 第一个命中ground truth的位置的倒数，没命中则0"""
    for idx, src in enumerate(ranked_sources):
        if src in gt_sources:
            return 1.0 / (idx + 1)
    return 0.0


def compute_ndcg(ranked_sources: list, gt_sources: set, k: int = K) -> float:
    """NDCG@k：relevance=1 if来自gt文档 else 0，用标准log2折损公式"""
    dcg = 0.0
    for idx, src in enumerate(ranked_sources[:k]):
        rel = 1.0 if src in gt_sources else 0.0
        dcg += rel / math.log2(idx + 2)  # idx从0开始，位置从1开始，log2(1+1)=1

    # IDCG: 理想情况下，所有相关文档都排在最前面
    num_relevant = min(len(gt_sources), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(num_relevant))
    return dcg / idcg if idcg > 0 else 0.0


def compute_redundancy(sources: list) -> float:
    """冗余率：重复来源文档的chunk数 / 总chunk数（同一文档被检索出多个chunk视为潜在冗余信号）"""
    if not sources:
        return 0.0
    from collections import Counter
    counts = Counter(sources)
    redundant = sum(c - 1 for c in counts.values() if c > 1)
    return redundant / len(sources)


def evaluate():
    retriever = build_retriever()

    per_question_results = []
    t_start = time.time()

    for q in EVAL_QUESTIONS:
        qid = q["id"]
        question = q["question"]
        gt_sources = set(q["ground_truth_source"])
        qtype = q["question_type"]

        retrieved_docs = retriever.invoke(question)
        retrieved_sources = [doc_source_filename(d) for d in retrieved_docs]

        # 检索层指标（两条pipeline共享，作为基线）
        retrieval_full_hit = gt_sources.issubset(set(retrieved_sources))
        retrieval_partial_hit = bool(gt_sources & set(retrieved_sources))
        mrr = compute_mrr(retrieved_sources, gt_sources)
        ndcg = compute_ndcg(retrieved_sources, gt_sources)
        redundancy = compute_redundancy(retrieved_sources)

        # graph1: 整批打分过滤
        g1_docs = graph1_filter(question, retrieved_docs)
        g1_sources = [doc_source_filename(d) for d in g1_docs]
        g1_full_hit = gt_sources.issubset(set(g1_sources))
        g1_partial_hit = bool(gt_sources & set(g1_sources))
        g1_precision = (sum(1 for s in g1_sources if s in gt_sources) / len(g1_sources)) if g1_sources else 0.0

        # graph2: 逐chunk打分过滤
        g2_docs = graph2_filter(question, retrieved_docs)
        g2_sources = [doc_source_filename(d) for d in g2_docs]
        g2_full_hit = gt_sources.issubset(set(g2_sources))
        g2_partial_hit = bool(gt_sources & set(g2_sources))
        g2_precision = (sum(1 for s in g2_sources if s in gt_sources) / len(g2_sources)) if g2_sources else 0.0

        row = {
            "id": qid, "question": question, "question_type": qtype,
            "ground_truth_source": list(gt_sources),
            "retrieved_sources": retrieved_sources,
            "retrieval_full_hit": retrieval_full_hit,
            "retrieval_partial_hit": retrieval_partial_hit,
            "mrr": round(mrr, 3), "ndcg_at_k": round(ndcg, 3), "redundancy": round(redundancy, 3),
            "graph1_kept_count": len(g1_docs), "graph1_full_hit": g1_full_hit,
            "graph1_partial_hit": g1_partial_hit, "graph1_precision": round(g1_precision, 3),
            "graph2_kept_count": len(g2_docs), "graph2_full_hit": g2_full_hit,
            "graph2_partial_hit": g2_partial_hit, "graph2_precision": round(g2_precision, 3),
            # 保留原始Document供生成层评估复用
            "_retrieved_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in retrieved_docs],
            "_graph1_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in g1_docs],
            "_graph2_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in g2_docs],
        }
        per_question_results.append(row)
        print(f"[{qid:02d}][{qtype:10s}] {question[:28]}... | "
              f"检索(部分命中:{retrieval_partial_hit},mrr={mrr:.2f},ndcg={ndcg:.2f},冗余={redundancy:.2f}) | "
              f"g1(留{len(g1_docs)},完全命中={g1_full_hit},prec={g1_precision:.2f}) | "
              f"g2(留{len(g2_docs)},完全命中={g2_full_hit},prec={g2_precision:.2f})")

    elapsed = time.time() - t_start

    n = len(per_question_results)

    def avg(key):
        return sum(r[key] for r in per_question_results) / n

    def rate(key):
        return sum(1 for r in per_question_results if r[key]) / n

    summary = {
        "total_questions": n,
        "elapsed_seconds": round(elapsed, 1),
        # 检索层
        "retrieval_full_recall": round(rate("retrieval_full_hit"), 4),
        "retrieval_partial_recall": round(rate("retrieval_partial_hit"), 4),
        "retrieval_mrr": round(avg("mrr"), 4),
        "retrieval_ndcg_at_k": round(avg("ndcg_at_k"), 4),
        "retrieval_redundancy": round(avg("redundancy"), 4),
        # graph1
        "graph1_full_recall": round(rate("graph1_full_hit"), 4),
        "graph1_partial_recall": round(rate("graph1_partial_hit"), 4),
        "graph1_precision": round(avg("graph1_precision"), 4),
        # graph2
        "graph2_full_recall": round(rate("graph2_full_hit"), 4),
        "graph2_partial_recall": round(rate("graph2_partial_hit"), 4),
        "graph2_precision": round(avg("graph2_precision"), 4),
        # 差值
        "full_recall_delta": round(rate("graph2_full_hit") - rate("graph1_full_hit"), 4),
        "precision_delta": round(avg("graph2_precision") - avg("graph1_precision"), 4),
    }

    # 按问题类型分组统计
    by_type = {}
    for qtype in ("factual", "multi_hop", "negation", "colloquial"):
        rows = [r for r in per_question_results if r["question_type"] == qtype]
        if not rows:
            continue
        nt = len(rows)
        by_type[qtype] = {
            "count": nt,
            "retrieval_partial_recall": round(sum(1 for r in rows if r["retrieval_partial_hit"]) / nt, 3),
            "graph1_precision": round(sum(r["graph1_precision"] for r in rows) / nt, 3),
            "graph2_precision": round(sum(r["graph2_precision"] for r in rows) / nt, 3),
        }

    print("\n" + "=" * 70)
    print("汇总结果")
    print("=" * 70)
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("\n按问题类型分组:")
    for qtype, stats in by_type.items():
        print(f"  {qtype}: {stats}")

    out_path = os.path.join(os.path.dirname(__file__), "eval_results_v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "by_type": by_type, "details": per_question_results},
                   f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {out_path}")

    return summary, by_type, per_question_results


if __name__ == "__main__":
    evaluate()

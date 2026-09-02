"""
修正Q1的ground_truth标注错误后，只重跑第1题（检索+过滤+生成三层），
并用重跑结果原地修正 eval_results_v2.json 和 eval_results_v2_generation.json 里的第1条记录+汇总统计，
避免因一处标注错误而整份重跑40题（节省时间和token）。
"""
import os
import sys
import json
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from run_recall_eval_v2 import (
    build_retriever, graph1_filter, graph2_filter, doc_source_filename,
    compute_mrr, compute_ndcg, compute_redundancy, K
)
from run_generation_eval import generate_answer, judge_correctness, judge_faithfulness, judge_relevance, format_docs
from eval_questions_v2 import EVAL_QUESTIONS

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results_v2.json")
GEN_RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results_v2_generation.json")


def rerun_q1():
    q1 = next(q for q in EVAL_QUESTIONS if q["id"] == 1)
    question = q1["question"]
    gt_sources = set(q1["ground_truth_source"])

    retriever = build_retriever()
    retrieved_docs = retriever.invoke(question)
    retrieved_sources = [doc_source_filename(d) for d in retrieved_docs]

    retrieval_full_hit = gt_sources.issubset(set(retrieved_sources))
    retrieval_partial_hit = bool(gt_sources & set(retrieved_sources))
    mrr = compute_mrr(retrieved_sources, gt_sources)
    ndcg = compute_ndcg(retrieved_sources, gt_sources)
    redundancy = compute_redundancy(retrieved_sources)

    g1_docs = graph1_filter(question, retrieved_docs)
    g1_sources = [doc_source_filename(d) for d in g1_docs]
    g1_full_hit = gt_sources.issubset(set(g1_sources))
    g1_partial_hit = bool(gt_sources & set(g1_sources))
    g1_precision = (sum(1 for s in g1_sources if s in gt_sources) / len(g1_sources)) if g1_sources else 0.0

    g2_docs = graph2_filter(question, retrieved_docs)
    g2_sources = [doc_source_filename(d) for d in g2_docs]
    g2_full_hit = gt_sources.issubset(set(g2_sources))
    g2_partial_hit = bool(gt_sources & set(g2_sources))
    g2_precision = (sum(1 for s in g2_sources if s in gt_sources) / len(g2_sources)) if g2_sources else 0.0

    new_retrieval_row = {
        "id": 1, "question": question, "question_type": q1["question_type"],
        "ground_truth_source": list(gt_sources),
        "retrieved_sources": retrieved_sources,
        "retrieval_full_hit": retrieval_full_hit,
        "retrieval_partial_hit": retrieval_partial_hit,
        "mrr": round(mrr, 3), "ndcg_at_k": round(ndcg, 3), "redundancy": round(redundancy, 3),
        "graph1_kept_count": len(g1_docs), "graph1_full_hit": g1_full_hit,
        "graph1_partial_hit": g1_partial_hit, "graph1_precision": round(g1_precision, 3),
        "graph2_kept_count": len(g2_docs), "graph2_full_hit": g2_full_hit,
        "graph2_partial_hit": g2_partial_hit, "graph2_precision": round(g2_precision, 3),
        "_retrieved_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in retrieved_docs],
        "_graph1_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in g1_docs],
        "_graph2_docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in g2_docs],
    }
    print(f"[重跑Q1-检索层] 检索来源:{retrieved_sources} | g1(留{len(g1_docs)},命中={g1_full_hit},prec={g1_precision:.2f}) "
          f"| g2(留{len(g2_docs)},命中={g2_full_hit},prec={g2_precision:.2f})")

    # ---------- 更新 eval_results_v2.json ----------
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        retrieval_data = json.load(f)
    old_row = next(r for r in retrieval_data["details"] if r["id"] == 1)
    idx = retrieval_data["details"].index(old_row)
    retrieval_data["details"][idx] = new_retrieval_row

    n = len(retrieval_data["details"])

    def avg(key):
        return sum(r[key] for r in retrieval_data["details"]) / n

    def rate(key):
        return sum(1 for r in retrieval_data["details"] if r[key]) / n

    retrieval_data["summary"] = {
        "total_questions": n,
        "elapsed_seconds": retrieval_data["summary"]["elapsed_seconds"],
        "retrieval_full_recall": round(rate("retrieval_full_hit"), 4),
        "retrieval_partial_recall": round(rate("retrieval_partial_hit"), 4),
        "retrieval_mrr": round(avg("mrr"), 4),
        "retrieval_ndcg_at_k": round(avg("ndcg_at_k"), 4),
        "retrieval_redundancy": round(avg("redundancy"), 4),
        "graph1_full_recall": round(rate("graph1_full_hit"), 4),
        "graph1_partial_recall": round(rate("graph1_partial_hit"), 4),
        "graph1_precision": round(avg("graph1_precision"), 4),
        "graph2_full_recall": round(rate("graph2_full_hit"), 4),
        "graph2_partial_recall": round(rate("graph2_partial_hit"), 4),
        "graph2_precision": round(avg("graph2_precision"), 4),
        "full_recall_delta": round(rate("graph2_full_hit") - rate("graph1_full_hit"), 4),
        "precision_delta": round(avg("graph2_precision") - avg("graph1_precision"), 4),
    }
    by_type = {}
    for qtype in ("factual", "multi_hop", "negation", "colloquial"):
        rows = [r for r in retrieval_data["details"] if r["question_type"] == qtype]
        if not rows:
            continue
        nt = len(rows)
        by_type[qtype] = {
            "count": nt,
            "retrieval_partial_recall": round(sum(1 for r in rows if r["retrieval_partial_hit"]) / nt, 3),
            "graph1_precision": round(sum(r["graph1_precision"] for r in rows) / nt, 3),
            "graph2_precision": round(sum(r["graph2_precision"] for r in rows) / nt, 3),
        }
    retrieval_data["by_type"] = by_type

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(retrieval_data, f, ensure_ascii=False, indent=2)
    print("已更新 eval_results_v2.json")

    # ---------- 生成层：重新生成答案并打分 ----------
    reference_answer = q1["reference_answer"]
    g1_answer = generate_answer(question, new_retrieval_row["_graph1_docs"])
    g2_answer = generate_answer(question, new_retrieval_row["_graph2_docs"])
    g1_context = format_docs(new_retrieval_row["_graph1_docs"])
    g2_context = format_docs(new_retrieval_row["_graph2_docs"])

    g1_correctness = judge_correctness(question, g1_answer, reference_answer)
    g1_faithfulness = judge_faithfulness(g1_answer, g1_context)
    g1_relevance = judge_relevance(question, g1_answer)

    g2_correctness = judge_correctness(question, g2_answer, reference_answer)
    g2_faithfulness = judge_faithfulness(g2_answer, g2_context)
    g2_relevance = judge_relevance(question, g2_answer)

    new_gen_row = {
        "id": 1, "question": question, "question_type": q1["question_type"],
        "reference_answer": reference_answer,
        "graph1_answer": g1_answer,
        "graph1_correctness": g1_correctness["score"], "graph1_correctness_reason": g1_correctness["reason"],
        "graph1_faithfulness": g1_faithfulness["score"], "graph1_faithfulness_reason": g1_faithfulness["reason"],
        "graph1_relevance": g1_relevance["score"], "graph1_relevance_reason": g1_relevance["reason"],
        "graph2_answer": g2_answer,
        "graph2_correctness": g2_correctness["score"], "graph2_correctness_reason": g2_correctness["reason"],
        "graph2_faithfulness": g2_faithfulness["score"], "graph2_faithfulness_reason": g2_faithfulness["reason"],
        "graph2_relevance": g2_relevance["score"], "graph2_relevance_reason": g2_relevance["reason"],
    }
    print(f"[重跑Q1-生成层] g1(correct={g1_correctness['score']:.2f},faith={g1_faithfulness['score']:.2f},rel={g1_relevance['score']:.2f}) "
          f"g2(correct={g2_correctness['score']:.2f},faith={g2_faithfulness['score']:.2f},rel={g2_relevance['score']:.2f})")

    with open(GEN_RESULTS_PATH, "r", encoding="utf-8") as f:
        gen_data = json.load(f)
    old_gen_row = next(r for r in gen_data["details"] if r["id"] == 1)
    idx2 = gen_data["details"].index(old_gen_row)
    gen_data["details"][idx2] = new_gen_row

    n2 = len(gen_data["details"])

    def avg2(key):
        return sum(r[key] for r in gen_data["details"]) / n2

    gen_data["summary"] = {
        "total_questions": n2,
        "elapsed_seconds": gen_data["summary"]["elapsed_seconds"],
        "graph1_correctness_avg": round(avg2("graph1_correctness"), 4),
        "graph1_faithfulness_avg": round(avg2("graph1_faithfulness"), 4),
        "graph1_relevance_avg": round(avg2("graph1_relevance"), 4),
        "graph2_correctness_avg": round(avg2("graph2_correctness"), 4),
        "graph2_faithfulness_avg": round(avg2("graph2_faithfulness"), 4),
        "graph2_relevance_avg": round(avg2("graph2_relevance"), 4),
        "correctness_delta": round(avg2("graph2_correctness") - avg2("graph1_correctness"), 4),
        "faithfulness_delta": round(avg2("graph2_faithfulness") - avg2("graph1_faithfulness"), 4),
        "relevance_delta": round(avg2("graph2_relevance") - avg2("graph1_relevance"), 4),
    }

    with open(GEN_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(gen_data, f, ensure_ascii=False, indent=2)
    print("已更新 eval_results_v2_generation.json")

    print("\n新汇总(检索+过滤层):", json.dumps(retrieval_data["summary"], ensure_ascii=False, indent=2))
    print("\n新汇总(生成层):", json.dumps(gen_data["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    rerun_q1()

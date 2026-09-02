"""
生成层评估：文章第四部分（正确性/忠实度Faithfulness/答案相关性）的手写实现。

流程：
1. 读取 run_recall_eval_v2.py 产出的 eval_results_v2.json，取每题graph1/graph2各自过滤后保留的chunk
2. 分别用这两组chunk作为context，调用LLM生成最终答案（复刻 graph/generate_node.py 和 graph2/generate_node2.py 的生成prompt，两条pipeline的生成prompt其实完全一样，都是"根据检索到的上下文回答问题"）
3. 用LLM-as-a-Judge对每个生成的答案打三个维度的分：
   - correctness: 跟reference_answer比，事实是否正确（0-1）
   - faithfulness: 答案是否基于检索到的context，有没有编造context之外的内容（0-1，拆解事实点逐一核查的简化版）
   - relevance: 答案是否真正回答了用户的问题（0-1）

不引入RAGAS等外部包，全部手写LLM-as-a-Judge逻辑，保持跟项目已有代码风格一致。
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.documents import Document

from llm_models.all_llm import llm

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results_v2.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "eval_results_v2_generation.json")


# ---------- 生成（复刻 graph/generate_node.py 与 graph2/generate_node2.py 的prompt，两者一致） ----------
GENERATE_PROMPT = PromptTemplate(
    template="你是一个问答任务助手。请根据以下检索到的上下文内容回答问题。如果不知道答案，请直接说明。回答保持简洁。\n问题：{question} \n上下文：{context} \n回答：",
    input_variables=["question", "context"],
)


def format_docs(docs: list) -> str:
    if not docs:
        return "（无检索结果）"
    return "\n\n".join(d["page_content"] for d in docs)


def generate_answer(question: str, docs: list) -> str:
    chain = GENERATE_PROMPT | llm | StrOutputParser()
    context = format_docs(docs)
    return chain.invoke({"context": context, "question": question})


# ---------- LLM-as-a-Judge：三个维度 ----------
class CorrectnessScore(BaseModel):
    score: float = Field(description="0到1之间的浮点数，1表示完全正确，0表示完全错误")
    reason: str = Field(description="简要说明打分理由")


class FaithfulnessScore(BaseModel):
    score: float = Field(description="0到1之间的浮点数，1表示回答完全基于上下文没有编造内容，0表示大量编造")
    reason: str = Field(description="简要说明打分理由，指出具体哪些内容缺乏上下文依据（如果有）")


class RelevanceScore(BaseModel):
    score: float = Field(description="0到1之间的浮点数，1表示完全回答了用户问题，0表示答非所问")
    reason: str = Field(description="简要说明打分理由")


def judge_correctness(question: str, generated_answer: str, reference_answer: str) -> dict:
    structured_llm = llm.with_structured_output(CorrectnessScore)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个严格的答案正确性评估专家。给定用户问题、模型生成的回答、以及人工撰写的参考答案，
判断生成回答在事实层面是否与参考答案一致（不要求措辞完全相同，只要求关键事实点、数字、规则一致）。
输出0到1之间的分数：1表示所有关键事实点都对，0.5表示部分关键事实点缺失或错误，0表示完全错误或答非所问。"""),
        ("human", "用户问题：{question}\n\n参考答案：{reference_answer}\n\n模型生成的回答：{generated_answer}\n\n请打分并说明理由。"),
    ])
    chain = prompt | structured_llm
    result = chain.invoke({
        "question": question, "reference_answer": reference_answer, "generated_answer": generated_answer
    })
    return {"score": result.score, "reason": result.reason}


def judge_faithfulness(generated_answer: str, context: str) -> dict:
    structured_llm = llm.with_structured_output(FaithfulnessScore)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个严格的幻觉检测专家。给定检索到的上下文和模型生成的回答，
把回答拆解成若干个事实陈述，逐一检查每个陈述是否能在上下文中找到依据。
输出0到1之间的分数：1表示回答的所有内容都能在上下文中找到依据（完全忠实，无幻觉），
0.5表示部分内容缺乏依据，0表示大部分内容是凭空编造、上下文中完全没有提及。
如果上下文为空但回答明确说'不知道/无法回答'，应该判为1分（诚实承认没有依据是忠实的表现）。"""),
        ("human", "检索到的上下文：{context}\n\n模型生成的回答：{generated_answer}\n\n请打分并指出具体哪些内容缺乏依据（如果有）。"),
    ])
    chain = prompt | structured_llm
    result = chain.invoke({"context": context, "generated_answer": generated_answer})
    return {"score": result.score, "reason": result.reason}


def judge_relevance(question: str, generated_answer: str) -> dict:
    structured_llm = llm.with_structured_output(RelevanceScore)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个答案相关性评估专家。给定用户问题和模型生成的回答，
判断这个回答是否真正针对性地回答了用户提出的具体问题，而不是答非所问、泛泛而谈、或者只回答了问题的一部分。
输出0到1之间的分数：1表示完全切题精准回答，0.5表示部分切题但有明显遗漏或跑偏，0表示完全答非所问。"""),
        ("human", "用户问题：{question}\n\n模型生成的回答：{generated_answer}\n\n请打分并说明理由。"),
    ])
    chain = prompt | structured_llm
    result = chain.invoke({"question": question, "generated_answer": generated_answer})
    return {"score": result.score, "reason": result.reason}


def evaluate_generation():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        retrieval_results = json.load(f)

    details = retrieval_results["details"]
    generation_results = []
    t_start = time.time()

    for row in details:
        qid = row["id"]
        question = row["question"]
        reference_answer = next(
            (q["reference_answer"] for q in __import__("eval_questions_v2").EVAL_QUESTIONS if q["id"] == qid),
            ""
        )

        g1_docs = row["_graph1_docs"]
        g2_docs = row["_graph2_docs"]

        # 1. 生成
        g1_answer = generate_answer(question, g1_docs)
        g2_answer = generate_answer(question, g2_docs)

        g1_context = format_docs(g1_docs)
        g2_context = format_docs(g2_docs)

        # 2. LLM-as-a-Judge 三维度打分
        g1_correctness = judge_correctness(question, g1_answer, reference_answer)
        g1_faithfulness = judge_faithfulness(g1_answer, g1_context)
        g1_relevance = judge_relevance(question, g1_answer)

        g2_correctness = judge_correctness(question, g2_answer, reference_answer)
        g2_faithfulness = judge_faithfulness(g2_answer, g2_context)
        g2_relevance = judge_relevance(question, g2_answer)

        result_row = {
            "id": qid, "question": question, "question_type": row["question_type"],
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
        generation_results.append(result_row)
        print(f"[{qid:02d}] g1(correct={g1_correctness['score']:.2f},faith={g1_faithfulness['score']:.2f},rel={g1_relevance['score']:.2f}) "
              f"g2(correct={g2_correctness['score']:.2f},faith={g2_faithfulness['score']:.2f},rel={g2_relevance['score']:.2f})")

    elapsed = time.time() - t_start
    n = len(generation_results)

    def avg(key):
        return sum(r[key] for r in generation_results) / n

    summary = {
        "total_questions": n,
        "elapsed_seconds": round(elapsed, 1),
        "graph1_correctness_avg": round(avg("graph1_correctness"), 4),
        "graph1_faithfulness_avg": round(avg("graph1_faithfulness"), 4),
        "graph1_relevance_avg": round(avg("graph1_relevance"), 4),
        "graph2_correctness_avg": round(avg("graph2_correctness"), 4),
        "graph2_faithfulness_avg": round(avg("graph2_faithfulness"), 4),
        "graph2_relevance_avg": round(avg("graph2_relevance"), 4),
        "correctness_delta": round(avg("graph2_correctness") - avg("graph1_correctness"), 4),
        "faithfulness_delta": round(avg("graph2_faithfulness") - avg("graph1_faithfulness"), 4),
        "relevance_delta": round(avg("graph2_relevance") - avg("graph1_relevance"), 4),
    }

    print("\n" + "=" * 70)
    print("生成层评估汇总")
    print("=" * 70)
    for k, v in summary.items():
        print(f"  {k}: {v}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": generation_results}, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {OUT_PATH}")

    return summary, generation_results


if __name__ == "__main__":
    evaluate_generation()

# Evaluation Runner 预测文件契约

Runner 不读取模型内部状态，只消费候选系统生成的 JSONL。每行对应一个 `case_id`：

```json
{"case_id":"SF-001","action":"answer","route":"vectorstore","answer":"须在4个工作小时内完成首次有效联系，并记录渠道、结果和下一步时间。","retrieved_source_refs":["adcrm://lead/governance@2.1.0#first-contact-sla"],"cited_source_refs":["adcrm://lead/governance@2.1.0#first-contact-sla"],"reason_code":null,"latency_ms":842.3}
```

字段含义：

- `action`：系统最终采取的 `answer`、`clarify` 或 `refuse`。
- `route`：实际路由 `vectorstore`、`direct_answer` 或 `refuse`。
- `answer`：最终面向用户的文本；拒答与澄清也写在这里。
- `retrieved_source_refs`：按召回顺序记录的 `source@version#section`。
- `cited_source_refs`：最终答案实际引用的证据。
- `reason_code`：拒答时必须给机器可判定的原因码；回答或澄清时为 `null`。
- `latency_ms`：可选的端到端耗时。

文件必须对所选数据集一条不多、一条不少，重复、缺失或未知 `case_id` 会直接终止评测。不要把数据集中的 `required_facts` 或 `match_any` 传给被测 RAG；这些是评判标签，不是推理上下文。

执行：

```bash
.venv/bin/python -m evaluation.run_cli path/to/candidate_predictions.jsonl \
  --output .rag-state/evaluation/candidate-report.json
```

输出包括总体指标、按 split/category/business_domain/risk_level 的切片、逐案例失败原因、资产校验信息和门禁结论。当前 Runner 是确定性离线评分器，不会主动调用生产 API；生成预测文件的 API 回放适配器属于独立的执行层。

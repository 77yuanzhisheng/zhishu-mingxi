# 批阅评测样本

`grading_samples.jsonl` 包含 20 条批阅种子样本，覆盖证明题、计算题、五维评分以及 5 类错误标签。它用于接口联调、回归测试和人工标注启动，不应直接视为真实学生金标准。

正式实验时应由至少两名教师独立评分，并使用现有 adjudication 接口完成仲裁；发布指标只使用仲裁后的标签。预测文件每行格式如下：

```json
{"id":"proof_demorgan_complete","total_score":98,"dimension_scores":{"conclusion_correctness":20,"key_reasoning_steps":34,"logical_rigor":24,"definition_theorem_usage":10,"expression_notation":10},"error_types":[],"latency_ms":8200,"needs_manual_review":false}
```

运行评测：

```powershell
py -3.11 scripts\evaluate_grading.py data\evaluation\predictions.jsonl
```

报告包含总分 MAE、五维 MAE、分档 Cohen Kappa、十分制二次加权 Kappa、错误类型 micro-F1、P50/P95 延迟及人工复核率。

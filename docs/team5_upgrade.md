# 队员五算法工具升级说明

## 1. 五维批阅加速与宽容度

`POST /api/grading/grade` 新增两个可选参数：

```json
{
  "grading_mode": "fast",
  "tolerance": "standard"
}
```

- `grading_mode=fast`：默认模式，一次模型调用同时完成分析、五维评分和复核。
- `grading_mode=strict`：保留分析、评分、复核三阶段，适合高风险考试或抽样复核。
- `tolerance=strict|standard|lenient`：控制等价写法、常规省略和 OCR 符号噪声的接受程度。错误结论、定理误用和循环论证在任何档位都不会被宽免。
- JSON 解析支持纯 JSON、Markdown JSON 代码块和带前后说明的 JSON 对象，减少无意义的修复调用。

## 2. 拍照 OCR 稳定性

`POST /api/practice/ocr` 地址和原请求格式不变。新链路会验证真实图片、检查尺寸和文件大小、自动旋转、缩放、增强对比度与锐度，并针对离散数学公式规范提示词。结果过短或无法识别时自动复核一次。

响应新增 `attempts`、`quality`、`warnings`、`raw_text` 和 `normalized`，原有 `ok/text/seconds` 继续保留。前端可依据警告提示重新拍照，同时允许用户修改识别文本后再提交批阅。

## 3. 八个符号工具入口

`GET /tools` 现在将 8 个确定性工具分成：

- 可计算：真值表、关系性质、公式化简、集合运算、最短路径、二分图判定。
- 可构造：主范式、哈斯图。

可用 `GET /tools?mode=compute` 或 `GET /tools?mode=construct` 筛选。Python/C 代码生成单列在 `assistant_tools`，所有原 `POST /tools/*` 及 `POST /tools/run` 保持兼容。

## 4. 批阅实验

评测样本位于 `data/evaluation/grading_samples.jsonl`，运行方法见同目录 README。正式 MAE/Kappa 结论必须使用教师独立评分并仲裁后的真实学生数据。

## 5. 微调前后 112 题对比

`scripts/team5_benchmark.py` 会让微调前、微调后两个模型分别完成老师题库全部 112 题，并使用同一个独立裁判模型评分。题型分布为填空题 56 道、计算题 36 道、证明题 16 道、应用题 4 道。运行过程按模型写入 JSONL 断点，最终生成：

- `artifacts/team5_benchmark/comparison.csv`：逐题准确性、分数和耗时。
- `artifacts/team5_benchmark/summary.json`：机器可读汇总及前后差值。
- `artifacts/team5_benchmark/report.md`：准确率、平均分、平均/P95 耗时对照表。
- `artifacts/team5_benchmark/proof_speed_gate.json`：证明题 `<=30s` 独立验收结果。

先在 `.env` 配置 `BASELINE_*`、`TUNED_*`、`JUDGE_*` 三组 OpenAI 兼容模型信息，再运行：

```powershell
& "D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe" scripts\team5_benchmark.py --resume --workers 2 --disable-thinking
```

默认速度门禁要求微调后 16 道证明题全部成功且每道不超过 30 秒，未达标时进程返回码为 2。联调时可先加 `--limit 2` 冒烟；只测速度可加 `--skip-judge`，但该模式不会生成准确率，不能作为最终对比结论。没有微调模型和独立裁判模型的真实 API 时，脚本不会伪造跑分。

## 6. 题库转微调指令集

`scripts/prepare_finetune_dataset.py` 将现有 112 题转为星火 MaaS 所需的 `system/user/assistant` JSONL，同时完成 HTML 清理、离散数学符号统一、空字段检查、重复问题去重和同题冲突答案检测：

```powershell
& "D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe" scripts\prepare_finetune_dataset.py
```

当前输出为 `data/finetune/teacher_questions_112.jsonl`，校验结果为 112/112 条有效、0 重复、0 冲突、0 无效，共规范化 562 处符号。默认文件严格只含三个训练字段；内部联调需要题号、题型和知识点时可加 `--include-metadata`。也可校验队员2扩展后的任意 JSONL：

```powershell
& "D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe" scripts\prepare_finetune_dataset.py --source data\finetune\expanded.jsonl --input-format jsonl --output data\finetune\expanded.cleaned.jsonl --report data\finetune\expanded.report.json
```

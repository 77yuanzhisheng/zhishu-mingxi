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

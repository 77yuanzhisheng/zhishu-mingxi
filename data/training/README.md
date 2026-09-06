# 星火 MaaS 训练数据

本目录保存离散数学智能教学平台的训练规则和数据说明。训练样本采用 MaaS 常用的 JSONL `messages` 格式，每一行都是一条独立 JSON 记录：

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}
```

- `system`：限定离散数学教师助手的角色、输出风格与格式要求。
- `user`：题目、知识点或学生作答。
- `assistant`：期望的讲解、推导、评分或纠错结果。

数据构建器支持题库中的 `exams`、`questions` 或顶层数组结构，覆盖填空、计算、证明、应用等题型；题目字段兼容 `q/a/kp` 与 `question/answer/knowledge_point` 命名。

## 构建数据集

在仓库根目录执行：

```powershell
python scripts/build_spark_dataset.py `
  --questions data/documents/教师训练题库.json `
  --documents data/documents `
  --rules data/training/symbol_rules.json `
  --output outputs/spark_dataset `
  --seed 20260903
```

构建过程会验证题库记录和符号规则、去重、固定随机种子切分，并原子写入输出目录。默认题库中的 112 道有效题会切分为：

```text
train: 90
validation: 11
test: 11
```

- `train.jsonl`：用于 MaaS 的 SFT 或 LoRA 训练。
- `validation.jsonl`：用于训练过程中的参数选择和效果监控。
- `test.jsonl`：仅用于训练后的固定评测，不参与调参。

## 上平台前确认

- 以目标 MaaS 平台实际支持的 SFT/LoRA、多模态训练和数据字段为准。
- API Key、AppID、API Secret、Token 等凭据不得写入 JSONL 或提交到仓库。
- 保持固定 `seed`，记录题库版本、训练参数和评测结果，保证实验可复现。
- 在平台预览中检查中文、LaTex、HTML 和离散数学符号的显示及转义行为。

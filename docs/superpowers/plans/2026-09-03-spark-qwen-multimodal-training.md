# 星火 MaaS + Qwen 离散数学多模型接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“知数·明析”接入星火 MaaS 微调后的 Qwen3-32B 文本模型和 Qwen3-VL-32B-Instruct 视觉模型，形成可训练、可调用、可测试的离散数学问答与图像识别链路，并用实测数据验证证明题等场景的 30 秒目标。

**Architecture:** 训练侧生成符合星火 MaaS 页面要求的文本 JSONL，采用 Qwen3-32B 的 SFT-LoRA；应用侧通过统一的 provider-neutral LLM 接口调用星火发布 API。图片题目和手写答案先由独立视觉适配器转成题目文本、学生答案、LaTeX 和符号，再进入现有 RAG、批阅、学情和学习路径业务；模型输出不能直接绕过现有规则校验和数据隔离。

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, python-dotenv, pytest, Chroma/RAG, JSONL, OpenAI-compatible HTTP/SSE；星火真实鉴权字段和模型资源标识只通过环境变量注入，不写入代码或 Git。

---

## 现状与改动边界

当前统一客户端位于 `backend/chat/llm.py`，业务层已经依赖 `generate(messages)` 和 `stream(messages)`；批阅入口位于 `backend/grading/router.py`，批阅流程位于 `backend/grading/service.py`；聊天入口位于 `backend/chat/router.py` 和 `backend/chat/service.py`；学习路径的 AI 解释位于 `backend/learning/path_ai.py`。数据中已有 `data/documents/老师训练题库.json` 以及离散数学教材、题库 Markdown 文件。

本计划不执行以下操作：

- 不删除已有 Qwen3.8-27B 压测脚本和历史结果；
- 不把 Qwen3-VL-32B 当成可微调模型；
- 不把星火密钥、AppID、API Secret、模型资源 ID 写入仓库；
- 不在星火接口字段尚未从平台页面确认前硬编码某一种私有请求格式；
- 不改写现有用户隔离、评分维度、批阅落库和学习路径规则。

---

### Task 1: 固定当前行为并盘点数据契约

**Files:**
- Create: `tests/test_spark_migration_inventory.py`
- Modify: `tests/test_llm.py`
- Inspect only: `backend/chat/llm.py`, `backend/chat/service.py`, `backend/grading/service.py`, `backend/learning/path_ai.py`, `data/documents/老师训练题库.json`

- [ ] **Step 1: 写当前客户端和核心业务的契约测试**

```python
from backend.chat.llm import LLMClient


def test_business_layers_depend_on_provider_neutral_methods():
    assert set(LLMClient.__annotations__) == set()
    assert callable(getattr(LLMClient, "generate"))
    assert callable(getattr(LLMClient, "stream"))
```

同时在测试中固定以下输入/输出约束：`generate()` 必须返回非空字符串；`stream()` 必须只产生字符串片段；批阅仍必须返回五个评分维度；学习路径必须允许模型不可用时规则回退。

- [ ] **Step 2: 运行测试，确认新增契约测试初始失败原因可解释**

Run:

```powershell
python -m pytest tests/test_spark_migration_inventory.py tests/test_llm.py -q
```

Expected: 新增测试先因当前 `LLMClient` 是 Protocol、没有 `__annotations__` 中的方法声明而失败；现有 `tests/test_llm.py` 的既有行为应保持通过。若失败来自导入或环境问题，先修正测试夹具，不修改生产逻辑。

- [ ] **Step 3: 根据实际数据建立盘点输出**

新增脚本 `scripts/inspect_training_sources.py`，读取 `data/documents/老师训练题库.json` 和指定 Markdown 目录，输出 JSON：文件数、样本数、题型计数、知识点计数、缺失答案数、疑似重复题数、非 UTF-8 或不可序列化记录数。脚本必须不修改源数据。

- [ ] **Step 4: 运行盘点并保存本地报告**

```powershell
python scripts/inspect_training_sources.py --json-out outputs/training_source_inventory.json
```

Expected: 命令返回 0，报告至少包含 `sources`、`question_count`、`type_counts`、`knowledge_point_counts`、`missing_answer_count`、`duplicate_count`；`outputs/` 属于本地产物，不将密钥或隐私数据写入报告。

---

### Task 2: 建立离散数学符号表与可审计推理规则

**Files:**
- Create: `backend/reasoning/symbols.py`
- Create: `backend/reasoning/rules.py`
- Create: `tests/test_discrete_math_symbols.py`
- Create: `data/training/symbol_rules.json`

- [ ] **Step 1: 先写失败测试**

```python
from backend.reasoning.symbols import normalize_symbols
from backend.reasoning.rules import validate_proof_structure


def test_normalize_symbols_preserves_required_discrete_math_symbols():
    result = normalize_symbols("A 属于 B，且 P 推出 Q")
    assert "∈" in result
    assert "→" in result


def test_validate_proof_structure_requires_conclusion_and_reasoning_step():
    result = validate_proof_structure({"known": "x", "conclusion": "y"})
    assert result.valid is False
    assert "reasoning_steps" in result.missing_fields
```

- [ ] **Step 2: 运行测试确认 RED**

```powershell
python -m pytest tests/test_discrete_math_symbols.py -q
```

Expected: FAIL with missing module/function，而不是因为 JSON 解析或路径错误。

- [ ] **Step 3: 实现最小符号规范化和证明结构校验**

`backend/reasoning/symbols.py` 提供：

```python
def normalize_symbols(text: str) -> str: ...
def symbol_table() -> dict[str, dict[str, str]]: ...
```

至少覆盖 `∀ ∃ ¬ ∧ ∨ → ↔ ∈ ∉ ⊆ ⊂ ∪ ∩ \ ᶜ R aRb f: A → B V E deg(v)`，并将中文同义词映射到统一符号，但不得破坏 LaTeX 命令。`backend/reasoning/rules.py` 提供：

```python
@dataclass(frozen=True)
class ProofValidation:
    valid: bool
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]

def validate_proof_structure(payload: Mapping[str, Any]) -> ProofValidation: ...
```

校验 `known`、`definitions_or_theorems`、`reasoning_steps`、`conclusion` 四段结构；规则只产生审计信息，不替代模型完成证明。

- [ ] **Step 4: 编写符号规则训练样本源**

`data/training/symbol_rules.json` 使用稳定结构：

```json
{
  "version": "discrete-math-symbols-v1",
  "symbols": [{"symbol": "∀", "meaning": "任意", "examples": ["∀x∈A"], "latex": "\\forall"}],
  "inference_rules": [{"name": "modus_ponens", "premises": ["P→Q", "P"], "conclusion": "Q"}],
  "proof_sections": ["known", "definitions_or_theorems", "reasoning_steps", "conclusion"]
}
```

- [ ] **Step 5: 运行测试确认 GREEN**

```powershell
python -m pytest tests/test_discrete_math_symbols.py -q
```

Expected: PASS。

---

### Task 3: 生成星火 MaaS 文本 SFT-LoRA JSONL 数据集

**Files:**
- Create: `scripts/build_spark_dataset.py`
- Create: `backend/training/dataset.py`
- Create: `tests/test_spark_dataset.py`
- Create: `data/training/README.md`
- Create at runtime only: `outputs/spark_dataset/train.jsonl`, `outputs/spark_dataset/validation.jsonl`, `outputs/spark_dataset/test.jsonl`

- [ ] **Step 1: 写数据生成器的失败测试**

```python
from backend.training.dataset import build_messages, split_records, validate_record


def test_build_messages_uses_system_user_assistant_roles():
    record = {"instruction": "解释命题", "answer": "命题是...", "knowledge_point": "命题逻辑"}
    sample = build_messages(record)
    assert [item["role"] for item in sample["messages"]] == ["system", "user", "assistant"]
    assert "命题逻辑" in sample["messages"][1]["content"]


def test_validate_record_rejects_missing_answer():
    assert validate_record({"instruction": "题目"}) == ["answer"]


def test_split_records_is_deterministic_and_disjoint():
    records = [{"id": str(i), "instruction": "q", "answer": "a"} for i in range(10)]
    parts = split_records(records, seed=17)
    assert set(parts["train"]).isdisjoint(parts["validation"])
    assert set(parts["train"]).isdisjoint(parts["test"])
    assert split_records(records, seed=17) == parts
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_spark_dataset.py -q
```

Expected: FAIL with missing `backend.training.dataset`。

- [ ] **Step 3: 实现数据标准化、去重、划分和 JSONL 校验**

`backend/training/dataset.py` 提供：

```python
def build_messages(record: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]: ...
def validate_record(record: Mapping[str, Any]) -> list[str]: ...
def split_records(records: Sequence[dict[str, Any]], seed: int = 20260903) -> dict[str, list[dict[str, Any]]]: ...
def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int: ...
```

系统消息固定说明离散数学角色、符号规范和证明四段结构；用户消息包含题型和知识点；助手消息保留高质量答案、批阅 JSON 或学习建议。所有输出使用 UTF-8、每行一个合法 JSON、无 NaN/Infinity。默认比例为 80/10/10，样本数不足时仍必须保证固定测试集至少 1 条且三集合不重叠。去重键使用归一化后的 `question + answer` 哈希，不能只按题目 ID 去重。

- [ ] **Step 4: 实现来源转换命令**

`scripts/build_spark_dataset.py` 必须支持：

```powershell
python scripts/build_spark_dataset.py `
  --questions data/documents/老师训练题库.json `
  --documents data/documents `
  --rules data/training/symbol_rules.json `
  --output outputs/spark_dataset `
  --seed 20260903
```

命令输出样本计数、题型计数、知识点计数和校验错误；有错误时退出码非 0，并不覆盖上一次有效数据集。

- [ ] **Step 5: 运行数据测试和生成器**

```powershell
python -m pytest tests/test_spark_dataset.py -q
python scripts/build_spark_dataset.py --questions data/documents/老师训练题库.json --documents data/documents --rules data/training/symbol_rules.json --output outputs/spark_dataset --seed 20260903
```

Expected: 测试 PASS；生成 `train.jsonl`、`validation.jsonl`、`test.jsonl`，并输出可复制到 MaaS 页面查看的统计摘要。

---

### Task 4: 重构 provider-neutral 配置并清理旧比赛主线文案

**Files:**
- Modify: `.env.example`
- Modify: `backend/chat/llm.py`
- Modify: `backend/api.py`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Create: `tests/test_provider_config.py`
- Keep unchanged: local `.env` and historical Qwen3.8-27B benchmark files

- [ ] **Step 1: 写配置行为测试**

```python
from backend.chat.llm import OpenAICompatibleLLM


def test_spark_provider_reads_only_spark_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "spark")
    monkeypatch.setenv("SPARK_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SPARK_API_KEY", "secret")
    monkeypatch.setenv("SPARK_MODEL", "published-qwen32b")
    client = OpenAICompatibleLLM()
    assert client.provider == "spark"
    assert client.base_url == "https://example.test/v1"
    assert client.model == "published-qwen32b"
    assert client.api_key == "secret"


def test_invalid_provider_fails_before_network(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    client = OpenAICompatibleLLM()
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        client.ensure_available()
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_provider_config.py -q
```

Expected: 新增属性/配置行为先失败。

- [ ] **Step 3: 实现配置解析和兼容别名**

配置字段改为：

```env
LLM_PROVIDER=spark
SPARK_BASE_URL=
SPARK_API_KEY=
SPARK_MODEL=
SPARK_VL_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2
LLM_MAX_TOKENS=768
LLM_ENABLE_THINKING=false
```

`OpenAICompatibleLLM` 保留 OpenAI-compatible HTTP 形态，但把字段统一成 `provider`、`base_url`、`api_key`、`model`；在迁移阶段允许读取现有 `OPENAI_*` 作为兼容回退，仅当 `LLM_PROVIDER` 未设置时使用，日志不得打印密钥前缀、长度或完整值。生产默认不启用 thinking，证明题通过任务级 prompt 控制输出长度，不让服务无界生成。

- [ ] **Step 4: 清理旧文案而不删除历史基线**

将页面和 API 健康信息从“Qwen3-8B + bge”改为“星火 MaaS + Qwen3-32B 文本 / Qwen3-VL-32B 视觉”；删除 `.env.example` 中 `Qwen/Qwen3-8B` 和 SiliconFlow 作为默认主线的配置。保留旧 benchmark 文件，并明确标记为历史本地基线。

- [ ] **Step 5: 运行配置、聊天和全量回归测试**

```powershell
python -m pytest tests/test_provider_config.py tests/test_llm.py tests/test_chat.py tests/test_chat_router.py -q
```

Expected: PASS；不得发生真实外网请求。

---

### Task 5: 实现星火文本 API 适配器和流式/错误契约

**Files:**
- Create: `backend/chat/providers/__init__.py`
- Create: `backend/chat/providers/spark.py`
- Modify: `backend/chat/llm.py`
- Create: `tests/test_spark_provider.py`

- [ ] **Step 1: 写 HTTP mock 的失败测试**

```python
import httpx
import pytest
from backend.chat.providers.spark import SparkTextClient


def test_spark_text_client_parses_openai_compatible_completion(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "结论"}}]})

    client = SparkTextClient(base_url="https://spark.test/v1", api_key="test-key", model="qwen32b", transport=httpx.MockTransport(handler))
    assert client.generate([{"role": "user", "content": "题目"}]) == "结论"


def test_spark_text_client_rejects_empty_choices():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    client = SparkTextClient(base_url="https://spark.test/v1", api_key="k", model="m", transport=transport)
    with pytest.raises(Exception):
        client.generate([{"role": "user", "content": "题目"}])
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_spark_provider.py -q
```

Expected: FAIL with missing provider module。

- [ ] **Step 3: 实现文本适配器**

`SparkTextClient` 构造函数必须接收 `base_url`、`api_key`、`model`、超时、重试次数和可注入 `httpx.Client`/transport；请求只使用运行时配置。`generate()` 解析 OpenAI-compatible `choices[0].message.content`；`stream()` 解析 SSE 的 `data:` 行、跳过 `[DONE]`、兼容字符串或对象形式的 delta；网络超时、429、5xx 可按现有退避策略重试，400/401/403 直接转换为明确的 `LLMUnavailableError`，错误消息不能包含密钥。

- [ ] **Step 4: 将统一客户端委托到 provider**

`OpenAICompatibleLLM` 根据 `LLM_PROVIDER=spark` 创建 `SparkTextClient`，业务层仍只调用：

```python
llm.generate(messages)
llm.stream(messages)
```

批阅和学习路径不得直接 import `SparkTextClient`，避免供应商耦合。

- [ ] **Step 5: 运行适配器和全量后端测试**

```powershell
python -m pytest tests/test_spark_provider.py tests/test_llm.py tests/test_chat.py tests/test_grading.py tests/test_learning_path.py -q
```

Expected: PASS。

---

### Task 6: 增加 Qwen3-VL 视觉识别适配器和图片接口

**Files:**
- Create: `backend/vision/__init__.py`
- Create: `backend/vision/models.py`
- Create: `backend/vision/spark_vl.py`
- Create: `backend/vision/router.py`
- Modify: `backend/api.py`
- Create: `tests/test_vision_api.py`

- [ ] **Step 1: 写视觉请求/响应和 mock 调用测试**

```python
from fastapi.testclient import TestClient
from backend.vision.models import VisionParseResponse


def test_vision_response_has_question_answer_latex_symbols_and_warnings():
    response = VisionParseResponse.model_validate({
        "question_text": "证明 A⊆B",
        "student_answer": "...",
        "latex": ["A\\subseteq B"],
        "symbols": ["⊆"],
        "confidence": 0.91,
        "warnings": [],
    })
    assert response.confidence == 0.91


def test_vision_endpoint_rejects_non_image_upload(client):
    response = client.post("/api/vision/parse", files={"file": ("note.txt", b"not image", "text/plain")})
    assert response.status_code == 415
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_vision_api.py -q
```

Expected: FAIL with missing `backend.vision` modules或路由。

- [ ] **Step 3: 实现视觉数据模型和调用边界**

`VisionParseResponse` 固定字段：

```python
class VisionParseResponse(BaseModel):
    question_text: str
    student_answer: str
    latex: list[str]
    symbols: list[str]
    confidence: float = Field(ge=0, le=1)
    warnings: list[str]
    elapsed_ms: int | None = Field(default=None, ge=0)
```

`SparkVisionClient` 使用 `SPARK_VL_MODEL`，输入采用平台实际支持的图像消息格式；由于星火页面/API 具体字段必须以用户提供的接口文档为准，客户端把“图片编码 + prompt”封装在一个 provider 边界内，响应统一转换为上述结构，并在模型返回非 JSON 时执行一次严格修复或返回带 warning 的可审计结果。

- [ ] **Step 4: 实现图片上传接口和大小/类型限制**

`POST /api/vision/parse` 接收 multipart 图片，限制 `image/png`、`image/jpeg`、`image/webp`，限制 10 MiB；不保存原图到 Git 跟踪目录。成功响应必须包含识别耗时；模型未配置时返回 503；解析失败返回 422。对图片内容只传给视觉客户端，不把文件路径拼入 prompt。

- [ ] **Step 5: 运行视觉测试和 API 启动检查**

```powershell
python -m pytest tests/test_vision_api.py tests/test_chat_router.py -q
python -c "from backend.api import app; print(sorted(route.path for route in app.routes if route.path.startswith('/api/vision')))"
```

Expected: PASS；输出包含 `/api/vision/parse`。

---

### Task 7: 将视觉结果接入问答、自测和批阅链路

**Files:**
- Modify: `backend/chat/models.py`
- Modify: `backend/chat/router.py`
- Modify: `backend/chat/service.py`
- Modify: `backend/grading/models.py`
- Modify: `backend/grading/router.py`
- Modify: `backend/grading/service.py`
- Create: `tests/test_multimodal_flow.py`

- [ ] **Step 1: 写端到端 mock 测试**

```python

def test_image_question_is_parsed_then_sent_as_text_to_reasoning_client():
    vision = FakeVisionClient(question_text="证明 A⊆B", student_answer="由定义可得...", latex=["A\\subseteq B"], symbols=["⊆"])
    text = RecordingLLM(answer="证明分为已知、定义、推理和结论四步。")
    result = solve_uploaded_question(vision=vision, llm=text, image_bytes=b"png")
    assert result.question_text == "证明 A⊆B"
    assert "A⊆B" in text.messages[0]["content"]


def test_grading_receives_vision_student_answer_and_preserves_user_id():
    result = grade_uploaded_answer(user_id=7, question_id="proof-1", parsed_answer="由定义可得...")
    assert result.user_id == 7
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_multimodal_flow.py -q
```

Expected: FAIL with missing orchestration functions/fields。

- [ ] **Step 3: 实现最小编排层**

新增小型纯函数或 service 方法，把视觉输出转换为现有文本接口输入：

```python
def vision_to_problem_context(parsed: VisionParseResponse) -> str: ...
```

问答请求支持可选图片字段；批阅请求支持 `image` 或已解析的 `student_answer`，但最终传入现有评分服务的仍是明确文本。批阅记录继续使用当前用户、当前题目和既有 `grading_results` 落库规则；任何视觉低置信度或 warning 都必须进入批阅依据或 `needs_human_review`。

- [ ] **Step 4: 接入自测页面需要的 API 契约**

保留现有自测和批阅 URL，不新建重复业务；新增可选字段：`image_parse_result`、`latex`、`symbols`、`vision_warnings`。前端在识图完成前显示加载状态，识别失败允许用户编辑/粘贴文本后继续，不阻塞文本题。

- [ ] **Step 5: 运行相关业务回归测试**

```powershell
python -m pytest tests/test_multimodal_flow.py tests/test_practice.py tests/test_grading.py tests/test_learning_path.py -q
```

Expected: PASS，既有纯文本路径结果不变。

---

### Task 8: 固定 prompt、JSON 输出和上下文控制

**Files:**
- Modify: `backend/chat/context.py`
- Modify: `backend/chat/reasoning.py`
- Modify: `backend/grading/prompts.py`
- Create: `backend/chat/prompt_policy.py`
- Create: `tests/test_prompt_policy.py`

- [ ] **Step 1: 写 prompt 策略测试**

```python
from backend.chat.prompt_policy import build_math_system_prompt


def test_proof_prompt_requires_structured_short_answer():
    prompt = build_math_system_prompt(task="proof", knowledge_context="定义：...")
    assert "已知条件" in prompt
    assert "关键推理步骤" in prompt
    assert "结论" in prompt
    assert "不要输出无界思维过程" in prompt


def test_grading_prompt_requires_json_only_and_five_dimensions():
    prompt = build_math_system_prompt(task="grading", knowledge_context="")
    for name in ["conclusion_correctness", "key_reasoning_steps", "logical_rigor", "definition_theorem_use", "expression_notation"]:
        assert name in prompt
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_prompt_policy.py -q
```

Expected: FAIL until策略模块和调用点存在。

- [ ] **Step 3: 实现上下文预算策略**

按任务类型设置上限：概念 512、计算 768、证明 1024、批阅 768；知识库上下文先截断/压缩再拼接历史消息，历史消息保留最近轮次并避免重复系统提示。默认 `temperature`、`top_p`、`max_tokens` 由环境变量读取；不要求模型输出隐藏思维链，只要求可审计的关键步骤摘要。

- [ ] **Step 4: 加入结构化输出解析与一次修复**

批阅响应继续使用现有 Pydantic/guardrail 校验；若模型返回 Markdown JSON，先去围栏再解析；只允许一次修复请求，修复失败按当前 `InvalidGradingOutputError` 路径处理并记录人工复核。问答可返回 Markdown，但证明必须包含四段结构和符号规范。

- [ ] **Step 5: 运行 prompt、批阅和聊天回归测试**

```powershell
python -m pytest tests/test_prompt_policy.py tests/test_grading.py tests/test_grading_guardrails.py tests/test_chat.py -q
```

Expected: PASS。

---

### Task 9: 星火 MaaS 训练任务说明、发布 API 配置和运行文档

**Files:**
- Create: `docs/spark-maas-training-guide.md`
- Modify: `data/training/README.md`
- Modify: `.env.example`
- Create: `scripts/check_spark_config.py`
- Create: `tests/test_spark_config_check.py`

- [ ] **Step 1: 写配置检查测试**

```python

def test_config_check_reports_missing_required_spark_values(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "spark")
    monkeypatch.delenv("SPARK_BASE_URL", raising=False)
    result = check_config()
    assert result.ok is False
    assert "SPARK_BASE_URL" in result.missing


def test_config_check_never_prints_secret(monkeypatch, capsys):
    monkeypatch.setenv("SPARK_API_KEY", "super-secret")
    check_config()
    assert "super-secret" not in capsys.readouterr().out
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_spark_config_check.py -q
```

Expected: FAIL with missing checker。

- [ ] **Step 3: 实现本地配置检查**

`check_spark_config.py` 检查 `LLM_PROVIDER`、`SPARK_BASE_URL`、`SPARK_API_KEY`、`SPARK_MODEL`；视觉链路启用时再检查 `SPARK_VL_MODEL`。输出只列变量名和状态，不输出值。支持 `--require-vl` 和 `--json`。

- [ ] **Step 4: 编写 MaaS 操作手册**

`docs/spark-maas-training-guide.md` 明确写出：

1. 在星火 MaaS 模型广场确认 Qwen3-32B 的 SFT/SFT-LoRA 能力；
2. 上传 `train.jsonl` 和 `validation.jsonl`；
3. 配置训练超参并发起任务；
4. 记录任务 ID、基座版本、数据集哈希、训练参数和验证指标；
5. 发布文本模型 API，把资源标识填入本地 `.env`；
6. 配置 Qwen3-VL-32B-Instruct 视觉 API；
7. 用健康检查和固定测试集验证；
8. API 具体认证字段以平台当前页面/接口文档为准，本文只定义仓库侧环境变量边界。

不得把平台密钥写入文档示例，示例只使用 `<set-locally>`。

- [ ] **Step 5: 运行配置检查**

```powershell
python scripts/check_spark_config.py --json
```

Expected: 未配置真实星火环境时返回非 0并清楚列出缺少变量；配置后返回 0且无密钥泄露。

---

### Task 10: 建立固定能力评测与 30 秒性能压测

**Files:**
- Create: `scripts/benchmark_spark_multimodal.py`
- Create: `tests/test_spark_benchmark.py`
- Create: `docs/spark-benchmark-report-template.md`
- Keep: `scripts/benchmark_qwen38_service.py`, `scripts/benchmark_grading_e2e.py`

- [ ] **Step 1: 写 benchmark 记录格式测试**

```python

def test_benchmark_record_contains_latency_and_model_identity():
    record = make_record(name="证明题问答", model="published-qwen32b", elapsed_seconds=12.3, output_tokens=240)
    assert record["model"] == "published-qwen32b"
    assert record["first_token_seconds"] >= 0
    assert record["elapsed_seconds"] == 12.3
    assert record["over_30s"] is False


def test_benchmark_marks_failed_request_not_as_pass():
    record = make_error_record(name="证明题批阅", model="published-qwen32b", error="HTTP 400")
    assert record["status"] == "error"
    assert record["over_30s"] is True
```

- [ ] **Step 2: 运行 RED 测试**

```powershell
python -m pytest tests/test_spark_benchmark.py -q
```

Expected: FAIL until benchmark schema exists。

- [ ] **Step 3: 实现固定测试集和计时器**

脚本固定覆盖至少：概念问答、计算题问答、证明题问答、计算题批阅、证明题批阅、题目图片识别、手写答案图片识别。每次记录：`provider`、`model`、`vl_model`、时间戳、输入/输出 token（若 API 提供）、首字延迟、总延迟、重试次数、HTTP 状态、错误、`over_30s`。首字延迟用流式首个非空 delta 时间计算；非流式请求 `first_token_seconds` 等于总延迟并明确标记 `streamed=false`。

- [ ] **Step 4: 实现在线集成运行命令**

```powershell
python scripts/benchmark_spark_multimodal.py `
  --base-url $env:SPARK_BASE_URL `
  --model $env:SPARK_MODEL `
  --vl-model $env:SPARK_VL_MODEL `
  --cases data/benchmark/spark_cases.jsonl `
  --output outputs/spark_benchmark/latest.json
```

脚本默认不重试 400/401/403；对 429/5xx 记录重试并保留每次尝试。30 秒目标按“完整响应”判断，不能把只有首字输出的请求判为通过。

- [ ] **Step 5: 运行离线 schema 测试，再运行真实 API 测试**

```powershell
python -m pytest tests/test_spark_benchmark.py -q
python scripts/benchmark_spark_multimodal.py --help
```

配置好星火模型后再执行真实压测，并把结果写入 `outputs/`；报告模板必须分别统计文本模型、视觉模型和端到端链路，禁止在无真实数据时声称 30 秒达标。

---

### Task 11: 全量回归、文档核查和交付前安全检查

**Files:**
- Modify: `README.md`（若仓库实际 README 存在）
- Modify: `docs/spark-maas-training-guide.md`
- Create: `tests/test_no_secret_or_8b_default.py`

- [ ] **Step 1: 写默认配置安全测试**

```python

def test_env_example_has_no_old_8b_or_siliconflow_default():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "Qwen/Qwen3-8B" not in text
    assert "SiliconFlow" not in text


def test_tracked_files_do_not_contain_secret_assignment_patterns():
    for path in tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "SPARK_API_KEY=sk-" not in text
        assert "API_SECRET=" not in text
```

- [ ] **Step 2: 运行最终测试**

```powershell
python -m pytest -q
python -m compileall backend scripts -q
```

Expected: 全部既有测试和新增测试通过；允许已有、与本次无关的依赖警告，但不能有失败。

- [ ] **Step 3: 检查差异范围**

```powershell
git diff -- .env.example backend scripts tests docs data/training frontend
 git status --short
```

确认没有修改 `.env`、没有删除历史 27B 基线、没有将 `outputs/` 中的密钥或原始图片纳入提交候选；本阶段仍不提交、不推送 GitHub。

- [ ] **Step 4: 形成交付清单**

交付记录必须包含：数据集统计、符号表版本、MaaS 训练任务 ID/基座版本/数据集哈希、发布模型标识、视觉模型标识、全量测试结果、真实压测 JSON 路径、超过 30 秒的案例及原因、当前回退策略。只有在真实 API 测试完成后，才可在竞赛材料中写“证明题 ≤30 秒达标”。

---

## 依赖顺序

```text
Task 1 ─┬─> Task 2 ─> Task 3 ─> Task 9
        ├─> Task 4 ─> Task 5 ─> Task 8
        └─> Task 6 ─> Task 7 ─> Task 10
Task 11 在所有任务完成后执行
```

实现时优先完成 Task 1–5，先获得可调用的文本模型链路；再完成 Task 6–7 视觉链路；最后用 Task 8–11 做上下文、训练发布和真实性能验收。

## 验收标准

- 星火 MaaS 训练集、验证集、固定测试集均为合法 UTF-8 JSONL，集合不重叠，符号规范一致；
- 后端业务只依赖统一 `generate/stream` 接口，文本模型和视觉模型均可通过环境变量替换；
- 图片题目和手写答案能够转换为 `question_text`、`student_answer`、`latex`、`symbols`、`confidence`、`warnings`；
- 批阅仍保留五维评分、错误类型、依据、人工复核和用户隔离；
- 上下文长度、最大输出、thinking 和重试均可配置；
- 固定测试集完整记录模型、首字延迟、总延迟、token、错误和重试；
- 真实星火 API 结果证明后，证明题、计算题问答和批阅分别统计是否达到 30 秒；
- 未配置星火或模型异常时，系统返回可理解的 503/回退信息，不泄露密钥；
- 当前阶段不提交、不推送 GitHub。

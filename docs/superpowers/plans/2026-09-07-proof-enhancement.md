# 通用证明增强与低延迟自检 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提升离散数学未见证明题的严谨性、定理条件核验和教学表达，同时保持默认单次模型调用、30 秒内完成率和低延迟特性。

**Architecture:** 在现有 `backend.reasoning` 规则层增加轻量、可审计的证明质量检查；在现有推理提示中加入紧凑的通用证明协议和领域约束；在 `ChatService` 中把质量检查作为本地快速门控，仅对多个明确风险信号同时出现的答案触发一次定向修订。普通回答只走一次模型调用，修订失败则保留原答案并返回风险元数据。

**Tech Stack:** Python 3.11/3.13、FastAPI service layer、pytest、现有 `backend.reasoning` 规则与 Spark OpenAI-compatible LLM adapter。

---

## 文件边界

- **Modify:** `backend/reasoning/rules.py`：新增证明质量风险的数据结构和纯本地检查函数；保留现有 `validate_proof_structure` 的兼容行为。
- **Modify:** `backend/reasoning/service.py`：扩展证明/推导提示协议和题型专项提示；不增加模型调用。
- **Modify:** `backend/chat/reasoning.py`：将质量检查结果纳入现有推理元数据，并提供统一的低延迟风险门控输入。
- **Modify:** `backend/chat/service.py`：在同步和流式调用链中接入质量检查；最多执行一次定向修订；记录阶段耗时。
- **Create:** `tests/test_proof_quality.py`：覆盖通用结构、定理条件、特殊案例泛化、图论/四色定理风险信号。
- **Modify:** `tests/test_reasoning.py`：覆盖新的提示协议和增强元数据。
- **Modify:** `tests/test_chat.py`：覆盖同步/流式调用的单次默认路径、风险修订路径和修订失败回退。
- **Create:** `scripts/evaluate_proof_enhancement.py`：对本地回归题和未见题 JSONL 执行调用/结果记录；脚本不内置题目答案，不输出密钥。
- **Create:** `data/evaluation/proof_enhancement_cases.jsonl`：按题型与错误诱导类型准备小型可审计评测集，不复制现有 112 题答案。
- **Create:** `docs/evaluation/proof_enhancement_report.md`：记录优化前后正确性、风险指标和延迟；仅在真实评测后填写结果。

---

### Task 1: 建立证明质量检查的失败测试

**Files:**
- Create: `tests/test_proof_quality.py`
- Modify: `tests/test_reasoning.py`

- [ ] **Step 1: 写本地纯函数的失败测试**

在 `tests/test_proof_quality.py` 中先导入尚不存在的接口，并固定以下行为：

```python
from backend.reasoning.rules import inspect_proof_quality


def test_quality_accepts_complete_generic_proof():
    result = inspect_proof_quality(
        "已知：G为有限图。目标：证明结论。\n"
        "由定义，...\n根据握手定理，且已验证其条件，...\n"
        "因此得到目标，证毕。",
        "证明一个关于有限图的命题",
    )
    assert result.checked is True
    assert result.revision_needed is False


def test_quality_flags_example_as_general_proof():
    result = inspect_proof_quality(
        "取一个例子 K4，给它染四种颜色，所以四色定理成立。",
        "证明每个平面图都可以用四种颜色着色",
    )
    assert result.revision_needed is True
    assert "example" in result.risk_codes


def test_quality_flags_hamiltonian_component_overclaim():
    result = inspect_proof_quality(
        "删除顶点后，哈密顿回路的每一段就是一个连通分支。",
        "证明删除顶点后图的连通分支数满足必要条件",
    )
    assert result.revision_needed is True
    assert "hamiltonian" in result.risk_codes


def test_quality_flags_unverified_theorem_conditions():
    result = inspect_proof_quality(
        "由某定理立即可知结论，因此证毕。",
        "证明给定命题",
    )
    assert result.revision_needed is True
    assert "theorem_conditions" in result.risk_codes
```

同时在 `tests/test_reasoning.py` 添加断言：证明题提示包含“目标、依据、逐步推导、自检、结论”要求；普通题提示仍为空/不启用。

- [ ] **Step 2: 运行失败测试确认缺口**

运行：

```powershell
python -m pytest tests/test_proof_quality.py tests/test_reasoning.py -q
```

预期：`tests/test_proof_quality.py` 因 `inspect_proof_quality` 未定义而失败；现有旧测试结果作为回归基线记录，不修改旧断言来掩盖失败。

---

### Task 2: 实现本地证明质量检查器

**Files:**
- Modify: `backend/reasoning/rules.py`
- Test: `tests/test_proof_quality.py`

- [ ] **Step 1: 增加可审计结果类型和保守规则**

在 `backend/reasoning/rules.py` 中新增：

```python
@dataclass(frozen=True)
class ProofQuality:
    checked: bool
    revision_needed: bool
    risk_codes: tuple[str, ...]
    section_presence: dict[str, bool]
    detail: str
```

实现：

```python
def inspect_proof_quality(answer: str, question: str) -> ProofQuality:
    """识别明显证明风险；不声称判断完整数学正确性。"""
```

规则必须满足：

- 空答案或普通非证明题返回 `checked=False`、`revision_needed=False`；
- 检查目标/已知或定义/推理依据/结论四类内容是否出现；
- 只有“证明/定理/推导/反证/构造/证明是否成立”等题目才启用；
- “一个例子、取 K4、该图可着色，所以所有平面图……”等在一般性问题中的组合信号加入 `example`；
- 哈密顿/删除顶点题中出现“每个连通分支都是路径”等过强表述加入 `hamiltonian`；
- 出现“由某定理立即/显然/可知”而没有定理名或条件核验信号加入 `theorem_conditions`；
- 缺少关键结构且同时存在高风险词时才将 `revision_needed=True`，避免所有简洁答案都触发第二次调用；
- 不做网络请求、不调用模型、不引入重型依赖，确保本地检查为常数级文本扫描。

- [ ] **Step 2: 运行质量测试**

运行：

```powershell
python -m pytest tests/test_proof_quality.py -q
```

预期：新增质量检查测试全部通过。

- [ ] **Step 3: 运行现有推理测试**

运行：

```powershell
python -m pytest tests/test_reasoning.py -q
```

预期：原有推理、符号和证明计划测试全部通过。

- [ ] **Step 4: 提交独立变更**

```powershell
git add backend/reasoning/rules.py tests/test_proof_quality.py tests/test_reasoning.py
git commit -m "feat: add lightweight proof quality checks"
```

---

### Task 3: 扩展通用证明提示协议

**Files:**
- Modify: `backend/reasoning/service.py`
- Modify: `backend/chat/service.py`
- Test: `tests/test_reasoning.py`

- [ ] **Step 1: 写提示内容失败断言**

为证明、推导和反例题增加断言，要求生成提示包含以下语义关键词：目标、已知/定义、证明策略、逐步依据、自检、结论；并包含禁止虚构定理、特殊案例不能替代一般证明的约束。测试只检查规范化后的语义片段，不依赖具体中文标点。

- [ ] **Step 2: 实现紧凑提示片段**

在 `backend/reasoning/service.py` 的 `build_reasoning_prompt`/相关格式化函数中集中生成一个短协议，内容采用以下固定结构：

```text
证明任务输出协议：
1. 目标：准确复述要证明/构造/反驳的命题。
2. 已知与定义：只使用题目给出的条件，写明关键定义。
3. 策略与依据：说明证明方法；使用定理时先核对其条件。
4. 推导：逐步给出可核验的中间结论，不跳过关键蕴含。
5. 自检：检查符号、边界条件、反例和“特例是否被误当一般结论”。
6. 结论：回扣目标；一般命题不能只靠一个例子证明。
禁止虚构定理、来源和条件；不输出内部思维链，只输出简洁可核验的证明步骤。
```

按关键词追加专项约束：

- 哈密顿图：区分回路、路径、连通分支，不能把删除顶点后的各路径直接等同于各连通分支；
- 四色定理：区分平面图/地图、顶点着色/区域着色；`K4` 例子不能证明一般定理；
- 集合/关系/逻辑：检查量词范围、蕴含方向、包含关系方向和符号一致性；
- 代数结构：核对封闭性、单位元、逆元、有限性和阶等前提。

协议保持短小，不要求模型展示隐藏思维过程，不增加模型调用。

- [ ] **Step 3: 运行提示回归测试**

运行：

```powershell
python -m pytest tests/test_reasoning.py -q
```

预期：提示协议测试和全部既有测试通过。

- [ ] **Step 4: 提交提示变更**

```powershell
git add backend/reasoning/service.py backend/chat/service.py tests/test_reasoning.py
git commit -m "feat: strengthen generic proof prompting"
```

---

### Task 4: 接入低延迟自检与一次性定向修订

**Files:**
- Modify: `backend/chat/reasoning.py`
- Modify: `backend/chat/service.py`
- Modify: `backend/chat/models.py`（仅当现有响应模型无法承载质量元数据时）
- Modify: `tests/test_chat.py`

- [ ] **Step 1: 为调用链写失败测试**

在 `tests/test_chat.py` 增加三个场景：

```python
def test_chat_uses_one_model_call_when_quality_check_is_clean():
    response = service.chat(proof_request)
    assert llm.calls == 1
    assert response.reasoning["quality"]["revision_needed"] is False


def test_chat_repairs_only_when_quality_risk_is_high():
    response = service.chat(proof_request_with_bad_answer)
    assert llm.calls == 2
    assert response.reasoning["quality"]["repair_attempted"] is True


def test_chat_returns_original_answer_when_repair_fails():
    response = service.chat(proof_request_with_unstable_llm)
    assert response.content
    assert response.reasoning["quality"]["repair_fallback"] is True
```

测试夹具必须使用现有 fake LLM/repository，不访问真实 Spark API；严格断言最多两次 `generate`，并覆盖修订文本包含风险原因而非整题答案。

- [ ] **Step 2: 扩展增强元数据**

在 `backend/chat/reasoning.py` 中引入 `inspect_proof_quality`，新增统一函数：

```python
def inspect_answer_quality(answer: str, question: str) -> dict[str, Any] | None:
    quality = inspect_proof_quality(answer, question)
    if not quality.checked:
        return None
    return asdict(quality)
```

保留现有 `check_symbol_fidelity` 和 `check_natural_deduction_validity` 的公开行为，避免影响队友已有调用。

- [ ] **Step 3: 调整同步调用链**

在 `ChatService.chat` 中：

1. 主模型调用后执行符号、自然演绎和证明质量三类本地检查；
2. 只有现有检查失败或 `quality.revision_needed=True` 时触发一次修订；
3. 修订消息只列出机器检测到的风险和简短修订要求；
4. 修订抛出异常、返回空答案或超时则使用主答案；
5. 将 `repair_attempted`、`repair_fallback`、风险代码和检查耗时写入 reasoning 元数据；
6. 不增加默认路径模型调用。

- [ ] **Step 4: 调整流式调用链**

在 `stream_chat` 中复用同一个质量门控和修订逻辑；只有在主答案完整收集后才决定是否修订。保持已有 `meta`/`delta`/`done` 事件协议不变，修订过程不得产生两份最终答案；修订失败时发送原答案完成事件。

- [ ] **Step 5: 运行聊天回归测试**

运行：

```powershell
python -m pytest tests/test_chat.py tests/test_chat_router.py -q
```

预期：聊天同步、流式、路由和回退测试全部通过，且新增测试证明干净路径只有一次模型调用。

- [ ] **Step 6: 提交调用链变更**

```powershell
git add backend/chat/reasoning.py backend/chat/service.py backend/chat/models.py tests/test_chat.py
git commit -m "feat: add gated proof answer repair"
```

---

### Task 5: 建立不针对固定答案的评测集与报告

**Files:**
- Create: `data/evaluation/proof_enhancement_cases.jsonl`
- Create: `scripts/evaluate_proof_enhancement.py`
- Create: `docs/evaluation/proof_enhancement_report.md`

- [ ] **Step 1: 准备分层题目集**

JSONL 每行只保存 `id`、`category`、`question`、`expected_checks`，不保存模型答案。至少覆盖：

- 集合恒等式与包含关系；
- 关系的自反/对称/传递/等价性；
- 命题逻辑量词与反例；
- 连通性、欧拉/哈密顿性；
- 平面图、`K4` 着色与四色定理边界；
- 群与子群构造；
- 错误定理条件诱导题；
- 反例构造题。

题目不得直接复用当前 112 题的完整文本或答案。

- [ ] **Step 2: 编写离线/在线兼容评测脚本**

脚本接受 `--input`、`--output`、`--provider` 参数；默认只执行本地提示与检查模拟，不读取或打印 `.env` 中密钥。真实调用模式通过现有 `OpenAICompatibleLLM`，逐题记录 `latency_seconds`、`answer`、`reasoning`，遇到单题异常继续下一题并保存 `error`。

- [ ] **Step 3: 编写报告模板**

报告必须分开记录：人工正确性/严谨性、符号一致性、定理条件核验率、修订触发率、修订成功率、平均/P95 延迟和 30 秒完成率。不得把提示增强结果表述成模型参数微调效果。

- [ ] **Step 4: 运行脚本的本地校验**

运行：

```powershell
python scripts/evaluate_proof_enhancement.py --help
python -m pytest tests/test_proof_quality.py tests/test_reasoning.py tests/test_chat.py -q
```

预期：CLI 能显示参数帮助；全部相关测试通过。

- [ ] **Step 5: 提交评测工具**

```powershell
git add data/evaluation/proof_enhancement_cases.jsonl scripts/evaluate_proof_enhancement.py docs/evaluation/proof_enhancement_report.md
git commit -m "test: add proof enhancement evaluation harness"
```

---

### Task 6: 全量验证与性能门槛

**Files:**
- Modify: `docs/evaluation/proof_enhancement_report.md`（仅填入实际结果）
- No code changes unless a test exposes a regression.

- [ ] **Step 1: 运行完整测试**

```powershell
python -m pytest tests algorithm_tools -q
```

预期：所有既有测试和新增测试通过；记录警告但不把已有弃用警告当失败。

- [ ] **Step 2: 运行未见题评测**

使用真实当前 Spark 模型运行：

```powershell
python scripts/evaluate_proof_enhancement.py --input data/evaluation/proof_enhancement_cases.jsonl --output data/evaluation/proof_enhancement_results.json
```

不在终端输出 API Key。人工抽检重点查看：哈密顿性、四色定理边界、定理条件、反例和证明回扣目标。

- [ ] **Step 3: 检查速度门槛**

验收：默认路径平均延迟不超过优化前基线的 1.25 倍，P95 和 30 秒完成率单独记录；低风险题不应触发修订。若质量提高但延迟超门槛，优先收紧修订门控，不通过删减正确步骤来换速度。

- [ ] **Step 4: 做最终安全检查**

```powershell
git diff --check
Select-String -Path data\evaluation\*.json,docs\evaluation\*.md,scripts\*.py,backend\**\*.py -Pattern 'sk-[A-Za-z0-9]{20,}|api[_-]?key\s*=' -CaseSensitive:$false
```

预期：无新增密钥模式；测试结果和报告中的数字均来自实际运行。

- [ ] **Step 5: 提交最终报告**

```powershell
git add docs/evaluation/proof_enhancement_report.md
git commit -m "docs: record proof enhancement verification"
```

---

## 完成定义

- 新增通用质量检查和证明提示协议，不针对固定题目写答案规则；
- 默认低风险回答保持一次模型调用；
- 高风险回答最多一次定向修订，失败可回退；
- 同步与流式聊天协议均保持兼容；
- 既有全量测试通过；
- 未见题评测有可审计结果，且平均/P95 延迟、30 秒完成率满足设计门槛；
- 没有新增 API Key 或其它敏感配置进入 Git。

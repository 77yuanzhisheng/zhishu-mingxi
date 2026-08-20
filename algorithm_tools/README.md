# 离散数学算法工具服务

本模块提供可独立运行、可被总后端挂载的离散数学算法工具。扩展工具不依赖大模型，结果由确定性算法计算。

## 已实现功能

原有兼容接口：

- `POST /tools/truth-table`：真值表生成
- `POST /tools/relation-properties`：关系性质判断

本阶段新增接口：

- `POST /tools/formula-simplify`：命题公式化简（最小析取范式）
- `POST /tools/normal-forms`：主析取范式和主合取范式
- `POST /tools/set-operation`：集合运算
- `POST /tools/hasse-diagram`：哈斯图 JSON
- `POST /tools/dijkstra`：Dijkstra 最短路径
- `POST /tools/bipartite`：二分图判定及划分
- `POST /tools/code-generate`：Python/C 算法代码生成

所有工具都支持以下统一结构：

```json
{
  "params": {}
}
```

统一返回：

```json
{
  "result": {},
  "steps": ["计算步骤"],
  "explanation": "算法说明"
}
```

## 安装和启动

在项目根目录执行：

```powershell
pip install -r algorithm_tools\requirements.txt
uvicorn algorithm_tools.main:app --reload --port 8010
```

打开接口文档：

```text
http://127.0.0.1:8010/docs
```

健康检查：

```text
GET http://127.0.0.1:8010/health
```

## 新增接口示例

### 1. 命题公式化简

```json
POST /tools/formula-simplify
{
  "params": {
    "expression": "(p and q) or (p and not q)"
  }
}
```

结果中的 `simplified` 为 `p`。化简采用真值表和 Quine-McCluskey 方法，目前最多支持 10 个变量。

### 2. 主范式转换

```json
POST /tools/normal-forms
{
  "params": {
    "expression": "p -> q"
  }
}
```

返回 `principal_dnf`、`principal_cnf`、`minterm_indices` 和 `maxterm_indices`。

逻辑公式支持：

```text
not, and, or, xor
~, !, &, |, ^
->, =>
<->, <=>
true, false
```

### 3. 集合运算

```json
POST /tools/set-operation
{
  "params": {
    "set_a": [1, 2, 3],
    "set_b": [3, 4],
    "operation": "union"
  }
}
```

`operation` 可取：

```text
union
intersection
difference
symmetric_difference
cartesian_product
power_set
complement
```

中文名称“并集、交集、差集、对称差、笛卡尔积、幂集、补集”也可使用。计算补集时还要传 `universal_set`。幂集最多支持 12 个不同元素，防止返回结果过大。

### 4. 哈斯图生成

```json
POST /tools/hasse-diagram
{
  "params": {
    "elements": [1, 2, 3, 6, 12],
    "relation_type": "divisibility"
  }
}
```

`relation_type` 支持：

```text
divisibility  根据正整数元素自动构造整除关系
less_equal    根据数值元素自动构造小于等于关系
subset        把每个数组视为集合，自动构造子集关系
explicit      使用 relation 有序对或 matrix 手动定义关系
```

自动模式会在 `elements` 改变后重新计算关系，不需要同步修改旧矩阵。`explicit` 模式下，也可以用与 `elements` 顺序对应的 `matrix` 代替 `relation`。接口会验证偏序关系，并进行传递约简，返回：

- `nodes`：节点 ID、显示文字和层级
- `edges`：哈斯图覆盖边
- `levels`：按层分组的节点，可直接交给 ECharts 等前端组件

### 5. Dijkstra 最短路径

```json
POST /tools/dijkstra
{
  "params": {
    "edges": [
      ["A", "B", 2],
      ["A", "C", 7],
      ["B", "C", 1]
    ],
    "start": "A",
    "end": "C",
    "directed": false
  }
}
```

返回是否可达、最短路径、距离、访问顺序和各顶点最终距离。Dijkstra 不接受负权边。

边也可以写成对象：

```json
{
  "source": "A",
  "target": "B",
  "weight": 2
}
```

### 6. 二分图判定

```json
POST /tools/bipartite
{
  "params": {
    "matrix": [
      [0, 1, 0, 1],
      [1, 0, 1, 0],
      [0, 1, 0, 1],
      [1, 0, 1, 0]
    ]
  }
}
```

使用广度优先搜索二染色。是二分图时返回左右划分；不是时返回第一条冲突边。非对称邻接矩阵按无向图处理。

### 7. Python/C 代码生成

```json
POST /tools/code-generate
{
  "params": {
    "problem": "给定 A-B 权重2、A-C权重7、B-C权重1，求 A 到 C 的最短路径并输出路径和距离",
    "language": "python",
    "use_llm": true
  }
}
```

`language` 可取 `python` 或 `c`。默认会自动识别问题类型，并调用已配置的 Qwen 根据完整题意生成代码，不再要求前端选择固定模板。模型生成的 Python 会进行语法检查；模型暂时不可用时，已支持的题型自动回退到可靠模板。

API 调试时仍可显式传入可选的 `problem_type`：

```text
truth_table
relation_properties
set_operation
dijkstra
bipartite
hasse
general
```

返回的 `generation_mode` 为 `qwen` 或 `verified_template`，用于区分按题生成和离线模板回退。设置 `use_llm: false` 可以强制使用离线模板。

## 原有接口兼容性

现有前端仍然可以按旧格式调用：

```json
POST /tools/truth-table
{
  "expression": "p -> q"
}
```

```json
POST /tools/relation-properties
{
  "matrix": [[1, 0], [0, 1]]
}
```

这两个接口会根据请求格式返回结果：旧请求返回旧响应，新 `{ "params": ... }` 请求返回统一的 `result/steps/explanation` 响应，因此不会破坏已经完成的前端页面。

## 注册到总后端

队员3可以把整个 `algorithm_tools` 目录放到项目根目录，在总 FastAPI 应用中加入：

```python
from algorithm_tools.router import router as algorithm_tools_router

app.include_router(algorithm_tools_router)
```

这样总后端会一次获得全部 9 个 `/tools/*` 接口，包括原有的真值表、关系判断和 7 个扩展工具。

## 运行测试

```powershell
python -m unittest algorithm_tools.test_tools -v
```

测试覆盖原有功能、7 个新增工具、错误输入和统一 API 格式。

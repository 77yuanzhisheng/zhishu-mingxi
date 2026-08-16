# 队员四前端使用说明

## 功能

- 个人学习仪表盘：今日学习、本周答题、总体进度、薄弱提醒和近 7 天活动
- RAG 问答：调用统一后端 `POST /chat`
- 多轮对话：复用 `session_id`，超过 10 轮自动压缩历史上下文
- 知识图谱：掌握度着色、薄弱节点提示、推荐路径和节点推荐题
- 学情分析：六模块雷达图、掌握/薄弱/未学统计、总体进度
- 班级管理：学生加入班级、教师查看学生学情、学情分享申请审批
- 在线考试：模块选择、15 分钟计时、自动判分和掌握度更新
- 算法工具箱：公式化简、主范式、集合运算、哈斯图、最短路径、二分图和代码生成
- 原有真值表、关系矩阵、自测练习页面

## 启动

先在项目根目录启动统一后端：

```powershell
cd D:\LabSource\tiaozhanbei\zhishu-mingxi-git
D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe main.py --api --port 8000 --no-reload
```

再启动前端：

```powershell
cd D:\LabSource\tiaozhanbei\zhishu-mingxi-git
D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe frontend\server.py --port 5500
```

浏览器打开：

```text
http://127.0.0.1:5500
```

学情页面也可以直接打开并刷新：

```text
http://127.0.0.1:5500/learning
```

算法工具箱可以直接打开：

```text
http://127.0.0.1:5500/tools
```

## API 对接

已直接对接：

- `POST /chat`
- `GET /kb/knowledge-graph`
- `GET /kb/search`
- `POST /kb/recommend`
- `POST /kb/learning-path`
- `POST /tools/formula-simplify`
- `POST /tools/normal-forms`
- `POST /tools/set-operation`
- `POST /tools/hasse-diagram`
- `POST /tools/dijkstra`
- `POST /tools/bipartite`
- `POST /tools/code-generate`

按队员三接口约定对接：

- `GET /api/learning/report`
- `POST /api/learning/update-mastery`
- `/api/class/*`
- `/api/exam/*`
- `/api/share/*`

上述学情、班级、考试和分享接口已合并进 `dhz0707`，数据持久化到 SQLite。班级和分享接口失败时页面会明确显示错误；考试暂时保留本地判分降级。

默认提供两个演示用户：用户 `1`（当前用户）和用户 `2`（分享测试对象）。首次打开页面会自动确保用户 `1` 已初始化。

## 注意

- 统一知识库与问答后端地址是 `http://127.0.0.1:8000`。
- 远程模型响应较慢时可在 `.env` 设置 `LLM_TIMEOUT_SECONDS=120`（允许范围 30-300 秒）。
- 算法工具已注册到统一后端 `http://127.0.0.1:8000/tools/*`。
- ECharts 已保存到 `frontend/vendor/echarts/`，学情图表不依赖外网 CDN。
- 后端测试命令：`D:\LabSource\tiaozhanbei\.venv310\Scripts\python.exe -m pytest -q -s`。
- 不要把 `.env`、API Key、`local_models/` 或 `data/chroma/` 提交到 Git。

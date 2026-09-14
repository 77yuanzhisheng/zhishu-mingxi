# 上线记录：知识图谱 500 修复 + SPA 路由刷新修复（2026-09-14 hotfix1）

镜像：`api:20260914-hotfix1` / `web:20260914-hotfix1`（基于 `20260914-teacherfeedback1` overlay）
站点：http://115.175.38.106:32170

## 一、改了什么（2 处，只覆盖 3 个文件）

### 1. `backend/learning/path_data.py` —— 修「学生知识图谱页偶发 500」
- 现象：并发/重复刷新学习路径时报 500
- 日志：`sqlite3.IntegrityError: UNIQUE constraint failed: learning_path_snapshots.user_id, version`
- 原因：`refresh_learning_path` 与 `persist_snapshot` 之间的 `SELECT MAX(version)+1` 不是原子的，两个请求算出同一版本号
- 修法：`persist_snapshot` 在事务内重新取版本号，撞唯一约束/写锁时取下一版本重试（最多 5 次），并用真实落库版本回填返回值

### 2. `frontend/app.js` + `frontend/index.html` —— 修「标签页 F5 刷新白屏」
| 旧路由（与 nginx 冲突） | 新路由 |
| --- | --- |
| `/chat`（GET 405） | `/qa` |
| `/tools`（301 到内部 8080） | `/tool-center` |
| `/textbook`（301 到内部 8080） | `/textbook-center` |

- 同时把 `index.html` 里 `app.js?v=66` 提升为 `app.js?v=67`，避免浏览器继续用缓存的旧脚本
- 后端接口 `/chat`、`/tools/run`、`/textbook/index.html` 一律未动；教材 iframe 仍指向 `/textbook/index.html`

## 二、验证结果（上线后实测）

- `GET /api/health` 200；`app.js?v=67` = 310771 B；`textbook/index.html` = 216726 B
- **并发 10 次** `POST /api/learning/path/refresh` → **10/10 均 200**（修复前会出现 500），日志无 IntegrityError
- 本地回归用例 `tests/test_learning_path_snapshot_race.py`：并发 8 次落库 → 0 报错、版本 1..8 唯一（pytest 通过）
- 新路由 `/qa`、`/tool-center`、`/textbook-center` 直链与 F5 刷新均 200，标签页正确恢复、0 控制台报错
- 功能回归：星辰 Agent 问答 200（provider=agent）、流式 131 帧、符号工具、证明题库、教师试卷列表、知识图谱、节点-教材映射（rel_02_05→K020402）全部 200

## 三、回滚

```bash
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-api api=115.175.38.106:8079/zhishu-mingxi/api:20260914-teacherfeedback1
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-web web=115.175.38.106:8079/zhishu-mingxi/web:20260914-teacherfeedback1
```

备份：`/root/zhishu-mingxi-backups/20260914-hotfix1/`（含切换前的 deploy yaml 与镜像清单）
构建目录：`/root/zhishu-mingxi-hotfix-20260914/`
# 教师反馈修复包上线记录（2026-09-14）

交付包：`_教师反馈修复_交付_20260914.zip`（第三批，替换已作废的“教师试卷回看”包）。

## 一、本次上线的 8 个文件

| 序号 | 目标位置 | 说明 |
| --- | --- | --- |
| 1 | `backend/management/models.py` | 试卷题型字段 |
| 2 | `backend/management/question_source.py` | 按题型筛题 |
| 3 | `backend/management/exam_service.py` | 组卷题型过滤与提示文案 |
| 4 | `backend/management/router.py` | 组卷接口 `question_types` 入参 |
| 5 | `backend/kb/recommender.py` | 推荐逻辑配套调整 |
| 6 | `frontend/app.js` | 教师端题型选择、学生端拍照识别（v=66） |
| 7 | `frontend/index.html` | 站点入口（v=66） |
| 8 | `deploy/teacher-feedback-20260914/textbook/index.html` | 教材页（去开发者提示、逐字输出） |

> 落地到站点根 `<站点根>/textbook/index.html`。教材目录其余 1168 个文件不动。

## 二、部署方式（与 `docs/部署上线手册.md` 一致）

1. 以线上镜像为底，用 overlay Dockerfile 只覆盖上述 8 个文件（**绝不整棵覆盖 `backend/`**，避免带上已叫停的 6 个防爬改动）。
2. `docker build` 生成 `api:20260914-teacherfeedback1` / `web:20260914-teacherfeedback1`。
3. push 到 Harbor `115.175.38.106:8079/zhishu-mingxi/`。
4. 服务器 `ctr -n k8s.io images import`（`imagePullPolicy: Never`，必须导入，否则拉起失败）。
5. `kubectl -n zhishu-mingxi set image`（先 API 后 Web）。

## 三、上线后验收（全部通过）

- `app.js?v=66`，`app.js` 310760 B，`textbook/index.html` 216726 B，`/api/health` 200。
- openapi 端点 73 → 76（`question_types` 已注册）。
- 交付包 `验收.py`：17/17 通过。
- 教师端组卷题型：不勾选 = 与改动前请求体一致；只勾证明题数量 20 → 返回“现有题库仅找到 2 道匹配题目…（已按题型筛选：证明题）”；概念题+选择题不出证明题。
- 学生拍照识别：识别结果回填作答框并随交卷提交；未出结果即交卷时迟到结果被丢弃；非图片文件给出明确提示。
- 回归：查看答案、成绩清单 CSV（UTF-8 BOM，中文正常）、结束考试二次确认、重新开放、教材页逐字输出且无开发者提示。

## 四、回滚

```bash
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-api api=115.175.38.106:8079/zhishu-mingxi/api:20260914-examreview1
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-web web=115.175.38.106:8079/zhishu-mingxi/web:20260914-examreview1
```

服务器备份目录：`/root/zhishu-mingxi-backups/20260914-teacherfeedback1/`。
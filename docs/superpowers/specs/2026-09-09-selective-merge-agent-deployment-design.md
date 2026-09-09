# 选择性合并、星辰 Agent 配置与安全部署设计

**日期：** 2026-09-09  
**状态：** 已确认设计，待执行计划

## 目标

在不回退已上线的聊天、批阅、视觉识别和登录修复的前提下，选择性吸收 GitHub 未合入分支中的稳定改进；使用本机提供的星辰 Agent 配置文件为生产 API 配置 Agent 优先通道；随后安全部署并完成真实功能验收。

## 约束

- 只在安全工作树中合并，主工作区的未提交改动不得被 pull、reset、clean 或覆盖。
- API Key、Secret、Flow ID 等仅写入服务器 K8s Secret，不得出现在源码、Git 历史、镜像日志或报告中。
- 服务器只能操作 `zhishu-mingxi` 命名空间内的 `zhishu-mingxi-api` 与 `zhishu-mingxi-web`。
- 不修改 K8s 系统组件、其他命名空间、Harbor 或全局镜像缓存。
- 发布使用新的不可变镜像标签，保留当前稳定版本以便回滚。

## 代码合并策略

### 已同步

- `dhz0707`：前端去除重复 Agent 状态标签，已合入当前安全分支。

### 选择性评估后吸收

- `codex/production-upstream-integration`：仅吸收可验证的流式聊天、同源 API、OCR/批阅/视觉输出 JSON 容错，以及对应测试；不整分支合并。
- `codex/kubernetes-deployment`：只评估题目类型自适应回答格式和对应测试；不采用其 Docker、K8s、Nginx 文件覆盖当前生产链路。

### 不直接合入

- `codex/fix-self-test-grading`：与当前分支分叉较早，整分支合并会产生大范围文件差异。仅在确有回归证据时摘取单个、经测试的补丁。

## Agent 配置策略

- 配置来源为用户确认的本地星辰 Agent 信息文件。
- 运行时环境由 `zhishu-mingxi-runtime` Secret 提供。
- 关键环境变量包括启用标志、请求地址、访问凭据、Flow ID、Bot 标识与超时设置；本文不记录具体值。
- 后端保持“星辰 Agent 优先；失败后训练后模型 / 本地 RAG 自动降级”的行为，并向前端传递 provider 与 fallback 状态。

## 发布与验收流程

1. 对每个候选补丁先执行针对性测试；测试不通过即不纳入发布。
2. 构建新的 API / Web 镜像并导入节点的 `k8s.io` containerd 命名空间。
3. 先更新 API，等待 Deployment rollout 成功并验证健康检查；再更新 Web。
4. 真实验收登录、普通问答、Agent 成功通道、降级通道、大题批阅、图片识别及浏览器 API 请求。
5. 任一核心验收失败时立即回滚到本次发布前记录的 API / Web 镜像标签，并保留诊断证据。

## 防回归检查

- 前端 JavaScript 语法检查与 API 基址/流式写入相关测试。
- 聊天 Agent 成功、未配置、超时、HTTP 异常、非法响应、降级与历史防重复写入测试。
- 批阅 JSON / LaTex 转义、OCR 与视觉输出解析测试。
- 发布后验证 API Pod 中 Secret 环境变量存在，但不输出任何值。

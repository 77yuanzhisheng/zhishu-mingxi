# 交互式教材 5.0 部署增量（2026-09-14）

本目录保存 2026-09-14 上线使用的教材 5.0 增量包。完整教材资源体积较大且按仓库规则不提交，本目录只提交本次实际变化的 16 个文件及验收清单，保证部署可复现。

## 文件说明

- `textbook-5.0-overlay.tar.gz`：解压后包含 `textbook/` 目录及 16 个增量文件。
- `验收基线.txt`：16 个增量文件的 CRC32、字节数和验收规则。

增量包 SHA256：

```text
3B42D53D93A76F0CE9DDAB6BB2913C3A91BE651AF25A246B4F818B0150E64C4A
```

## 本次上线方式

1. 在服务器上基于原有 Web 镜像增量构建，不替换 API 或其他业务容器：

```dockerfile
FROM 115.175.38.106:8079/zhishu-mingxi/web:20260913-team4frontend
USER root
COPY context/textbook/ /usr/share/nginx/html/textbook/
RUN chown -R 101:101 /usr/share/nginx/html/textbook
USER 101
```

2. 构建并推送目标镜像：

```text
115.175.38.106:8079/zhishu-mingxi/web:20260914-textbook5
```

3. 仅更新 Web Deployment：

```bash
kubectl -n zhishu-mingxi set image deployment/zhishu-mingxi-web \
  web=115.175.38.106:8079/zhishu-mingxi/web:20260914-textbook5
kubectl -n zhishu-mingxi rollout status deployment/zhishu-mingxi-web --timeout=300s
```

## 验收地址

使用 `<站点根>/textbook/index.html`，不要使用不带结尾斜杠的 `/textbook`。

重点检查：

- `/textbook/data/kg-kpmap.js` 返回 `application/javascript`
- `/textbook/index.html` 为 202381 字节
- 第 5 章 23 张图正常
- 主应用首页和 `/api/health` 正常

## 回滚

将 Web Deployment 镜像改回原版本即可：

```text
115.175.38.106:8079/zhishu-mingxi/web:20260913-team4frontend
```

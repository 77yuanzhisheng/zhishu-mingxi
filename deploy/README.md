# 部署说明（知数·明析）

线上跑在导师那台服务器的 k8s 上，`zhishu-mingxi` 命名空间里两个 Deployment：

| Deployment | 作用 | 镜像 |
|---|---|---|
| `zhishu-mingxi-api` | FastAPI 后端（`/api/`、`/chat`、`/kb/`、`/tools/`） | `115.175.38.106:8079/zhishu-mingxi/api:<tag>` |
| `zhishu-mingxi-web` | nginx：静态前端 + 反向代理到 api | `115.175.38.106:8079/zhishu-mingxi/web:<tag>` |

体验地址：http://115.175.38.106:32170

## 硬约束

1. **绝不能整棵覆盖 `backend/`**。仓库里有若干被叫停的改动（防爬 / 接口收口），整树覆盖会把它们带上线。
   每次只传交付包点名的那几个文件。
2. **不能动这台机器上别的 k8s 工作负载**（它同时是别的课题的集群节点）。
   所有 `kubectl` 命令都必须带 `-n zhishu-mingxi`。
3. **不要往服务器传 `.env`**。
4. 前端改完**必须同时**更新 `index.html` 里的 `app.js?v=`（缓存钥匙），否则手机浏览器会继续吃旧脚本。

## 上线步骤（照这个来）

```bash
# 0) 备份当前部署与镜像清单
mkdir -p /root/zhishu-mingxi-backups/<日期>
kubectl -n zhishu-mingxi get deploy -o yaml > /root/zhishu-mingxi-backups/<日期>/deploy-before.yaml

# 1) 准备构建目录：只放这次要覆盖的文件
#    /root/zhishu-mingxi-<用途>-<日期>/
#      api/backend/...            ← 只放改动过的后端文件
#      web/app.js, web/index.html ← 只放改动过的前端文件
#      Dockerfile.api / Dockerfile.web

# 2) 构建（FROM 上一个 tag，链式叠加，不重打整棵树）
docker build -f Dockerfile.api -t 115.175.38.106:8079/zhishu-mingxi/api:<新tag> .
docker build -f Dockerfile.web -t 115.175.38.106:8079/zhishu-mingxi/web:<新tag> .

# 3) ★ 校验镜像里的文件确实是这一份（md5 对交付包）
docker run --rm --entrypoint md5sum <新镜像> /app/backend/... /usr/share/nginx/html/app.js
docker run --rm --entrypoint nginx   <新镜像> -t          # nginx 配置必须 test is successful

# 4) 送进 containerd（k8s 用的是 containerd，不是 docker 的存储）
docker save -o /root/<tag>.tar <api镜像> <web镜像>
ctr -n k8s.io images import /root/<tag>.tar
rm -f /root/<tag>.tar                                      # 顺手清掉，别占磁盘

# 5) 切镜像并等滚动完成
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-api api=<api镜像>
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-web web=<web镜像>
kubectl -n zhishu-mingxi rollout status deploy/zhishu-mingxi-api --timeout=180s
kubectl -n zhishu-mingxi rollout status deploy/zhishu-mingxi-web --timeout=180s

# 6) 确认没影响别人
kubectl get pods -A --field-selector=status.phase!=Running --no-headers    # 期望为空
```

Deployment 用的是 `imagePullPolicy: Never` —— 镜像必须先 `ctr import` 进去，否则 Pod 起不来。

## 回滚

```bash
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-api api=<上一个tag>
kubectl -n zhishu-mingxi set image deploy/zhishu-mingxi-web web=<上一个tag>
```

## nginx 上传上限

`deploy/nginx/default.conf` 是 web 镜像里 nginx 配置的唯一来源（构建时 COPY 到
`/etc/nginx/conf.d/default.conf`）。里面的 `client_max_body_size 12m;` 是必须的：
nginx 默认上限只有 **1 MiB**，超一点就在 nginx 层被挡回 **413**，请求根本到不了应用
（手机拍照原图 2–8 MB、教材上传都踩这条线）。

改这个文件之后：`docker run --rm --entrypoint nginx <镜像> -t` 必须先过，再上线。
# Ditto 容器部署

该目录描述单机、loopback-only 的 Ditto API 与 Prefect worker 部署。生产 compose 不隐式构建，也不接受 `latest` 作为默认值：调用方必须通过 `DITTO_IMAGE` 提供已验证的镜像引用，推荐 `registry/name@sha256:<digest>`。

## 构建与验证

```bash
docker build --pull -f deploy/docker/Dockerfile -t ditto:dev .
docker run --rm \
  --env TUSHARE_TOKEN='<runtime-token>' \
  -p 127.0.0.1:8000:8000 \
  ditto:dev
curl --fail http://127.0.0.1:8000/readyz
```

镜像使用固定 digest 的 builder/runtime base，多阶段构建，最终进程以 `65532:65532` 运行。容器内不调用 uv；只执行构建阶段生成的冻结环境。

## Compose

创建并授权持久目录：

```bash
sudo install -d -o 65532 -g 65532 \
  /opt/ditto/state \
  /opt/ditto/cache \
  /opt/ditto/prefect \
  /opt/ditto/logs/api \
  /opt/ditto/logs/job
```

启动时必须提供镜像身份：

```bash
DITTO_IMAGE='registry.example/ditto@sha256:<digest>' \
  TUSHARE_TOKEN='<runtime-token>' \
  docker compose -f deploy/docker/docker-compose.yml up -d
```

本地构建可显式使用 `DITTO_IMAGE=ditto:dev`，但不可作为发布证据。宿主端口只绑定 `127.0.0.1`。

## 运行时目录契约

| 变量 | 容器路径 | 用途 |
|---|---|---|
| `DITTO_CONFIG_ROOT` | `/opt/ditto` | 包含 `config/<environment>` 的只读配置根 |
| `DITTO_STATE_ROOT` | `/var/lib/ditto/state` | 业务状态与数据库 |
| `DITTO_CACHE_ROOT` | `/var/cache/ditto` | 可丢弃缓存 |
| `LOG_DIR` | `/var/log/ditto` | 应用日志 |
| `PREFECT_HOME` | `/var/lib/ditto/prefect` | Prefect 状态 |

旧 `DITTO_DATA_ROOT` 不再由部署层设置，仅保留应用内过渡兼容。

## 探针与安全边界

- `/healthz` 只表示进程存活。
- `/readyz` 验证启动、config/state/cache 和生产数据源凭证；文档占位值不会获得 production readiness。
- 根文件系统只读；state、cache、logs、Prefect 和 `/tmp` 是显式可写边界。
- `no-new-privileges` 开启，镜像无 root 运行入口。

查看状态：

```bash
DITTO_IMAGE='registry.example/ditto@sha256:<digest>' \
  TUSHARE_TOKEN='<runtime-token>' \
  docker compose -f deploy/docker/docker-compose.yml ps
curl --fail http://127.0.0.1:8000/readyz
```

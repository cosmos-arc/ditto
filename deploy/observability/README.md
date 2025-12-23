# Ditto 可观测性系统部署指南

## 概述

本目录包含 Ditto 可观测性系统的 Docker Compose 配置，用于部署以下服务：

- **VictoriaMetrics** (v1.104.0) - Metrics 存储与 OTLP 接收
- **VictoriaLogs** (v0.37.0) - Logs 存储与查询
- **Vector** (v0.52.0) - 日志采集
- **Grafana** (11.1.0) - 可视化仪表盘

## 快速开始

### 1. 启动 Docker Desktop

确保 Docker Desktop 正在运行：

```powershell
docker version
```

### 2. 启动服务

从项目根目录运行：

```powershell
.\scripts\observability\start.ps1
```

### 3. 验证服务

运行健康检查：

```powershell
.\scripts\observability\health_check.ps1
```

### 4. 访问服务

| 服务 | URL | 用途 |
|------|-----|------|
| Grafana | http://localhost:3000 | 可视化仪表盘 |
| VictoriaMetrics | http://localhost:8428 | Metrics 查询 UI |
| VictoriaLogs | http://localhost:9428 | Logs 查询 UI |
| Vector | http://localhost:8686 | 日志采集状态 |

## 目录结构

```
deploy/observability/
├── docker-compose.yml          # Docker Compose 配置
├── vector.toml                 # Vector 日志采集配置
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── datasources.yml      # 数据源配置
        └── dashboards/
            ├── dashboard.yml         # 仪表盘提供者配置
            └── ditto-overview.json   # Ditto 概览仪表盘
```

## 数据流向

```
┌─────────────────────────────────────────────────────────────────┐
│                      Ditto Application                           │
├─────────────────────────────────────────────────────────────────┤
│  Loguru → logs/ditto.jsonl → Vector → VictoriaLogs             │
│  OTel Metrics → OTLP HTTP → VictoriaMetrics                     │
│  Traces → 通过 trace_id 关联日志（暂不独立存储）                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                        ┌──────────────┐
                        │   Grafana    │
                        │    :3000     │
                        └──────────────┘
```

## 停止服务

```powershell
.\scripts\observability\stop.ps1
```

停止并清理数据卷：

```powershell
.\scripts\observability\stop.ps1
# 提示清理时输入 'y'
```

## 故障排查

### Docker Desktop 未启动

**错误**: `error during connect: ... The system cannot find the file specified`

**解决**: 启动 Docker Desktop

### 端口占用

**错误**: 端口 8428、9428、3000、8686 被占用

**解决**:
```powershell
# 查看端口占用
netstat -ano | findstr "8428"
```

### 日志未采集

**检查**:
1. 确认 `logs/ditto.jsonl` 文件存在
2. 检查 Vector 容器日志：`docker logs ditto-vector`
3. 确认 Vector 可以访问日志目录

### 指标未推送

**检查**:
1. 确认应用正在运行
2. 检查 `vm_endpoint` 配置是否为 `http://localhost:8428/opentelemetry/v1/metrics`
3. 查看 VictoriaMetrics 日志：`docker logs ditto-vm`

## 资源占用

| 组件 | 内存 | 磁盘（30天） |
|------|------|--------------|
| VictoriaMetrics | ~100MB | ~500MB |
| VictoriaLogs | ~100MB | ~2GB |
| Vector | ~50MB | - |
| Grafana | ~150MB | ~100MB |
| **总计** | **~400MB** | **~2.6GB** |

## 数据保留

- **VictoriaMetrics**: 90 天
- **VictoriaLogs**: 30 天
- **应用日志文件**: 30 天（自动轮转和压缩）

## 配置修改

### 修改端口

编辑 `docker-compose.yml`，修改对应的端口映射。

### 修改保留期

编辑 `docker-compose.yml`，修改 `--retentionPeriod` 参数。

### 修改资源限制

编辑 `docker-compose.yml`，修改 `deploy.resources.limits.memory`。

## 相关文档

- [可观测性设计文档](../../../docs/design/05_observability.md)
- [部署拓扑文档](../../../docs/design/04_deployment_topology.md)
- [日志模块文档](../../../packages/foundation/src/ditto_foundation/observability/@README.PACKAGE.md)

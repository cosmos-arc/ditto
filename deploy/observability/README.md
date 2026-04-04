# Ditto Observability Deployment Guide

**版本**: v0.2.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

This directory contains the Docker Compose configuration for deploying Ditto observability stack.

## Services

| Service | Version | Port | Memory Limit | Purpose |
|---------|---------|------|--------------|---------|
| VictoriaMetrics | v1.104.0 | 8428 | 256M | Metrics storage + OTLP receiver |
| VictoriaLogs | v1.37.0 | 9428 | 256M | Logs storage + query |
| Vector | v0.52.0-debian | 8686 | 128M | Log collection |
| Grafana | 11.1.0 | 3000 | 256M | Visualization dashboards |

**Total Resource Usage**: ~400MB RAM, ~2.6GB disk (30 days)

## CI/CD Integration

This configuration is also used in GitHub Actions for integration tests.

- **CI Workflow**: `.github/workflows/ci-integration.yml`
- **Command**: `docker compose -f docker-compose.yml up -d`
- **Note**: CI uses Docker Compose V2 plugin (`docker compose`)

### CI vs Local Differences

| Aspect | Local | CI |
|--------|-------|-----|
| Command | `docker-compose` | `docker compose` |
| Volumes | Persistent | None (ephemeral) |
| Coverage Check | N/A | `--cov-fail-under=0` (disabled) |

## Prerequisites

- Docker Desktop installed and running
- Windows PowerShell 5.1+
- Ports 8428, 9428, 3000, 8686 available

## Quick Start

### 1. Start Services

```bash
# From this directory
docker compose up -d
```

> **Note**: PowerShell helper scripts (`start.ps1`, `health_check.ps1`, `stop.ps1`) are not yet implemented. Use `docker compose` commands directly.

### 2. Check Service Health

Expected output:
```
Service           Status    URL
-------           ------    ---
VictoriaMetrics   Healthy   http://localhost:8428
VictoriaLogs      Healthy   http://localhost:9428
Vector            Healthy   http://localhost:8686
Grafana           Healthy   http://localhost:3000
```

### 3. Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Visualization dashboards |
| VictoriaMetrics | http://localhost:8428 | Metrics query UI |
| VictoriaLogs | http://localhost:9428 | Logs query UI |
| Vector | http://localhost:8686 | Log collection status |

### 4. Stop Services

```bash
# From this directory
docker compose down
```

## Data Flow

```
Ditto Application
    Loguru -> logs/ditto.jsonl -> Vector -> VictoriaLogs
    OTel Metrics -> OTLP HTTP -> VictoriaMetrics
    Traces -> Correlated with logs via trace_id (not stored separately)
                                        |
                                        v
                                  Grafana :3000
```

## Testing

Generate test logs and metrics:

```powershell
python scripts/observability/test_observability.py
```

This will:
- Write test logs to `logs/ditto.jsonl`
- Push test metrics to VictoriaMetrics
- Allow you to verify the data flow

## Troubleshooting

### Docker Desktop not running

```powershell
docker version
```

If this fails, start Docker Desktop.

### Port conflicts

Check if ports are in use:

```powershell
netstat -an | findstr "8428 9428 3000 8686"
```

Stop conflicting services or change ports in `docker-compose.yml`.

### Vector cannot read logs

Check that the `logs/` directory exists and has correct permissions:

```powershell
ls logs\
```

### Metrics not being pushed

Check the `vm_endpoint` configuration in your observability config:

```
http://localhost:8428/otlp/v1/metrics
```

Verify network connectivity from your application to VictoriaMetrics.

### Grafana datasource connection failed

Check container network and DNS resolution:

```powershell
docker exec ditto-grafana ping victoriametrics
docker exec ditto-grafana ping victorialogs
```

## Configuration

### Vector Configuration

File: `vector.toml`

- Source: Reads from `/logs/ditto*.jsonl`
- Transform: Parses JSON messages
- Sink: Pushes to VictoriaLogs HTTP endpoint

### Grafana Provisioning

Located in `grafana/provisioning/`:

- `datasources/datasources.yml`: Configures VictoriaMetrics and VictoriaLogs
- `dashboards/dashboard.yml`: Dashboard provider configuration
- `dashboards/ditto-overview.json`: Main Ditto observability dashboard

## Maintenance

### View logs

```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f victoriametrics
docker-compose logs -f grafana
```

### Restart a service

```powershell
docker-compose restart grafana
```

### Clear data (WARNING: deletes all data)

```powershell
docker-compose down -v
docker-compose up -d
```

### Update service versions

Edit `docker-compose.yml`, then:

```powershell
docker-compose pull
docker-compose up -d
```

## Security Notes

This configuration is for local development only:

- Grafana anonymous access enabled
- No authentication configured
- No TLS/SSL

For production deployment:
- Enable Grafana authentication
- Configure TLS certificates
- Restrict network access
- Enable audit logging

## 变更记录

### v0.2.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善文档结构

### v0.1.0 (2025-12-23)
**新增**
- 初始可观测性部署配置
- Docker Compose 配置
- Grafana 仪表盘配置

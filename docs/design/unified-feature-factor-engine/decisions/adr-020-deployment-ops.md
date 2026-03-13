# ADR-020: 部署与运维设计

**状态**: 已决策（2026-03-05）

---

## 背景

因子引擎需要部署 QuestDB（时序存储）和 Kvrocks（状态存储），需要设计：
1. Docker Compose 部署方案
2. 本地开发测试的 Mock 方案
3. 与现有运维体系集成

---

## 设计目标

1. **Docker Compose 一键部署** QuestDB + Kvrocks
2. **与现有架构兼容** - 统一数据路径、端口无冲突
3. **本地开发友好** - Mock/内存后端支持
4. **可观测性集成** - 复用现有 VictoriaMetrics + Grafana

---

## 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      deploy/derived/                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐       ┌─────────────────────┐          │
│  │     QuestDB         │       │      Kvrocks        │          │
│  │     :9000 (HTTP)    │       │     :6666 (Redis)   │          │
│  │     :8812 (PG)      │       │                     │          │
│  │                     │       │   RocksDB 持久化    │          │
│  │   Hot 层时序数据    │       │   增量状态/Checkpoint│          │
│  └─────────┬───────────┘       └─────────┬───────────┘          │
│            │                             │                       │
│            └─────────────┬───────────────┘                       │
│                          ▼                                       │
│            ┌──────────────────────────────┐                      │
│            │   /opt/ditto/data/           │                      │
│            │   ├── questdb/               │                      │
│            │   └── kvrocks/               │                      │
│            └──────────────────────────────┘                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Docker Compose 配置

**`deploy/derived/docker-compose.yml`**:

```yaml
version: "3.8"

services:
  questdb:
    image: questdb/questdb:8.2.1
    container_name: ditto-questdb
    restart: unless-stopped
    ports:
      - "9000:9000"   # Web Console + REST API
      - "8812:8812"   # PostgreSQL wire protocol
    volumes:
      - /opt/ditto/data/questdb:/root/.questdb
      - ./questdb/server.conf:/root/.questdb/conf/server.conf:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/status"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
    networks:
      - ditto-derived

  kvrocks:
    image: apache/kvrocks:2.9.0
    container_name: ditto-kvrocks
    restart: unless-stopped
    ports:
      - "6666:6666"
    volumes:
      - /opt/ditto/data/kvrocks:/var/lib/kvrocks
      - ./kvrocks/kvrocks.conf:/etc/kvrocks/kvrocks.conf:ro
    command: ["./kvrocks", "-c", "/etc/kvrocks/kvrocks.conf"]
    healthcheck:
      test: ["CMD", "redis-cli", "-p", "6666", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 256M
    networks:
      - ditto-derived

networks:
  ditto-derived:
    driver: bridge
```

---

## 配置文件

### QuestDB 配置 (`deploy/derived/questdb/server.conf`)

```conf
# HTTP 服务
http.enabled=true
http.bind.to=0.0.0.0:9000

# PostgreSQL wire protocol
pg.netty.enabled=true
pg.netty.bind.to=0.0.0.0:8812
pg.user=admin
pg.password=${QUESTDB_PASSWORD}

# O3 列存储（时序优化）
cairo.o3.enabled=true
cairo.o3.max.lag=86400000

# 写入优化
cairo.commit.lag=10000
cairo.max.uncommitted.rows=1000
```

### Kvrocks 配置 (`deploy/derived/kvrocks/kvrocks.conf`)

```conf
bind 0.0.0.0
port 6666
daemonize no
dir /var/lib/kvrocks

requirepass ${KVROCKS_PASSWORD}

# RocksDB 调优
rocksdb.compression snappy
rocksdb.write_buffer_size 64mb
rocksdb.max_write_buffer_number 4
rocksdb.target_file_size_base 64mb

# 持久化
rocksdb.wal_recovery_mode 1

# 内存管理
maxmemory 200mb
maxmemory-policy allkeys-lru
```

---

## 资源配置

| 服务 | 内存限制 | 磁盘预估 | 用途 |
|------|----------|----------|------|
| QuestDB | 512MB | ~1GB | Hot 层时序数据 |
| Kvrocks | 256MB | ~50MB | 增量状态 |
| **总计** | **768MB** | **~1.1GB** | |

---

## 本地开发测试方案

### 测试分层策略

| 测试类型 | QuestDB | Kvrocks | 场景 |
|----------|---------|---------|------|
| **单元测试** | 自实现 Mock | fakeredis | 快速、隔离 |
| **集成测试** | testcontainers | fakeredis | 真实行为验证 |

### 依赖配置

```toml
# pixi.toml
[feature.dev.dependencies]
fakeredis = ">=2.30.0"
testcontainers = ">=4.0.0"
```

### Kvrocks Mock（fakeredis）

```python
import fakeredis

def create_mock_kvrocks() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()
```

### QuestDB 集成测试（testcontainers）

```python
import pytest
from testcontainers.core.generic import GenericContainer

@pytest.fixture(scope="session")
def questdb_container():
    container = GenericContainer("questdb/questdb:8.2.1")
    container.with_exposed_ports(9000, 8812)
    container.with_env("QDB_PG_USER", "admin")
    container.with_env("QDB_PG_PASSWORD", "test")
    container.start()

    yield {
        "http_url": f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}",
        "pg_url": f"postgresql://admin:test@{container.get_container_host_ip()}:{container.get_exposed_port(8812)}/qdb",
    }

    container.stop()
```

---

## 文件清单

```
deploy/derived/
├── docker-compose.yml      # 主部署文件
├── .env.example            # 环境变量模板
├── README.md               # 使用说明
├── questdb/
│   └── server.conf         # QuestDB 配置
└── kvrocks/
    └── kvrocks.conf        # Kvrocks 配置
```

---

## 决策摘要

| 决策点 | 决策 | 理由 |
|--------|------|------|
| 部署方式 | Docker Compose | 与现有架构一致 |
| 数据路径 | `/opt/ditto/data/` 统一 | 管理便捷 |
| QuestDB 端口 | 9000(HTTP), 8812(PG) | 默认端口无冲突 |
| Kvrocks 端口 | 6666 | 默认端口 |
| 单元测试 Mock | fakeredis + 自实现 | 轻量快速 |
| 集成测试 | testcontainers | 真实行为验证 |

---

## DuckDB ADHOC 工具

> 详见 [ADR-026: DuckDB 定位与使用规范](adr-026-duckdb-positioning.md)

DuckDB 不作为常驻服务，仅作为 ADHOC/审计工具使用：

### 使用场景

| 场景 | 命令示例 |
|------|---------|
| ADHOC SQL 查询 | `duckdb -c "SELECT * FROM read_parquet('data/market/cn/bar_1d/*.parquet') WHERE trade_date = '2026-03-10'"` |
| 审计对拍 | `python scripts/audit_using_duckdb.py` |
| Parquet/SQLite 联查 | `duckdb -c "SELECT * FROM sqlite_scan('data/metadata/metadata.sqlite', 'instrument')"` |

### 部署说明

- DuckDB 作为 Python 依赖安装在环境中，无需独立服务
- CLI 工具通过 `pixi run` 调用
- 不暴露 HTTP API

# Sprint 2 Phase 3: 数据摄取增强 - 实现计划

**创建日期**: 2025-12-29
**状态**: 待实施
**预计工期**: 4-5 天

---

## 用户决策总结

| 决策项 | 选择 | 影响 |
|--------|------|------|
| **增量目标** | 完整实现（API + 写入） | 需要设计完整的增量机制 |
| **增量粒度** | 渐进式（日期 + 数据级别） | 需要支持两种模式切换 |
| **告警通道** | 多通道（微信/Telegram/邮件） | 需要抽象告警接口 |
| **调度器** | Prefect 原生 | 与现有任务体系一致 |
| **API 接口** | 依赖 Prefect UI | Task 3.6 简化 |
| **AkShare** | 暂缓 P2 | Task 3.7, 3.8 延后 |
| **Failover** | 仅重试 | Task 3.8 简化 |
| **DQ 集成** | 完整增强 | Task 1.8 全面实现 |

---

## 新增文件结构

```
packages/datahub/src/ditto_datahub/
├── sources/
│   ├── metadata.py                        # 新增：摄取元数据模型
│   ├── base.py                            # 修改：添加增量更新接口
│   └── tushare/source.py                  # 修改：实现增量查询
│
├── stores/
│   └── ingestion_metadata_store.py        # 新增：摄取元数据 SQLite 存储
│
├── alerts/                                # 新增目录
│   ├── __init__.py
│   ├── base.py                            # AlertSender 抽象接口
│   ├── wechat.py                          # 微信告警通道
│   ├── telegram.py                        # Telegram 告警通道
│   ├── email.py                           # 邮件告警通道
│   └── manager.py                         # 告警管理器
│
└── repositories/
    └── bars.py                            # 修改：DQ 集成增强

apps/server/src/ditto_server/
├── ingestion/
│   ├── tasks/
│   │   ├── monitoring.py                  # 新增：摄取质量监控任务
│   │   └── bars.py                        # 修改：集成增量更新
│   └── flows/
│       ├── daily_ingest.py                # 修改：添加告警和监控
│       └── scheduled_ingest.py            # 新增：定时调度配置
│
└── config/
    └── alerts.yaml                        # 新增：告警配置文件
```

---

## 核心任务分解

### Task 3.1: 增量更新机制设计

**新增文件**: `packages/datahub/src/ditto_datahub/sources/metadata.py`

```python
from dataclasses import dataclass
from datetime import date
from enum import Enum

class IncrementalMode(str, Enum):
    QUICK = "quick"       # 快速模式：日期级别检查
    PRECISE = "precise"   # 精确模式：数据级别检查

@dataclass
class IngestionMetadata:
    dataset: str
    source: str
    last_trade_date: date | None
    last_checksum: str | None
    last_rows: int
    last_updated_at: str
```

**修改文件**: `packages/datahub/src/ditto_datahub/sources/base.py`

在 DataSource 基类添加增量接口：
```python
@abstractmethod
def fetch_etf_daily_incremental(
    self,
    trade_date: str,
    mode: IncrementalMode = IncrementalMode.QUICK,
    last_trade_date: str | None = None,
    last_checksum: str | None = None,
) -> tuple[pl.DataFrame, IngestionMetadata]:
    pass
```

**新增文件**: `packages/datahub/src/ditto_datahub/stores/ingestion_metadata_store.py`

SQLite 存储摄取元数据，支持：
- `get_metadata(dataset, source)` - 获取元数据
- `save_metadata(metadata)` - 保存元数据
- `list_pending_datasets(trade_date)` - 列出待摄取数据集

---

### Task 3.2: Tushare 增量适配

**修改文件**: `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

实现 `fetch_etf_daily_incremental()`：
- **快速模式**: 比较 `trade_date > last_trade_date`
- **精确模式**: 计算 `checksum(df) != last_checksum`
- 返回 `(DataFrame, IngestionMetadata)`

**关键方法**:
```python
def _compute_checksum(self, df: pl.DataFrame) -> str:
    """计算 DataFrame 校验和."""
    import hashlib
    content = df.write_ipc(compression_level=1)
    return hashlib.sha256(content).hexdigest()[:16]
```

---

### Task 3.3: 摄取质量监控

**新增文件**: `apps/server/src/ditto_server/ingestion/tasks/monitoring.py`

Prefect 任务：`monitor_ingestion_quality(trade_date, ingestion_results)`

**监控指标**:
- 摄取行数（OpenTelemetry Counter）
- 摄取耗时（OpenTelemetry Histogram）
- DQ 检查结果
- API 调用次数
- 新注册证券数

---

### Task 3.4: 摄取异常告警

**新增目录**: `packages/datahub/src/ditto_datahub/alerts/`

| 文件 | 用途 |
|------|------|
| `base.py` | `AlertSender` 抽象接口、`AlertLevel` 枚举、`AlertMessage` 数据类 |
| `wechat.py` | 微信企业号机器人实现 |
| `telegram.py` | Telegram Bot 实现 |
| `email.py` | SMTP 邮件实现 |
| `manager.py` | `AlertManager` 管理器，协调多通道发送 |

**AlertManager 核心方法**:
```python
def send_alert(level, title, message, **context) -> dict[str, bool]
def alert_ingestion_failure(dataset, trade_date, error) -> None
def alert_dq_failure(dataset, trade_date, failed_rules, error_count) -> None
```

**告警级别**:
| 级别 | 触发条件 | 通道 |
|------|----------|------|
| INFO | 摄取完成 | 日志 |
| WARNING | DQ L2 警告 | 日志 + 微信 |
| ERROR | DQ L1 错误 | 微信 + Telegram + 邮件 |
| CRITICAL | 系统故障 | 所有通道 |

---

### Task 3.5: 定时调度配置

**新增文件**: `apps/server/src/ditto_server/ingestion/flows/scheduled_ingest.py`

Prefect Flow：`scheduled_daily_ingest_flow()`

**配置**:
```python
@flow(
    schedule=CronSchedule(cron="0 18 * * 1-5"),  # 工作日 18:00
)
def scheduled_daily_ingest_flow(
    trade_date: str | None = None,  # None = 自动推断
    source: str = "tushare",
    enable_monitoring: bool = True,
    enable_alerts: bool = True,
) -> dict[str, Any]:
```

**流程**:
1. 推断交易日期（如未指定）
2. 执行 `daily_ingest_flow()`
3. 执行 `monitor_ingestion_quality()`
4. 发送告警（如有问题）

---

### Task 3.6: API 触发接口

**简化方案**: 依赖 Prefect UI 的参数化能力，不需要自建 API。

确保 `scheduled_daily_ingest_flow` 的参数支持通过 Prefect UI 传递。

---

### Task 3.7: AkShare 适配器

**状态**: 暂缓 P2，不在本次实现。

---

### Task 3.8: 数据源自动切换

**简化方案**: 仅依赖 Tushare 客户端的重试机制（已实现），不做多源切换。

---

### Task 1.8: Repository DQ 集成增强

**修改文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**三大增强**:

1. **隔离区自动写入**:
```python
if not dq_result.passed:
    for issue in dq_result.issues:
        if issue.severity == DQSeverity.ERROR:
            failed_data = df.filter(pl.col(issue.column).is_null())
            quarantine_store.save_failed_data(
                dataset=dataset,
                rule_id=issue.rule_name,
                failed_data=failed_data,
            )
```

2. **阻断机制**:
```python
if dq_result.has_errors:
    # L1 错误阻断
    return WriteResult(blocked=True, dq_result=dq_result)
# L2 警告继续
if dq_result.has_warnings:
    logger.warning("L2 warnings, proceeding...")
```

3. **报告生成集成**:
```python
def _generate_dq_report(self, result: DQResult, dataset: str) -> Path:
    report_path = self.data_root / "reports" / "dq" / f"{dataset}_{timestamp}.md"
    self._dq_report_generator.save_report(result, report_path)
    return report_path
```

**WriteResult 扩展**:
```python
@dataclass
class WriteResult:
    file_path: str
    checksum: str
    rows_written: int
    blocked: bool = False
    dq_result: DQResult | None = None
```

---

## 数据流设计

### 增量更新完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│                  定时调度触发 (Cron: 工作日 18:00)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             v
┌─────────────────────────────────────────────────────────────────┐
│                    scheduled_daily_ingest_flow                   │
│                                                                   │
│  1. 推断交易日期 → hub.calendar.get_last_trading_day()           │
│  2. 读取摄取元数据 → metadata_store.get_metadata()               │
│  3. 增量获取数据 → source.fetch_*_incremental()                  │
│     ├─ 快速模式: trade_date > last_trade_date?                   │
│     └─ 精确模式: checksum != last_checksum?                      │
│  4. DQ 检查 → dq_engine.check()                                  │
│     ├─ L1 错误 → 隔离区 → 阻断                                    │
│     ├─ L2 警告 → 日志 → 继续                                     │
│     └─ 通过 → 继续                                               │
│  5. 写入数据 → bars_store.write()                                │
│  6. 更新元数据 → metadata_store.save_metadata()                  │
│  7. 生成 DQ 报告 → report_generator.save_report()                │
│  8. 质量监控 → monitor_ingestion_quality()                       │
│  9. 发送告警 → alert_manager.alert_*()                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 任务依赖顺序

```
第一阶段：基础设施（Week 1-2）
├── Task 3.1: 增量更新机制设计
│   ├── 新增 metadata.py
│   ├── 新增 ingestion_metadata_store.py
│   └── 修改 base.py
│
└── Task 3.2: Tushare 增量适配
    └── 修改 tushare/source.py

第二阶段：监控告警（Week 3，可并行）
├── Task 3.3: 摄取质量监控
│   └── 新增 tasks/monitoring.py
│
├── Task 3.4: 摄取异常告警
│   ├── 新增 alerts/base.py
│   ├── 新增 alerts/wechat.py
│   ├── 新增 alerts/telegram.py
│   ├── 新增 alerts/email.py
│   └── 新增 alerts/manager.py
│
└── Task 3.8: 数据源自动切换（简化）
    └── 依赖现有 TushareClient 重试

第三阶段：集成调度（Week 4）
├── Task 1.8: Repository DQ 集成增强
│   ├── 修改 repositories/bars.py
│   └── 修改 tasks/bars.py
│
├── Task 3.5: 定时调度配置
│   ├── 新增 flows/scheduled_ingest.py
│   └── 修改 flows/daily_ingest.py
│
└── Task 3.6: API 触发接口（依赖 Prefect UI）
    └── 确保参数化支持

第四阶段：暂缓
└── Task 3.7: AkShare 适配器
```

---

## 关键文件（Critical Files）

| 文件路径 | 修改内容 | 优先级 |
|----------|----------|--------|
| `packages/datahub/src/ditto_datahub/sources/base.py` | 添加增量更新接口 | P0 |
| `packages/datahub/src/ditto_datahub/sources/tushare/source.py` | 实现增量查询 | P0 |
| `packages/datahub/src/ditto_datahub/repositories/bars.py` | DQ 集成增强 | P0 |
| `apps/server/src/ditto_server/ingestion/tasks/bars.py` | 集成增量更新 | P0 |
| `packages/datahub/src/ditto_datahub/alerts/manager.py` | 新增告警管理器 | P0 |

---

## 验收标准

### 功能验收
- [ ] 增量更新：快速模式跳过已摄取日期
- [ ] 增量更新：精确模式检测数据变化
- [ ] 告警系统：微信/Telegram/邮件三个通道可用
- [ ] DQ 集成：L1 错误自动写入隔离区
- [ ] DQ 集成：L1 错误阻断写入
- [ ] DQ 集成：生成 DQ 报告文件
- [ ] 定时调度：Prefect Cron 调度配置完成
- [ ] 监控任务：OpenTelemetry 指标记录

### 测试覆盖
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试覆盖关键流程

### 文档更新
- [ ] `packages/datahub/README.md`（增量更新说明）
- [ ] `apps/server/README.md`（告警配置）
- [ ] `docs/sprints/sprint-02.md`（状态更新）

---

## 参考

- Sprint 2 文档: `docs/sprints/sprint-02-data-quality.md`
- Phase 1 设计: `docs/design/09_data_quality_design.md`
- 数据层设计: `docs/design/02_data_design.md`

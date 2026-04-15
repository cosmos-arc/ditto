# Sprint 5: 交易 API 分页 + 成交幂等 + 偏差报告 + CORS 配置

> **Sprint**: V1 Sprint 5 | **Commit**: `914713c1`
> **创建**: 2026-04-15 | **状态**: Done
> **目标**: 完善交易 API 体验（分页、幂等、偏差报告）与部署配置（CORS）

---

## 1. 概述

Sprint 5 聚焦于交易 API 的生产就绪性增强，包含 5 项改进：

| # | 功能 | 优先级 | 说明 |
|---|------|--------|------|
| F1 | 交易 API 分页扩展 | P0 | positions / signals/latest / signals/{date}/intents 支持 Pagination |
| F2 | 成交幂等 | P0 | POST /trade/fills 按 intent_id + trade_date 去重，防止重复录入 |
| F3 | 信号-成交偏差报告 | P1 | 新增 GET /trade/deviation 端点，对比信号与实际成交差异 |
| F4 | 信号推送重构 | P1 | 删除 NotificationPort，DeliveryRouter 直接注入 AlertManager |
| F5 | CORS 环境感知配置 | P1 | development 固定 localhost:3000，production 通过 CORS_ORIGINS 环境变量控制 |

---

## 2. 功能详情

### 2.1 F1: 交易 API 分页扩展

**问题**: positions、signals/latest、signals/{date}/intents 三个端点返回完整列表，数据量大时响应慢且前端无法分页加载。

**方案**: 注入 `PaginationRequest`（offset + limit），返回 `PaginationResponse`（total + limit + offset）。

**涉及端点**:

| 端点 | 方法 | 分页参数 |
|------|------|---------|
| `/api/v1/trade/positions` | GET | `limit`, `offset` |
| `/api/v1/trade/signals/latest` | GET | `limit`, `offset` |
| `/api/v1/trade/signals/{signal_date}/intents` | GET | `limit`, `offset` |

---

### 2.2 F2: 成交幂等

**问题**: POST /trade/fills 无去重机制，网络重试或前端重复提交会导致同一笔成交被多次录入。

**方案**: 在 `RecordFillHandler.handle()` 开头增加幂等检查 — 按 `intent_id + trade_date` 查询是否已有成交记录，若存在则直接返回已有记录。

**去重键**: `intent_id` + `trade_date`（每个意图每天只允许一条成交）

**行为**:
- 已存在 → 返回已有 `FillResponse`（幂等，200 OK）
- 不存在 → 正常走创建流程

---

### 2.3 F3: 信号-成交偏差报告

**问题**: 用户无法直观查看哪些信号已成交、哪些未成交，以及成交与信号的偏差。

**方案**: 新增 `GET /api/v1/trade/deviation` 端点，对比指定日期的信号意图与实际成交记录。

**响应结构**:

```python
class DeviationResponse(BaseModel):
    strategy_id: str
    signal_date: str
    total_signals: int
    filled: int
    unfilled: int
    items: list[SignalDeviationItem]

class SignalDeviationItem(BaseModel):
    instrument_id: int
    signal_action: str        # BUY / SELL / HOLD
    signal_weight: float      # 信号目标权重
    actual_weight: float | None  # 实际成交权重
    deviation_bps: float | None  # 偏差（基点）
    fill_status: str          # filled / unfilled
```

---

### 2.4 F4: 信号推送重构

**问题**: `SignalDeliveryProvider` 内嵌 `_TelegramNotificationAdapter`（~100 行），职责不清且与 `AlertManager` 重复。

**方案**:
- 删除 `NotificationPort` Protocol 及其实现（`_TelegramNotificationAdapter`、`_NoOpNotificationPort`）
- `DeliveryRouter` 直接注入 `AlertManager`（由 `NotificationProvider` 负责通道配置）
- `SignalDeliveryProvider` 简化为 ~30 行，仅负责 `DeliveryRouter` + `SignalDeliveryProtocol` 的 DI 注册

**依赖链变更**:

```
Before: SignalDeliveryProvider → NotificationPort → DeliveryRouter → SignalDeliveryProtocol
After:  SignalDeliveryProvider → AlertManager → DeliveryRouter → SignalDeliveryProtocol
```

---

### 2.5 F5: CORS 环境感知配置

**问题**: CORS 固定为 `localhost:3000`，生产环境部署到非 localhost 域名时无法访问 API。

**方案**:

| 环境 | CORS 来源 | 配置方式 |
|------|----------|---------|
| development | `localhost:3000`, `127.0.0.1:3000` | 硬编码 |
| production | 通过 `CORS_ORIGINS` 环境变量（逗号分隔） | 环境变量，未设置时默认 `*` |

---

## 3. 涉及文件

### 3.1 修改文件

| 文件 | 变更内容 |
|------|---------|
| `interfaces/src/ditto_interfaces/api/routes/trade.py` | 分页扩展 + 偏差报告端点 |
| `interfaces/src/ditto_interfaces/main.py` | CORS 环境感知配置 |
| `interfaces/src/ditto_interfaces/models/trade.py` | 新增 `DeviationResponse`、`SignalDeviationItem` |
| `interfaces/src/ditto_interfaces/registry/infra/signal_delivery.py` | 删除 NotificationPort，注入 AlertManager |
| `interfaces/src/ditto_interfaces/registry/infra/notification.py` | 通知通道调整 |
| `interfaces/src/ditto_interfaces/registry/contexts/strategy.py` | 上下文调整 |
| `interfaces/src/ditto_interfaces/cli/main.py` | CLI 调整 |
| `interfaces/src/ditto_interfaces/jobs/flows/__init__.py` | Flow 注册调整 |
| `interfaces/src/ditto_interfaces/jobs/flows/deploy.py` | Deploy flow 调整 |
| `packages/app/src/ditto_app/command/trade.py` | 成交幂等检查 |
| `packages/app/src/ditto_app/process/execution/delivery.py` | DeliveryRouter 重构（移除 NotificationPort） |
| `packages/data/src/ditto_data/services/trade_service.py` | 新增 `find_fill()` 方法 |
| `config/development/observability.env` | CORS 配置说明 |
| `config/production/observability.env` | CORS_ORIGINS 环境变量说明 |
| `docs/plans/2026-04-14-v1-final-enhancement-design.md` | Sprint 5 状态更新为 Done |

### 3.2 新增文件

| 文件 | 说明 |
|------|------|
| `docs/plans/2026-04-15-v1-rc-closeout-plan.md` | RC 关闭计划 |
| `interfaces/tests/integration/api/test_trade_api_integration.py` | 交易 API 集成测试（172 行） |

### 3.3 测试文件变更

| 文件 | 新增测试 |
|------|---------|
| `packages/app/tests/unit/command/test_trade_unit.py` | 幂等性测试（+53 行） |
| `packages/app/tests/unit/process/execution/test_delivery_unit.py` | DeliveryRouter 重构测试（+90/-38 行） |
| `packages/data/tests/unit/services/test_trade_service_unit.py` | `find_fill()` 测试（+56 行） |
| `interfaces/tests/unit/jobs/flows/test_deploy_unit.py` | Deploy flow 调整测试（+41/-行） |

---

## 4. 验收标准

### 4.1 功能验收

- [x] positions / signals/latest / signals/{date}/intents 三个端点支持 `limit` + `offset` 分页参数
- [x] POST /trade/fills 重复提交（相同 intent_id + trade_date）返回已有记录，不创建重复成交
- [x] GET /trade/deviation 返回指定策略和日期的信号-成交偏差报告
- [x] DeliveryRouter 不再依赖 NotificationPort，直接注入 AlertManager
- [x] development 环境 CORS 固定为 localhost:3000
- [x] production 环境 CORS 通过 CORS_ORIGINS 环境变量控制

### 4.2 质量验收

- [x] `pixi run -e dev check` 全通过
- [x] 新增集成测试覆盖偏差报告端点（172 行）
- [x] 单元测试覆盖幂等性、`find_fill()`、DeliveryRouter 重构
- [x] 无 `HTTPException` 残留（统一使用 APIError 体系）
- [x] 架构约束无新增违规

---

## 5. 实现状态

**状态**: Done (2026-04-15)

所有功能已实现并通过验收。代码已合并至 `feat/v1-sprint` 分支（commit `914713c1`）。

### 代码统计

| 指标 | 数值 |
|------|------|
| 变更文件 | 21 |
| 新增代码 | +1,285 行 |
| 删除代码 | -196 行 |
| 新增测试 | ~374 行（5 个测试文件） |

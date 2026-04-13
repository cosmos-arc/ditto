# ADR 0007: 回测引擎 DataFeed 数据加载策略

**状态**: 已接受
**日期**: 2026-04-13
**决策者**: 架构团队
**相关 ADR**: [ADR 0003](0003-data-storage-strategy.md), [ADR 0006](0006-hybrid-plane-v2-accepted-deviations.md)

---

## 背景

因子表达式需要历史数据窗口（lookback）来计算指标值。例如：

- `rs(close, 20)` 需要前 20 个交易日收盘价
- `ts_mean(volume, 60)` 需要前 60 个交易日成交量
- Regime 检测（MomentumIndicator）需要额外 60 日默认 lookback

回测引擎按交易日步进（EngineLoop），若 DataFeed 仅加载 `config.start_date` 之后的数据，则回测首 N 日（N = max_lookback）的因子值全部为 null。这导致：

| 问题 | 影响 |
|------|------|
| **首 N 日因子缺失** | 信号、评分、排序全部为空，前 N 个换仓日无法产生有效订单 |
| **策略收益低估** | 首段空白期的 NAV 平坦，拉低整体收益指标 |
| **冷启动不可控** | lookback 大小随策略配置变化，用户无法预测"热身期"长度 |

---

## 决策

### 决策 1：DataFeed 数据加载起点向前扩展

`StrategyServiceFactory._build_backtest_runtime()` 在构造 `ProviderBackedDataFeed` 时，将 `start_date` 向前偏移 `max_lookback * 2` 个日历日：

```python
# packages/app/src/ditto_app/builders/service_factory.py

max_lookback = _compute_max_lookback(runtime.compiled_expressions)
data_start_date = _shift_back_calendar_days(config.start_date, max_lookback * 2)

data_feed = ProviderBackedDataFeed(
    self._data_provider,
    tickers=tickers,
    start_date=data_start_date,  # 向前扩展
    end_date=config.end_date,
    id_map=id_map,
    benchmark_id=resolved_config.benchmark_id,
)
```

`max_lookback` 的计算方式：

- 优先取编译后因子表达式的最大 `expr.analysis.lookback`
- 兜底值为 `_REGIME_DEFAULT_LOOKBACK = 60`（覆盖 MomentumIndicator 等内置 lookback）
- `* 2` 将交易日转换为日历日（中国 A 股约 5/7 = 0.71 的交易日比例，乘以 2 留有余量）

### 决策 2：EngineLoop 步进区间不变

`EngineLoop.run()` 从 DataFeed 获取完整交易日列表后，过滤到 `config.start_date` 之后：

```python
# packages/engine/src/ditto_engine/backtest/engine.py

days = self._data_feed.trading_days()
trading_days = [d for d in days if d >= self._config.start_date]
```

引擎仅步进用户配置的回测区间，不受 DataFeed 数据加载起点影响。

---

## 后果

### 积极面

- **因子预热问题解决**：回测首日即可获得完整的因子值，信号生成正常
- **引擎步进区间不变**：用户配置的 `start_date` / `end_date` 语义不变
- **自适应 lookback**：根据策略编译结果动态计算，无需用户手动指定
- **向后兼容**：`get_slice()` / `get_history()` 接口无变更

### 消极面

- **数据加载量增加**：额外加载 `max_lookback * 2` 个日历日的行情数据，对长期回测（如 10 年）增加约 0.3-0.5% 的数据量
- **交易日 / 日历日转换不精确**：`* 2` 是近似值，极端情况下可能多加载或不足。当前基于"宁可多加载"原则，影响可忽略

---

## 考虑的替代方案

### 方案 A：用户手动指定 warm-up 期

在 `CreateBacktestRunRequest` 中添加 `warmup_days` 参数。

**拒绝理由**：增加 API 复杂度；用户需理解因子 lookback 语义才能正确设置；容易遗漏或设置错误。

### 方案 B：DataFeed 接口增加 lookback 参数

修改 `DataFeed.__init__` 接受 `lookback_days` 参数，内部自动扩展。

**拒绝理由**：DataFeed 是 Engine 层协议，lookback 是 App 层编排关注点。将编排逻辑下沉到 Engine 层违反分层原则。

### 方案 C：引擎内部跳过首 N 日

EngineLoop 自动跳过前 `max_lookback` 个交易日，不生成订单。

**拒绝理由**：改变了用户配置的 `start_date` 语义 — 用户期望从 `start_date` 开始计算收益，而非跳过。

---

## 相关决策

- [ADR 0003 - Data Storage Strategy](0003-data-storage-strategy.md)：数据加载依赖 Parquet 存储的高效列读取
- [ADR 0006 - Hybrid Plane v2 已接受偏离 D4](0006-hybrid-plane-v2-accepted-deviations.md)：DataProvider 位于 Data 层，Engine 层通过 Protocol 解耦

---

**文档版本**: 1.0
**最后更新**: 2026-04-13

# 实时流数据管道设计 v2

**状态**: ✅ 已确认

**创建日期**: 2026-03-08

**版本**: v2（基于 v1 讨论更新）

---

## 1. 设计目标

为 Ditto 因子引擎提供可靠的实时行情数据流，支持：
- 盘中实时因子计算
- 多消费者解耦（因子引擎、风控系统、监控告警）
- 断点续传与数据可靠性保障

---

## 2. 核心决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 消息队列 | **Kvrocks Streams** | 已部署，复用现有组件 |
| 交互模式 | **推拉结合** | 推送获取实时数据 + 定时拉取确保完整性 |
| 消费语义 | **At-Least-Once** | 简单可靠，配合幂等处理 |
| Stream 分片 | **按类型分 Stream** | 平衡复杂度和扩展性 |

---

## 3. 数据范围

### 3.1 MVP 阶段数据类型

| 数据类型 | 是否包含 | 说明 |
|---------|---------|------|
| 股票分钟K线 | ✅ | 全市场股票 OHLCV |
| 指数分钟K线 | ✅ | 宽基指数 + 行业指数 |
| Tick 快照 | ⚠️ Phase 2 | 买卖五档，用于风控/盘口分析 |

### 3.2 指数列表

**宽基指数**（6个）：
- 沪深300 (000300.SH)
- 中证500 (000905.SH)
- 中证1000 (000852.SH)
- 上证50 (000016.SH)
- 创业板指 (399006.SZ)
- 上证指数 (000001.SH)

**行业指数**（可选，Phase 2）：
- 申万一级行业指数（31个）

---

## 4. 架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              实时流数据管道架构                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          数据摄入层 (Ingestion)                              │   │
│  │                                                                             │   │
│  │  ┌───────────────────────┐    ┌───────────────────────┐                    │   │
│  │  │ 路径 1: 股票分钟K线     │    │ 路径 2: 指数分钟K线     │                    │   │
│  │  │                       │    │                       │                    │   │
│  │  │ 定时器驱动（每分钟末）  │    │ 定时器驱动（每分钟末）  │                    │   │
│  │  │ get_full_kline        │    │ get_market_data_ex    │                    │   │
│  │  │ + 增量提取             │    │ (count=1)             │                    │   │
│  │  └───────────────────────┘    └───────────────────────┘                    │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                       │                                             │
│                                       ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                     消息缓冲层 (Kvrocks Streams)                             │   │
│  │                                                                             │   │
│  │  Stream: realtime:kline:1m        Stream: realtime:index:1m                 │   │
│  │       │                                   │                                  │   │
│  │  (股票分钟K线)                       (指数分钟K线)                            │   │
│  │  MAXLEN ~500K/日                    MAXLEN ~15K/日                          │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                       │                                             │
│                                       ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          消费处理层 (Consumers)                              │   │
│  │                                                                             │   │
│  │  Consumer Group: factor-engine     Consumer Group: risk-monitor             │   │
│  │       │                                   │                                  │   │
│  │       ▼                                   ▼                                  │   │
│  │  [因子引擎]                          [风控系统]                               │   │
│  │       │                                   │                                  │   │
│  │       └──────────────────┬─────────────────┘                                  │   │
│  │                           │                                                  │   │
│  │                           ▼                                                  │   │
│  │                    ┌───────────────┐                                         │   │
│  │                    │   QuestDB     │                                         │   │
│  │                    │   (持久化)     │                                         │   │
│  │                    └───────────────┘                                         │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 关键设计：定时器驱动的分钟K线获取

**为什么不用 callback 驱动？**

`subscribe_whole_quote` 只推送**有变化**的股票，如果某分钟没有成交，callback 不会被触发，导致分钟K线数据丢失。

**解决方案**：使用独立定时器，每分钟第 57 秒主动拉取 K 线数据。

```python
class MinuteKlineProducer:
    """分钟K线生产者（定时器驱动）"""

    def __init__(self):
        self.stock_list: list[str] = []
        self.index_list: list[str] = []
        self.last_minute: int = 0
        self._stop_event = threading.Event()

    def start(self):
        """启动定时器"""
        # 初始化股票/指数列表
        self.stock_list = xtdata.get_stock_list_in_sector('沪深A股')
        self.index_list = ['000300.SH', '000905.SH', '000016.SH',
                          '399006.SZ', '000852.SH', '000001.SH']

        # 启动定时器线程
        timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        timer_thread.start()

    def _timer_loop(self):
        """定时器循环：每分钟第 57 秒触发"""
        while not self._stop_event.is_set():
            now = datetime.now()

            # 在每分钟第 57 秒触发
            if now.second == 57:
                self._fetch_klines()

            time.sleep(1)

    def _fetch_klines(self):
        """获取分钟K线"""
        current_minute = int(time.time() // 60)

        if current_minute > self.last_minute:
            # 股票K线：使用 get_full_kline + 增量提取
            # get_full_kline 返回当日所有分钟数据（随时间增长）
            # 需要根据 last_minute 只提取新增的 K 线
            all_stock_klines = xtdata.get_full_kline(
                stock_list=self.stock_list,
                period='1m'
            )
            new_stock_klines = self._extract_new_klines(all_stock_klines, self.last_minute)
            self._write_to_stream('realtime:kline:1m', new_stock_klines)

            # 指数K线：使用 get_market_data_ex(count=1)
            # 指数数量少，直接获取最新一条即可
            index_klines = xtdata.get_market_data_ex(
                field_list=[],
                stock_list=self.index_list,
                period='1m',
                count=1,
                dividend_type='none'
            )
            self._write_to_stream('realtime:index:1m', index_klines)

            self.last_minute = current_minute

    def _extract_new_klines(self, all_klines: dict, last_minute: int) -> dict:
        """从全量数据中提取新增的分钟K线"""
        new_klines = {}
        for code, df in all_klines.items():
            # 筛选出时间戳大于 last_minute 的记录
            df['minute'] = df['time'] // 60  # 假设 time 是秒级时间戳
            new_df = df.filter(df['minute'] > last_minute)
            if len(new_df) > 0:
                new_klines[code] = new_df
        return new_klines
```

---

## 5. API 能力确认

### 5.1 subscribe_whole_quote

| 特性 | 说明 |
|------|------|
| **触发频率** | ~3秒（由数据源决定，非可控） |
| **推送条件** | 只推送**有变化**的股票 |
| **数据范围** | `['SH', 'SZ']` = 股票全市场，**不含指数** |
| **返回格式** | `dict {stock: tick_data, ...}` 多标的批量返回 |

### 5.2 get_full_kline

| 特性 | 说明 |
|------|------|
| **返回数据** | 最新交易日所有分钟K线（随时间增长） |
| **适用场景** | **股票全市场**（5000+ 股票，get_market_data_ex 传入完整列表性能差） |
| **推荐用法** | **必须配合本地增量提取**，只处理新增的分钟K线 |

### 5.3 get_market_data_ex

| 特性 | 说明 |
|------|------|
| **count 参数** | 控制返回条数，`count=1` 只返回最新一条 |
| **适用场景** | **指数**（数量少，~10个） |
| **推荐用法** | 指数用 `count=1`，避免数据量随时间增长 |

### 5.4 指数订阅

指数**不在** `subscribe_whole_quote(['SH', 'SZ'])` 范围内，需要**单独订阅**：

```python
# 指数需要单独订阅
index_list = ['000300.SH', '000905.SH', '000016.SH', '399006.SZ']
xtdata.subscribe_quote(index_list, period='1m', callback=on_index_data)
```

---

## 6. Stream 设计

### 6.1 Stream 分片

| Stream 名称 | 数据类型 | 估算量/日 | MAXLEN |
|------------|---------|----------|--------|
| `realtime:kline:1m` | 股票分钟K线 | ~5000 × 240 = 1.2M | ~2M |
| `realtime:index:1m` | 指数分钟K线 | ~10 × 240 = 2.4K | ~10K |

### 6.2 消息格式

**股票/指数分钟K线**：

```json
{
  "seq": 123456789,
  "code": "000001.SZ",
  "trade_time": "20260308103000",
  "open": 11.50,
  "high": 11.55,
  "low": 11.48,
  "close": 11.52,
  "volume": 1234567,
  "amount": 14234567.89,
  "source": "realtime",
  "ts": 1741422600000
}
```

### 6.3 消息写入策略

| 策略 | 描述 | 选择 |
|------|------|------|
| 批量写入 | 每条消息包含多只股票 | ❌ 不选 |
| **单条写入** | 每只股票单独一条消息 | ✅ 选择 |

**理由**：
- 单条写入便于消费端按标的过滤
- 便于实现幂等消费（按 code + trade_time 去重）
- 消息大小可控

---

## 7. 可靠性保障

### 7.1 生产者端

| 机制 | 实现 |
|------|------|
| **定时器保障** | 独立线程，不依赖 callback |
| **心跳检测** | Producer 每 30s 发送心跳到 `realtime:heartbeat` |
| **异常恢复** | 定时器异常后自动重启 |

### 7.2 数据完整性校验

**盘中检测**（每 5 分钟）：
```python
def check_data_completeness():
    last_time = get_stream_last_time('realtime:kline:1m')
    expected_time = get_last_trading_minute()

    if (expected_time - last_time) > 5min:
        trigger_alert("数据延迟超过 5 分钟")
```

**盘后对账**（每日 18:00）：
```python
def daily_reconciliation():
    # 对比 Stream 数据量与预期
    actual_count = count_stream_messages('realtime:kline:1m')
    expected_count = stock_count * 240

    if actual_count < expected_count:
        # 从 Tushare 补齐
        tushare_backfill(missing_codes, missing_times)
```

### 7.3 消费者端

| 机制 | 实现 |
|------|------|
| **消费语义** | At-Least-Once |
| **ACK 时机** | QuestDB 写入成功后 |
| **幂等性** | QuestDB 主键 (code, trade_time) 去重 |

---

## 8. 运维考虑

### 8.1 盘后清理

```python
# 每日收盘后清理（保留最近 3 天）
XTRIM realtime:kline:1m MAXLEN ~6000000  # 3天数据
XTRIM realtime:index:1m MAXLEN ~10000
```

### 8.2 监控指标

| 指标 | 阈值 | 告警 |
|------|------|------|
| Stream 消息堆积 | Pending > 10000 | WARNING |
| 心跳超时 | > 60s 无心跳 | ERROR |
| 数据延迟 | 最新数据 > 5min 前 | ERROR |

---

## 9. Phase 2 扩展（可选）

### 9.1 Tick 快照流

```
Stream: realtime:tick:snapshot

用途：
- 实时风控（价格异动监控）
- 盘口分析（买卖力量判断）
- 日内短线策略

数据量：~5000 股票 × 80 次/天 = 400K 条/天
```

### 9.2 行业指数扩展

```
新增 Stream: realtime:sector:1m

指数列表：
- 申万一级行业指数（31个）

用途：
- 行业轮动策略
- 行业中性化因子
```

---

## 10. 相关文档

- [ADR-023: 灾备恢复策略](../design/unified-feature-factor-engine/decisions/adr-023-disaster-recovery.md)
- [ADR-020: 部署与运维](../design/unified-feature-factor-engine/decisions/adr-020-deployment-ops.md)
- [v1 设计文档](./2026-03-06-realtime-stream-pipeline-design.md)（已归档）

---

## 11. 更新记录

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-03-06 | v1 | 初始创建，早期讨论 |
| 2026-03-08 | v2 | 基于 API 能力调研重构设计，确认定时器驱动模式 |
| 2026-03-08 | v2.1 | 修正股票/指数 API 差异：股票用 `get_full_kline`+增量提取，指数用 `get_market_data_ex` |

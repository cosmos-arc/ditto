# 存储与执行架构修订计划

> **状态**: 历史修订稿，仅供参考。
> **说明**: 本文档形成于 `ADR-026 ~ ADR-031` 收敛前后，当前关于 retention、state namespace、shadow publish、compatibility manifest 的正式口径已由后续文档覆盖。当前执行请优先参考：
> - [README.md](README.md)
> - [main-design.md](main-design.md)
> - [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

**文档状态**: 历史修订稿

**创建日期**: 2026-03-10

**目标**: 基于四条核心原则，增量修订现有设计，明确各存储职责边界与执行分层策略

---

## 1. 核心原则（四条铁律）

| 原则 | 含义 | 影响 |
|------|------|------|
| **真相只存一次** | Parquet 是唯一长期真相层 | QuestDB/Kvrocks 均为可重建派生层 |
| **热层只存够用的 lookback** | QuestDB 按业务需求配置 TTL | 不做全历史存储，分钟热层 60-120 天 |
| **状态和分析分开** | Kvrocks 存最新状态，QuestDB/Polars 负责时序分析 | 职责边界清晰 |
| **表达式语义统一，物理执行分层** | FeatureSpec 是语义源头 | 执行器可下推 QuestDB 或 Polars 计算 |

---

## 2. 存储职责边界

### 2.1 六大组件定位

| 组件 | 职责 | 不负责 |
|------|------|--------|
| **Parquet** | 唯一真相层、历史归档、可回放可重算 | 盘中实时查询、状态管理 |
| **QuestDB** | 盘中热查询、lookback、SAMPLE BY、MV、热点因子 | 全历史唯一真相、元数据治理 |
| **Kvrocks** | 最新状态、缓存、队列、排名、触发器 | 历史明细、SQL 聚合 |
| **SQLite** | 数据目录、元数据、任务控制、血缘、审计 | 大数据存储、热点查询 |
| **Polars** | 统一表达式语义、批量计算、研究回测 | 存储 |
| **DuckDB** | ADHOC SQL、临时审计、Parquet/SQLite 联查 | 常驻服务、API 后端、共享热层 |

### 2.2 与现有设计对比

| 组件 | 现有定位 | 修订后定位 | 变化 |
|------|---------|-----------|------|
| Parquet | 持久层 | **唯一真相层** | 强调不可替代性 |
| QuestDB | 温层存储 | **盘中热层 + TTL + MV** | 明确 TTL 策略 |
| Kvrocks | 状态管理 | **只存"现在"** | 无变化（已一致） |
| SQLite | 元数据 | 元数据 | 无变化 |
| Polars | 计算引擎 | **统一语义层 + 主计算引擎** | 强调语义源头 |
| DuckDB | 冷层引擎 | **ADHOC/审计工具** | **降级为工具角色** |

---

## 3. 修订清单

### 3.1 需要新增的 ADR

| 编号 | 标题 | 说明 | Phase |
|------|------|------|-------|
| ADR-026 | DuckDB 定位与使用规范 | 明确降级为 ADHOC 工具，不做常驻服务 | 1.2 |
| ADR-027 | 表达式 Pushdown 策略 | 三层判定：能力层 + 模式层 + 开关层 | 1.3 |
| ADR-028 | QuestDB 热表与物化视图 DDL | 热表设计、TTL 策略、SAMPLE BY 物化视图 | 1.2 |
| ADR-029 | 盘中实时路径与盘后批量路径 | 因子分级（SERIES/STATE/DERIVE/OFFLINE）+ 路径分离 | 1.4 |
| ADR-030 | Online Data Access Boundary | Parquet 隔离：接口隔离 + 运行时模式 + 可观测性 + 降级显式 | 1.2 |
| ADR-031 | State Snapshot ABI | 简单状态用 Hash，复杂状态用 versioned blob | 1.2 |

### 3.2 需要废弃的 ADR

| 编号 | 标题 | 废弃原因 |
|------|------|---------|
| ADR-016 | Catalog 存储架构 | ✅ 已合并到 ADR-010（2026-03-07） |
| ADR-025 | DuckDB 统一数据架构 | 🔄 本次新增废弃 — 改用 ADHOC 定位（ADR-026） |

### 3.3 需要大幅修订的 ADR

| 编号 | 当前内容 | 修订内容 |
|------|---------|---------|
| ADR-011 | 流式模式架构（ReactiveStateEngine、温层 QuestDB） | 移除流式引擎概念，存储拆分到 ADR-028，重定位为"盘中微批量处理模式" |
| ADR-023 | 灾备恢复策略（暂缓、依赖存储引擎自身持久化） | 明确"上游可重发"决策，盘中恢复=上游重发，历史回补=Parquet |

### 3.4 需要补充说明的 ADR

| 编号 | 补充内容 |
|------|---------|
| ADR-009 | 补充盘中/盘后路径分离说明，引用 ADR-029；更新流程图 |
| ADR-010 | 补充 `serve_mode` 字段（SERIES/STATE/DERIVE/OFFLINE），补充 Kvrocks key 结构变更 |
| ADR-012 | 补充 Pushdown 能力层信息，引用 ADR-027；补充状态快照格式引用 ADR-031 |
| ADR-017 | 补充盘中查询 API 路径，引用 ADR-030（Parquet 隔离）；补充 RuntimeMode 检查 |
| ADR-018 | 补充 `online_parquet_reads_total` 指标 |
| ADR-020 | 补充 DuckDB 作为 ADHOC 工具的使用说明，引用 ADR-026 |

### 3.5 无需修改的 ADR

| 编号 | 原因 |
|------|------|
| ADR-001~008 | TS/CS 嵌套、算子体系、表达式语法、因子清单、增量计算、标准化管线 — 与存储层无关 |
| ADR-013~015 | ts_rank 精度、表达式引擎核心、DAG 优化 — 计算层设计仍有效 |
| ADR-019 | 测试策略 — 测试分层仍有效 |
| ADR-021~022 | PIT 一致性、更正数据处理 — 数据一致性设计仍有效 |
| ADR-024 | 因子版本管理 — 版本管理机制仍有效 |

### 3.6 需要更新的主设计文档

| 文档 | 更新内容 |
|------|---------|
| main-design.md | 新增 0.1 核心原则章节 |
| README.md | 更新 ADR 索引（新增 ADR-026~031，废弃 ADR-025） |

---

## 4. 待确认问题清单

### 4.0 QuestDB + Kvrocks 热层设计（深度讨论）

> **状态**: ✅ 深度讨论已完成
>
> 在细化 TTL 等具体参数之前，需要先从整体架构层面讨论以下问题：

#### 4.0.1 热层数据范围与边界

> **状态**: ✅ 已确认

**三层分工架构**：

| 层级 | 存储 | 职责 | 典型数据 |
|------|------|------|---------|
| **长期真相层** | Parquet | 长期因子真相、历史归档、可回放可重算 | 长期研究因子、训练标签、实验性特征、复杂长窗口因子 |
| **热 lookback 层** | QuestDB | 热序列因子、时序查询、SAMPLE BY、MV | 短窗口收益、波动率、VWAP 偏离、breadth 统计、盘口因子 |
| **最新状态层** | Kvrocks | 最新值、状态、缓存、队列、触发器 | 最新信号、风控状态、持仓快照、排名、冷却状态 |

**核心原则**：
- **历史归 Parquet，热序列归 QuestDB，最新状态归 Kvrocks**

**判断标准**（三个问题，两个"是"就进 QuestDB）：
1. 是否需要**回看最近 N 天/N 分钟**？
2. 是否会被**多个模块反复查询**？
3. 是否适合**时序 SQL / 聚合 / 对齐**？

**三类数据处理方式**：

| 类型 | QuestDB | Kvrocks | Parquet | 示例 |
|------|---------|---------|---------|------|
| **第一类：只放 Kvrocks** | ❌ | ✅ | ❌ | 最新信号、最新风控状态、最新持仓快照、最新排名/观察池、下单冷却状态 |
| **第二类：QuestDB + Kvrocks** | ✅（完整热序列） | ✅（最新一条） | ❌ | 短窗口收益/波动率、VWAP 偏离、成交额/量能强弱、ETF 溢折价、breadth 统计、盘口不平衡 |
| **第三类：只进 Parquet** | ❌ | ❌ | ✅ | 长期研究因子、训练标签、实验性特征、复杂长窗口因子 |

**查询路径**：
- 看最近 N 天某因子的轨迹、分位、历史上下文 → **QuestDB**
- 拿某个标的当前最新因子值做交易决策 → **Kvrocks**
- 做长期研究/回测/训练 → **Parquet**

#### 4.0.2 Kvrocks 在热层的角色

> **状态**: ✅ 已确认

**核心原则**：
- **Kvrocks TTL 是 key 级别**，不是 field/member 级别
- **不要让 TTL 替代"交易日切换逻辑"**
- **尽量在 value 里放元信息**（asof_ts, trade_date, calc_ver）
- **需要不同生命周期就拆 key**

**Key 设计与 TTL 策略**：

| 类别 | Key Pattern | 结构 | TTL | 说明 |
|------|-------------|------|-----|------|
| 最新因子值 | `state:feature:{factor}:{sid}` | String/Hash | **2-7 天** | 是缓存/热状态，非唯一真相；value 必须带 `asof_ts`, `trade_date` |
| 最新信号 | `state:signal:{strategy}:{sid}` | String/Hash | **当日到 3 天** | 信号天然有时效性；value 带 `signal_ts`, `action`, `status` |
| 风控状态 | `state:risk:{account}:{sid}` | Hash | **无 TTL** | 权威状态，误过期风险大 |
| 持仓状态 | `state:position:{account}:{sid}` | Hash | **无 TTL** | 权威状态，误过期风险大 |
| 冷却状态 | `state:cooldown:{strategy}:{sid}` | String | **按冷却期** | 时效性约束，单独拆 key |
| 排名/观察池 | `rank:watchlist:{bucket}` | ZSet | **看用途** | 当前榜单可无 TTL；历史快照 3-15 天 |

**总结原则**：
> **缓存和时效对象要 TTL；权威状态不要 TTL；需要不同生命周期就拆 key**

**与 QuestDB 分工**：
- 看 N 天历史/轨迹/分位 → **QuestDB**
- 拿当前最新值做交易决策 → **Kvrocks**

#### 4.0.3 数据流路径

> **状态**: ✅ 已确认

**盘中实时写入路径**：

```
上游行情 → Kvrocks Streams（队列中转）
         → 消费者写入 QuestDB（bar 表）
         → 因子计算
         → Kvrocks（最新因子值）
```

**热层到冷层归档**：
- **不归档** — QuestDB 热层通过 TTL 自动过期
- Parquet 是唯一真相层，由 Tushare 等数据源独立写入
- 分钟数据不在 Parquet 中保留（与 ADR-023 一致）

**冷层到热层回补**：

| 场景 | 触发方式 | 说明 |
|------|---------|------|
| **定时回补** | 每日盘后→盘前 | Parquet 数据计算完成后自动灌入 QuestDB |
| **触发式回补** | 主动触发（CLI/API） | 收到触发信号后自动回补 |

**数据流总览**：

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据流总览                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  【盘后批量路径】                                                 │
│                                                                  │
│  Tushare/数据源 → Parquet（唯一真相层）                           │
│                        │                                         │
│                        ▼                                         │
│                  Polars 因子计算                                  │
│                        │                                         │
│                        ▼                                         │
│           ┌───────────┴───────────┐                              │
│           ▼                       ▼                              │
│     QuestDB（热层回补）      Kvrocks（状态初始化）                 │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  【盘中实时路径】                                                 │
│                                                                  │
│  行情源 → Kvrocks Streams（队列）                                 │
│                │                                                 │
│                ▼                                                 │
│          消费者处理                                               │
│                │                                                 │
│                ▼                                                 │
│           QuestDB（bar 表写入）                                   │
│                │                                                 │
│                ▼                                                 │
│          因子计算（热点因子）                                      │
│                │                                                 │
│                ▼                                                 │
│           Kvrocks（最新因子值）                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.0.4 查询模式

> **状态**: ✅ 已确认

**核心原则**：
> **盘中主链路不查 Parquet；如果盘中需要一个原本在 Parquet 的因子，就把它升级成 A/B/C 类**

**因子分级模型（A/B/C/D 四类）**：

| 类别 | 特点 | 存储 | 例子 |
|------|------|------|------|
| **A 类：实时热因子** | 盘中高频反复用 | QuestDB 热序列 + Kvrocks 最新值 | 5m/20m 收益、20m 波动率、VWAP 偏离、盘口不平衡、ETF 溢折价 |
| **B 类：盘前冷算+盘中热更新** | 需要长历史背景 | 盘前 Parquet 算初值，盘中 QuestDB 增量/Kvrocks 快照 | 252d 波动率、120d/250d 趋势、长周期行业 regime、中长期 beta |
| **C 类：盘中按需现算** | 不预存 | 从 QuestDB 热基础数据小窗现算 | 临时 37m 偏离度、策略专用组合特征、临时诊断指标 |
| **D 类：纯冷因子** | 只在研究/训练用 | Parquet/Polars | 不进入盘中主链路 |

**盘中禁止直接查 Parquet 的场景**：
- 自动下单
- 自动风控
- 实时排序
- 盘中信号触发

**允许查 Parquet 的场景**：
- 盘前预计算
- 盘后重算
- 审计对拍
- 人工研究
- 低频临时诊断

**因子升级机制**：
如果某个因子满足以下任意一条，就不能只留在 Parquet：
- 盘中自动下单要用
- 盘中风控要用
- 盘中人工决策频繁要看
- 每分钟会重复计算很多次
- 依赖的长历史在盘前可以预先摘要

升级选项（三选一）：
1. **预存热序列** 到 QuestDB
2. **预存最新快照** 到 Kvrocks
3. **预存盘前快照 + 盘中基于 QuestDB 增量更新**

#### 4.0.5 典型场景梳理

> **状态**: ✅ 已确认

**场景 1：盘中因子计算**（A 类因子）

```
QuestDB bar_1m_hot (最近 20m bar)
        │
        ▼
   Polars 小窗计算
   (ts_mean, ts_std, ts_rank...)
        │
        ├──────────────────────┐
        ▼                      ▼
QuestDB f_1m_hot        Kvrocks state:feature:{factor}:{sid}
(完整热序列)            (最新值 + asof_ts + trade_date)
```

**场景 2：策略信号触发**（B 类因子）

```
Kvrocks state:feature:{factor}:{sid} (最新因子值)
        │
        ├──────────────────────┐
        ▼                      ▼
QuestDB bar_1m_hot       策略逻辑判断
(实时行情补充)            (信号条件检查)
        │                      │
        └──────────────────────┘
                    │
                    ▼
        Kvrocks state:signal:{strategy}:{sid}
        (signal_ts, action, strength, status)
```

**场景 3:风控监控**

```
Kvrocks state:position:{account}:{sid} (当前持仓)
        │
        ├──────────────────────┐
        ▼                      ▼
Kvrocks state:risk:{account}:{sid}   QuestDB bar_1m_hot
(风控因子/敞口)                 (实时行情)
        │                      │
        └──────────────────────┘
                    │
                    ▼
            风控规则检查
                    │
                    ├─────────────────────┐
                    ▼                     ▼
        Kvrocks state:risk:{account}:{sid}   Kvrocks state:cooldown:{strategy}:{sid}
        (风控状态更新，无 TTL)    (冷却期，有 TTL)
```

**场景 4:盘后重算回补**

```
Parquet (market/cn/bar_1d, bar_1m)
        │
        ▼
   Polars 批量重算
   (全量或增量因子)
        │
        ├──────────────────────┬──────────────────────┐
        ▼                      ▼                      ▼
Parquet (factors/)         QuestDB f_1m_hot       Kvrocks state:feature:*
(长期真相层)             (热层回补，按 TTL)      (状态重建/初始化)
````

---

**四个场景与存储层的映射**：

| 场景 | Parquet | QuestDB | Kvrocks |
|------|--------|--------|---------|
| 盘中因子计算 | ❌ | ✅ 读 bar 表， ✅ 写热序列 + 最新值 |
| 策略信号触发 | ❌ | ✅ 读 bar 表 | ✅ 读因子 + 写信号 |
| 风控监控 | ❌ | ✅ 读 bar 表 | ✅ 读持仓/风控 + 写状态 |
| 盘后重算回补 | ✅ 读/写因子 | ✅ 回补热层 | ✅ 初始化状态 |

---

### 4.1 QuestDB 热层设计（ADR-028）

> **状态**: ✅ 已确认

#### 热表设计

| 表名 | 数据类型 | 分区 | TTL | 说明 |
|------|---------|------|-----|------|
| `bar_1m_hot` | 分钟 K 线 | `PARTITION by day` | **120 DAYS** | 全市场股票 + ETF + 指数 |
| `lob_5s_hot` | 5 秒盘口摘要 | `partition by day` | **20 DAYS** | 全市场 |
| `lob_1m_mv` | 1 分钟盘口摘要 | `partition by month` | **120 DAYS** | 从 5s 聚合，物化视图 |
| `lob_1s_hot` | 1 秒盘口摘要 | `partition by day` | **3-5 DAYS** | 仅重点标的（可选） |
| `f_1m_hot` | 热点分钟因子 | `partition by day` | **120 DAYS** | A 类因子热序列 |
| `bar_15m_mv` | 15 分钟聚合 | `partition by month` | **180 DAYS** | 从 1m 聚合，物化视图 |
| `bar_60m_mv` | 60 分钟聚合 | `partition by month` | **365 DAYS** | 从 1m 聚合，物化视图 |

#### 盘口因子窗口设计

**四档回看窗口**：

| 窗口 | 用途 | 说明 |
|------|------|------|
| **15 秒** | 极短执行/风控 | spread 扩张、扫单后恢复、进场过滤 |
| **60 秒** | 短时确认 | 平滑确认、过滤假信号 |
| **5 分钟** | 和 1m/5m K 线协同 | 盘口强弱与价量融合 |
| **15 分钟** | 背景分位/上下文 | 当前值相对历史分位判断异常 |

#### 韨选盘口因子（Phase 1）

| 因子 | 说明 | 窗口 |
|------|------|------|
| spread | bid-ask 价差 | 实时 |
| mid | 中间价 | 实时 |
| top1_imbalance | 第一档不平衡 | 实时 |
| top5_imbalance | 前五档不平衡 | 实时 |
| top5_depth_sum | 前五档深度和 | 实时 |
| book_pressure_ratio | 买卖压力比 | 实时 |
| depth_slope_proxy | 深度斜率代理 | 实时 |

**盘口数据原则**：
> **盘口数据最值得做的是"5 秒采样 + 多窗口摘要"，不是全市场长期保存原始全深度变动流。**

---

### 4.2 Pushdown 策略（ADR-027）

> **状态**: ✅ 已确认

**下推范围**：基础 + 简单因子

**首版下推白名单**：
- 1m/5m/15m/60m OHLCV bars
- session VWAP
- cumulative volume / amount
- rolling sum/mean/min/max/count（短窗口）
- simple return / rolling return
- short rolling vol
- ETF 溢折价序列
- `ASOF JOIN` 的指数/ETF/成分对齐
- 盘口不平衡、价差、前五档量差
- breadth: up/down counts, adv/dec ratio, turnover sums

**白名单管理策略**：混合方式

| 层级 | 管理 | 说明 |
|------|------|------|
| **代码定义** | 能力白名单 | 定义哪些算子**可以**下推 |
| **SQLite 配置** | 启用控制 | 运行时控制哪些算子**实际启用**下推 |

**失败处理策略**：记录日志，可见回退 Polars

| 情况 | 行为 |
|------|------|
| QuestDB 不支持某算子 | 日志 WARNING + 回退 Polars |
| QuestDB 执行超时 | 日志 ERROR + 回退 Polars |
| QuestDB 执行报错 | 日志 ERROR + 回退 Polars |

**设计原则**：
> **统一语义，不统一物理实现**。表达式语义只定义一次在 Polars/FeatureSpec，QuestDB 只是可下推后端，不是语义源头。

### 4.3 DuckDB 定位（ADR-026）

> **状态**: ✅ 已确认

**决策**：保留，但降级为 ADHOC/审计工具

| 场景 | 是否允许 | 说明 |
|------|---------|------|
| ADHOC SQL 查询 | ✅ 允许 | 临时分析、快速探索 |
| 审计对拍 | ✅ 允许 | 独立视角验证数据 |
| Parquet/SQLite 联查 | ✅ 允许 | DuckDB 直接读取很方便 |
| 常驻服务 | ❌ 禁止 | 并发模型不支持 |
| API 后端 | ❌ 禁止 | 单进程读写/多进程只读限制 |
| 共享热层 | ❌ 禁止 | 不适合扛主并发读写 |
| 研究场景 | ⚠️ 不推荐 | 优先统一用 Polars |

**一句话定位**：
> **DuckDB 是临时刀，不是主仓库。**

### 4.4 盘中/盘后路径（ADR-029）

> **状态**: ✅ 已确认

**盘中实时路径**：Phase 2 完整实现

| Phase | 内容 |
|-------|------|
| **Phase 1** | 批量路径（Parquet → Polars → QuestDB/Kvrocks） |
| **Phase 2** | 盘中实时路径完整实现 |

**回补机制**：

| 触发方式 | 说明 | 实现时机 |
|---------|------|---------|
| **定时回补** | 每日盘后→盘前自动 | Phase 1 |
| **触发式回补** | CLI/API 主动触发 | Phase 1 |
| **自动检测回补** | 基于数据质量监控 | Phase 2（可选） |

### 4.5 灾备策略（ADR-023 修订）

> **状态**: ✅ 已确认

**分钟级数据灾备**：上游可重发

**QuestDB 恢复流程**：从 Parquet 回补为主，盘中缺口由数据源重放补齐

```
QuestDB 故障恢复流程：
    │
    ├─ 1. 判断故障范围
    │      ├─ 仅热数据丢失 → 从 Parquet 回补
    │      └─ 包含分钟数据 → 从数据源重放
    │
    ├─ 2. 从 Parquet 回补
    │      └─ Parquet bar_1d → QuestDB bar_1m_hot（如适用）
    │
    ├─ 3. 从数据源重放（如需要）
    │      └─ 上游支持断点续传 → 重放分钟数据
    │
    └─ 4. 重建状态
           └─ Polars 重算因子 → Kvrocks 状态初始化
```

**核心原则**：
> **QuestDB 和 Kvrocks 均为可重建派生层，Parquet 是唯一真相层。**

---

## 5. 数据分层命名

**决策**: 保持现有命名，不采用 Bronze/Silver/Gold

| 层级 | 现有路径 | 职责 |
|------|---------|------|
| 原始层 | `market/`, `fundamental/`, `capital/` | 供应商原始落地 |
| 标准层 | `market/cn/bar_1d/`, `market/cn/bar_1m/` | 统一 canonical 数据 |
| 派生层 | `features/`, `factors/` | 特征与因子 |

---

## 6. 实施顺序建议

```
Phase 1.1: 核心原则确立
    └── 更新 main-design.md（0.1 核心原则章节）

Phase 1.2: 存储职责明确
    ├── ADR-026: DuckDB 定位
    ├── ADR-028: QuestDB 热表 DDL
    └── 更新 ADR-011: 流式模式（补充 TTL/MV）

Phase 1.3: 执行分层
    └── ADR-027: Pushdown 策略

Phase 2.1: 路径设计
    ├── ADR-029: 盘中/盘后路径
    └── 更新 ADR-023: 灾备策略
```

---

## 7. 下一步行动

核心决策已全部确认，下一步：

1. ✅ ~~逐一确认待确认问题（Section 4）~~ — 已完成
2. **按顺序编写/修订 ADR**
   - ADR-026: DuckDB 定位与使用规范
   - ADR-027: 表达式 Pushdown 策略
   - ADR-028: QuestDB 热表与物化视图 DDL
   - ADR-029: 盘中实时路径与盘后批量路径
   - ADR-011 修订: 补充 QuestDB TTL/MV/热层定位
   - ADR-023 修订: 更新灾备恢复策略
3. **更新 main-design.md**（新增 0.1 核心原则章节）
4. **更新 README.md**（ADR 索引）

---

## 附录：相关文档

- [main-design.md](main-design.md) - 主设计文档
- [ADR-011](decisions/adr-011-streaming-mode.md) - 流式模式架构设计
- [ADR-023](decisions/adr-023-disaster-recovery.md) - 灾备恢复策略
- [realtime-stream-pipeline-design-v2.md](../../plans/2026-03-08-realtime-stream-pipeline-design-v2.md) - 实时流数据管道设计

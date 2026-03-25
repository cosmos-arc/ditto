# 日频策略底层能力完备度缺口分析

**日期**: 2026-03-18
**状态**: 待实施
**范围**: 仅覆盖因子/特征摄取、计算、获取能力层，不包含回测和策略框架

---

## 总览

| 能力层 | 当前完备度 | 目标 | P0 | P1 | P2 |
|--------|-----------|------|----|----|-----|
| 数据摄取 | 90% | 100% | 3 | 7 | 5 |
| 因子表达式引擎 | 80% | 100% | 5 | 6 | 7 |
| 物化 + 存储 + 查询 | 85% | 100% | 3 | 4 | 4 |
| 评估 + 发布安全 + 失效传播 | 90% | 100% | 0 | 9 | 5 |
| 元数据 + 日历 + Universe + 研究数据集 + 配置 | 85% | 100% | 2 | 8 | 8 |

---

## 第一层：数据摄取

### P0

| ID | 缺口 | 位置 | 说明 |
|----|------|------|------|
| ING-DQ-1 | DQ YAML 规则为空 | `packages/datahub/config/dq/*.yaml` | OHLCV 无校验（负数、零成交量、极端值），零自动化数据质量检查 |
| ING-CU-1 | Cursor 读写器未实现 | `IngestionCursor` model 存在但无 reader/writer | 断点续传不可用 |
| ING-IC-1 | 指数成分 out_date 未跟踪 | index constituent adapter | PIT 查询在成分退出后仍返回该成分 |

### P1

| ID | 缺口 | 说明 |
|----|------|------|
| ING-SS-1 | list_status 无历史记录 | 停牌/退市状态无法 PIT 查询 |
| ING-ST-1 | ST/PT 状态变更无历史 | `is_st` 无 effective_from/to |
| ING-IC-2 | 指数权重硬编码 1.0 | 未采集实际权重 |
| ING-F-1 | 财报只取 6 个字段 | PE/PB/PS/ROE 等常用指标缺失 |
| ING-A-1 | 复权因子无按 ticker 回填 | 全量回填效率低 |
| ING-DQ-2 | Quarantine 基础设施未触发 | 异常数据不被自动隔离 |
| ING-FL-1 | FreezeManager 未接入摄入流程 | 数据冻结机制形同虚设 |

### P2

| ID | 缺口 | 说明 |
|----|------|------|
| ING-SS-2 | 无 IPO 日期过滤能力 | 无法排除上市 <60 天新股 |
| ING-C-1 | 缺股本变动数据 | 公司行动不完整 |
| ING-C-2 | 缺回购/配股数据 | 公司行动不完整 |
| ING-X-1 | 无摄入调度器 | T0/T1/T2/T3 需手动触发 |
| ING-X-2 | read-modify-write 竞态 | 并发写入不安全 |

---

## 第二层：因子表达式引擎

### P0

| ID | 缺口 | 位置 | 说明 |
|----|------|------|------|
| ENG-E-1 | ts_corr/ts_cov 注册但无 codegen | `codegen.py` | 表达式通过校验但 codegen 报错 |
| ENG-E-2 | Lookback off-by-1 | `analyzer.py` + `planner.py` | ts_mean(x,20) 返回 lookback=20，实际需 21 数据点 |
| ENG-E-3 | cs_zscore 除零 | `codegen.py:362-365` | 截面 std=0 时产生 Inf/NaN |
| ENG-E-4 | cs_scale 除零 | `codegen.py:359-361` | 所有值为零时分母为 0 |
| ENG-E-5 | ts_pct_change 除零 | `codegen.py:319-320` | shift(n) 为 0 时产生 Inf |

### P1

| ID | 缺口 | 影响来源 |
|----|------|---------|
| ENG-E-6 | ts_ema 未实现 | 阻塞 EMA/MACD，ADR-005 中 4 个因子 |
| ENG-E-7 | ts_decay_linear 未实现 | 阻塞线性衰减加权因子 |
| ENG-E-8 | 零个具体因子定义 | ADR-005 规划的 30 个因子未编写 DerivedSpec |
| ENG-E-9 | coalesce 未实现 | 无空值安全回退 |
| ENG-E-10 | group_rank/group_zscore 未实现 | 无行业分组标准化 |
| ENG-E-11 | 无循环依赖检测 | 自引用表达式可运行时死循环 |

### P2

| ID | 缺口 | 说明 |
|----|------|------|
| ENG-E-12 | L1 内存缓存无上限 | 长期运行进程内存泄漏 |
| ENG-E-13 | cs_winsorize 硬编码 3σ | 与 spec 定义的分位数 winsorize 不一致 |
| ENG-E-14 | 无表达式类型检查 | 类型错误到运行时才暴露 |
| ENG-E-15 | 窗口参数未校验正值 | ts_mean(x, -1) 静默接受 |
| ENG-E-16 | L2 缓存命中时双重解析 | 不必要 CPU 开销 |
| ENG-E-17 | 缺失标量算子 | log10/log2/floor/ceil/round |
| ENG-E-18 | 无算子 golden data 测试 | 无数学正确性基准验证 |

---

## 第三层：物化 + 存储 + 查询

### P0

| ID | 缺口 | 位置 | 说明 |
|----|------|------|------|
| MAT-M-1 | 读时无文件级分区裁剪 | `derived_artifact_reader.py` | 查 1 个月扫描全部年份文件 |
| MAT-M-2 | 无 Schema 演化支持 | `derived_artifact_writer.py` | 新旧 parquet schema 不一致时报错或丢列 |
| MAT-M-3 | 无版本/运行记录 GC | `derived_catalog_service.py` | SQLite 记录和磁盘 artifact 无限膨胀 |

### P1

| ID | 缺口 | 说明 |
|----|------|------|
| MAT-M-4 | 大数据集无内存管理 | 全量加载 OOM 风险 |
| MAT-M-5 | 多分区写入非事务性 | 部分写入失败后残留无法回滚 |
| MAT-M-6 | 增量物化粒度为整年文件 | 改 1 天需重写整个年分区 |
| MAT-M-7 | 多 spec 物化纯串行 | materialize_daily 无并发 |

### P2

| ID | 缺口 | 说明 |
|----|------|------|
| MAT-M-8 | ephemeral/metadata 写入无原子性 | 无 temp-rename 保护 |
| MAT-M-9 | 无可配置压缩设置 | 默认 Snappy |
| MAT-M-10 | Query→Evaluation 无显式适配器 | 需手动 select/drop 列 |
| MAT-M-11 | Catalog 无 unified dashboard 查询 | 无 spec+状态+运行时间一站式查询 |

---

## 第四层：评估 + 发布安全 + 失效传播

### P0

（无）

### P1

| ID | 缺口 | 说明 |
|----|------|------|
| EVAL-EV-1 | Sharpe 公式未减无风险利率 | sharpe = annual_return / annual_vol |
| EVAL-EV-2 | 无 Fama-MacBeth 回归 | 因子检验金标准 |
| EVAL-EV-3 | 无因子暴露分析 | 无法计算对风格因子的 beta |
| EVAL-EV-4 | 无尾部风险指标 | 缺 CVaR/偏度/峰度 |
| EVAL-EV-5 | 无 Regime-Adjusted IC | 无法按市场状态分段评估 |
| PUB-PB-1 | 发布 DQ 仅基础约束 | 缺分布漂移/覆盖率/连续性检查 |
| INVAL-IC-1 | repair_batch 首个失败即终止 | 应 try/continue |
| INVAL-IC-2 | 无死信队列 | 永久损坏数据无限重试 |
| INVAL-IC-3 | 无优先级队列 | 同深度无角色排序 |

### P2

| ID | 缺口 | 说明 |
|----|------|------|
| EVAL-EV-6 | periods_per_year 硬编码 244 | 不可配置 |
| EVAL-EV-7 | 无 Calmar Ratio | 年化收益/最大回撤 |
| EVAL-EV-8 | 无 Grinold-Kahn IR 形式化 | IR = IC × sqrt(breadth) |
| EVAL-EV-9 | 无 Performance Attribution | 逐期收益分解 |
| EVAL-EV-10 | 无 IC 动量监测 | IC 趋势下降预警 |
| INVAL-IC-4 | 无跨事件去重 | 并发 cascade 重复修复 |
| INVAL-IC-5 | 无分布式锁 | 多 worker 竞态 |

---

## 第五层：元数据 + 日历 + Universe + 研究数据集 + 配置

### P0

| ID | 缺口 | 说明 |
|----|------|------|
| META-MD-1 | delist_date 定义但从未写入 | 退市股票无法过滤 |
| META-UV-1 | CSI 300/500/1000 成分未采集 | 策略无标准指数可用 |

### P1

| ID | 缺口 | 说明 |
|----|------|------|
| META-MD-2 | is_st 无历史变更记录 | 回测无法 PIT 查询 ST 状态 |
| META-MD-3 | list_status 无 PIT 记录 | 停牌/退市历史不可查 |
| META-MD-4 | 无 IPO 日期过滤 | 无 min_list_days 参数 |
| META-CL-1 | 无半日交易标记 | 半天交易日收益率计算偏差 |
| META-CL-2 | Calendar 丰富字段未自动化 | prev_trade_date/is_month_end 等无代码填充 |
| META-IN-1 | 仅 SW L1/L2，缺 L3 | 行业中性化粒度不够 |
| META-IN-2 | 无 CSRC 行业分类 | 仅 SW 分类 |
| META-UV-2 | 无流动性过滤 | 无 min_avg_volume 过滤 |
| META-UV-3 | 无成分批量替换接口 | 调仓需逐条操作 |
| META-RS-1 | LateArrivalPolicy 未实现 | REQUIRE_REBUILD 无实际代码 |

### P2

| ID | 缺口 | 说明 |
|----|------|------|
| META-MD-5 | 无股票名称变更历史 | 报告无法显示历史名称 |
| META-MD-6 | 无 share class 区分 | A/B/H 股无标记 |
| META-MD-7 | board 字段自由文本 | 未枚举化 |
| META-CL-3 | 仅 SSE 日历 | 北交所未覆盖 |
| META-CL-4 | 无特殊交易日概念 | IPO 首日规则未联动 |
| META-IN-3 | PIT 重组分类部分覆盖 | entry_reason 可空 |
| META-IN-4 | 多级行业查询返回单条 | LIMIT 1 无法同时返回 L1+L2 |
| META-UV-4 | 无调仓日程跟踪 | 无官方调仓日期 |
| META-UV-5 | 无集合运算 | 无 intersection/union/subtract |
| META-RS-2 | 仅 Parquet 导出 | 无 CSV/Feather |
| CFG-1 | 无启动配置校验 | TOKEN 可为空 |
| CFG-2 | 无交易策略配置段 | 无默认 universe/cost/risk 配置 |
| CFG-3 | Settings 未聚合 | 无统一配置入口 |

---

## 实施路线建议

按能力层分批推进，每层内部按 P0→P1→P2 顺序：

```
Layer 1: 数据摄取 (P0×3 + P1×7)
  └─ 前置依赖：无，可立即开始

Layer 2: 因子表达式引擎 (P0×5 + P1×6)
  └─ 前置依赖：无，可与 Layer 1 并行

Layer 3: 物化 + 存储 + 查询 (P0×3 + P1×4)
  └─ 前置依赖：Layer 2 P0 完成（物化依赖编译正确性）

Layer 4: 评估 + 发布 + 失效传播 (P1×9)
  └─ 前置依赖：Layer 3 完成（评估需要可查询的因子数据）

Layer 5: 元数据 + 日历 + Universe + 研究数据集 (P0×2 + P1×8)
  └─ 前置依赖：Layer 1 完成（元数据依赖摄取层的 ST/status 数据）
```

**可并行的层**：Layer 1 + Layer 2 + Layer 5 可同时启动。
**有依赖的层**：Layer 3 → Layer 4 有前后依赖。

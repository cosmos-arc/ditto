# Ditto System Description

> Spec-grade YAML — 供 `/ditto-product-arch` 消费的结构化系统描述。
> 生成日期：2026-04-17 | 模式：--from-existing

```yaml
meta:
  name: Ditto
  version: discovery-v1
  generated: "2026-04-17"
  mode: from-existing
  zachman_coverage:
    what: entities, capabilities      # ENTITIES + CAPABILITIES
    how: capabilities                 # CAPABILITIES
    where: constraints, integrations  # CONSTRAINTS + INTEGRATIONS
    who: actors                       # ACTORS
    when: events                      # EVENTS + INTEGRATIONS
    why: events                       # EVENTS

# ──────────────────────────────────────
# WHAT: Domain Model
# ──────────────────────────────────────
entities:
  # 市场层
  - name: Instrument
    description: 可交易证券（股票、债券、ETF 等）
    layer: market
    attributes:
      - { name: code, type: string, required: true }
      - { name: name, type: string, required: true }
      - { name: price, type: decimal }
      - { name: sector, type: string }
      - { name: market_cap, type: decimal }
      - { name: ohlcv, type: object, nested: [open, high, low, close, volume] }
      - { name: halt_status, type: enum, values: [trading, halted, suspended, to_be_listed] }
      - { name: limit_up, type: decimal }
      - { name: limit_down, type: decimal }

  - name: Universe
    description: 命名股票池（指数成分、自选股、筛选结果）
    layer: market
    attributes:
      - { name: name, type: string, required: true }
      - { name: criteria, type: object, description: "筛选条件或指数代码" }
      - { name: instrument_count, type: integer }
      - { name: membership, type: array, items: string }

  - name: Regime
    description: 市场状态分类
    layer: market
    attributes:
      - { name: state, type: enum, values: [risk_on, risk_off, mixed] }
      - { name: confidence, type: decimal, range: [0, 1] }
      - { name: driving_factors, type: array, items: string }
      - { name: switch_history, type: array, items: object }

  # 研究层
  - name: Research
    description: 投研活动记录
    layer: research
    attributes:
      - { name: id, type: string, required: true }
      - { name: title, type: string }
      - { name: type, type: enum, values: [note, analysis, hypothesis, review] }
      - { name: content, type: text }
      - { name: linked_instruments, type: array, items: string }
      - { name: created_at, type: datetime }
      - { name: source, type: enum, values: [manual, ai_copilot, ai_agent] }

  - name: Factor
    description: 可解释的量化因子（有金融含义）
    layer: research
    attributes:
      - { name: name, type: string, required: true }
      - { name: family, type: string }
      - { name: ic, type: decimal }
      - { name: ir, type: decimal }
      - { name: decay, type: decimal }
      - { name: turnover, type: decimal }
      - { name: coverage, type: decimal }
      - { name: health_status, type: enum, values: [active, degrading, failed] }
      - { name: expression, type: text }

  - name: Feature
    description: 模型输入特征（可为黑盒 ML 特征，与 Factor 区分）
    layer: research
    attributes:
      - { name: name, type: string, required: true }
      - { name: source, type: enum, values: [factor_derived, raw, ml_generated, external] }
      - { name: importance, type: decimal }
      - { name: model_ref, type: string, description: "关联的 ML 模型" }
      - { name: is_interpretable, type: boolean }

  - name: Strategy
    description: 策略配置（因子组合 + 股票池 + 权重 + 风控规则）
    layer: research
    attributes:
      - { name: name, type: string, required: true }
      - { name: version, type: string }
      - { name: mode, type: enum, values: [form, code] }
      - { name: factor_config, type: array }
      - { name: universe_ref, type: string }
      - { name: weight_method, type: enum, values: [equal, ic_weighted, risk_budget, manual] }
      - { name: risk_rules, type: array }
      - { name: preprocessing_pipeline, type: array }

  - name: Experiment
    description: 因子/策略的 A/B 对照实验
    layer: research
    attributes:
      - { name: name, type: string, required: true }
      - { name: status, type: enum, values: [draft, running, completed, failed] }
      - { name: hypothesis, type: text }
      - { name: treatment_group, type: object }
      - { name: control_group, type: object }

  # 验证层
  - name: Backtest
    description: 策略历史回测执行记录
    layer: validation
    attributes:
      - { name: run_id, type: string, required: true }
      - { name: strategy_ref, type: string }
      - { name: interval, type: object }
      - { name: status, type: enum, values: [pending, running, completed, failed] }
      - { name: nav_series, type: array }
      - { name: sharpe, type: decimal }
      - { name: max_drawdown, type: decimal }
      - { name: turnover, type: decimal }
      - { name: fees, type: decimal }

  # 交易层
  - name: Signal
    description: 交易信号（策略/AI 生成，需人工复核）
    layer: trading
    attributes:
      - { name: id, type: string, required: true }
      - { name: timestamp, type: datetime }
      - { name: instrument, type: string }
      - { name: direction, type: enum, values: [buy, sell] }
      - { name: weight, type: decimal }
      - { name: confidence, type: decimal, range: [0, 1] }
      - { name: source, type: enum, values: [strategy, ai_agent, manual] }
      - { name: status, type: enum, values: [pending, approved, rejected, expired, executed] }

  - name: Order
    description: 已确认的交易指令
    layer: trading
    attributes:
      - { name: id, type: string, required: true }
      - { name: instrument, type: string }
      - { name: side, type: enum, values: [buy, sell] }
      - { name: quantity, type: integer }
      - { name: price, type: decimal }
      - { name: type, type: enum, values: [limit, market] }
      - { name: status, type: enum, values: [pending, submitted, partial_fill, completed, failed, cancelled] }
      - { name: fees, type: decimal }
      - { name: slippage, type: decimal }

  - name: Execution
    description: 订单执行记录
    layer: trading
    attributes:
      - { name: id, type: string }
      - { name: order_ref, type: string }
      - { name: filled_price, type: decimal }
      - { name: filled_quantity, type: integer }
      - { name: fill_time, type: datetime }
      - { name: market_impact, type: decimal }

  - name: Account
    description: 券商账户信息
    layer: trading
    attributes:
      - { name: broker, type: string, required: true }
      - { name: account_id, type: string }
      - { name: available_cash, type: decimal }
      - { name: total_assets, type: decimal }
      - { name: buying_power, type: decimal }
      - { name: connection_status, type: enum, values: [connected, disconnected, error] }

  # 风控层
  - name: Risk
    description: 风控规则与事件
    layer: risk
    attributes:
      - { name: id, type: string }
      - { name: type, type: enum, values: [rule, event, breach] }
      - { name: metric, type: enum, values: [var, max_drawdown, beta, concentration, exposure] }
      - { name: threshold, type: decimal }
      - { name: current_value, type: decimal }
      - { name: severity, type: enum, values: [normal, warning, critical] }
      - { name: triggered_at, type: datetime }

  - name: Portfolio
    description: 组合持仓
    layer: risk
    attributes:
      - { name: instruments, type: array, items: object }
      - { name: total_value, type: decimal }
      - { name: daily_pnl, type: decimal }
      - { name: gross_exposure, type: decimal }
      - { name: net_exposure, type: decimal }
      - { name: t1_frozen, type: array, description: "T+1 冻结持仓" }

  # AI 层
  - name: AgentPlan
    description: AI Agent 工作流计划
    layer: ai
    attributes:
      - { name: id, type: string, required: true }
      - { name: status, type: enum, values: [draft, running, paused, completed, failed] }
      - { name: linked_strategy, type: string }
      - { name: pipeline_steps, type: array }
      - { name: agent_roles, type: array, items: string }

  - name: AgentFinding
    description: AI Agent 产出的发现/结论
    layer: ai
    attributes:
      - { name: id, type: string, required: true }
      - { name: confidence, type: decimal, range: [0, 1] }
      - { name: evidence_chain, type: array }
      - { name: approval_status, type: enum, values: [pending, approved, rejected, expired] }
      - { name: linked_signal, type: string, description: "审批通过后自动生成的信号" }

  - name: Pipeline
    description: Agent 或数据处理流水线
    layer: ai
    attributes:
      - { name: name, type: string, required: true }
      - { name: steps, type: array }
      - { name: status, type: enum, values: [idle, running, completed, failed] }
      - { name: logs, type: array }
      - { name: artifacts, type: array }

# ──────────────────────────────────────
# HOW: Capabilities
# ──────────────────────────────────────
capabilities:
  - name: 市场观测与发现
    domain: market
    sub_capabilities:
      - { name: 跨市场扫描, actors: [human, ai_analyst] }
      - { name: 单市场结构扫描, actors: [human] }
      - { name: 多维筛选, actors: [human] }
      - { name: 事件日历, actors: [human, ai_analyst] }
      - { name: 市场情报聚合, actors: [ai_analyst, ai_news_analyst] }

  - name: 标的分析
    domain: instrument
    sub_capabilities:
      - { name: 深度 Hub（8 Tab）, actors: [human] }
      - { name: K 线技术指标, actors: [human, ai_technical_analyst] }
      - { name: 资金流向分析, actors: [human, ai_analyst] }
      - { name: 基本面分析, actors: [human, ai_fundamental_analyst] }

  - name: 因子研究与策略构建
    domain: research
    sub_capabilities:
      - { name: 因子健康监测, actors: [human, ai_agent] }
      - { name: 因子多维诊断, actors: [human] }
      - { name: 因子预处理流水线, actors: [human] }
      - { name: AI 因子发现, actors: [ai_agent] }
      - { name: 策略构建（Form/Code 双模式）, actors: [human, ai_agent] }
      - { name: 策略版本管理, actors: [human] }

  - name: 回测验证
    domain: validation
    sub_capabilities:
      - { name: 日线收盘价回测, actors: [human, ai_agent] }
      - { name: A 股规则模拟, actors: [system] }
      - { name: 前向验证 + 过拟合检测, actors: [human, ai_agent] }
      - { name: 回测对比（最多 5 组）, actors: [human] }

  - name: 交易执行与风控
    domain: trading
    sub_capabilities:
      - { name: 信号复核队列, actors: [human] }
      - { name: 下单确认单（预交易检查）, actors: [human] }
      - { name: 实时执行, actors: [system, broker] }
      - { name: 订单生命周期追踪, actors: [human] }
      - { name: 盘后归因分析, actors: [human, ai_agent] }
      - { name: 实时风控仪表盘, actors: [human, ai_risk_manager] }
      - { name: 压力测试, actors: [human] }

  - name: AI Agent 协同
    domain: ai
    sub_capabilities:
      - { name: Copilot Studio（市场/个股/策略/因子 4 模式）, actors: [human, ai_copilot] }
      - { name: Agent Console（Plan→Run→Finding→Approval）, actors: [human, ai_agent] }
      - { name: 多空辩论推理, actors: [ai_bull_researcher, ai_bear_researcher] }
      - { name: 自动化投研 Pipeline, actors: [ai_agent] }
      - { name: Confidence Framework, actors: [system] }

  - name: 平台运维
    domain: platform
    sub_capabilities:
      - { name: 数据源健康监控, actors: [human, system] }
      - { name: Pipeline/任务管理, actors: [human] }
      - { name: 系统告警, actors: [system] }
      - { name: 日志审计, actors: [human] }

# ──────────────────────────────────────
# WHO: Actors
# ──────────────────────────────────────
actors:
  - name: 全栈量化交易者（人类）
    type: human
    roles: [strategy_researcher, trade_executor, system_maintainer]
    description: 单一用户承担研/交/风/运全部角色，由 AI Agent 团队辅助
    permissions:
      - 所有读写操作
      - 最终决策权（信号审批、Agent Finding 审批）
      - 危险操作确认（暂停交易、全部撤单、停止 Agent）

  - name: AI 分析师团队
    type: agent
    hierarchy: analyst
    members:
      - { name: 基本面分析师, role: fundamental_analyst }
      - { name: 技术面分析师, role: technical_analyst }
      - { name: 情绪面分析师, role: sentiment_analyst }
      - { name: 新闻分析师, role: news_analyst }
    permissions:
      - 数据读取和分析
      - 生成分析报告
      - 无交易权限

  - name: AI 研究员团队
    type: agent
    hierarchy: researcher
    members:
      - { name: 多头研究员, role: bull_researcher }
      - { name: 空头研究员, role: bear_researcher }
    permissions:
      - 读取分析师报告
      - 多空辩论推理
      - 生成投资建议
      - 无交易权限

  - name: AI 交易员
    type: agent
    hierarchy: trader
    permissions:
      - 综合分析师+研究员报告
      - 生成交易提案
      - 无直接下单权限（需 PM 审批）

  - name: AI 风控经理
    type: agent
    hierarchy: risk
    permissions:
      - 评估波动率、流动性、集中度
      - 生成风控报告
      - 对交易提案标注风险等级

  - name: AI 组合经理
    type: agent
    hierarchy: pm
    permissions:
      - 最终审批/拒绝交易提案
      - 审批通过后自动生成 Signal
      - 无直接下单权限（Signal 需人类复核）

  - name: System
    type: system
    description: 自动化系统任务（数据刷新、stale 检测、告警触发）
    permissions:
      - 数据读取和写入
      - 自动化任务执行
      - 无决策权限

  - name: Broker (MiniQMT)
    type: external
    description: 券商交易通道
    permissions:
      - 接收订单指令
      - 返回成交报告
      - 提供实时行情

# ──────────────────────────────────────
# WHEN: Events
# ──────────────────────────────────────
events:
  - name: 回测执行
    trigger: 用户提交或 Agent 自动触发
    steps:
      - 策略配置读取
      - 历史数据加载（tushare/通达信）
      - 逐日模拟（A 股规则引擎）
      - 生成 NAV/持仓/交易序列
      - 计算绩效指标（Sharpe/MDD/Turnover）
    payload: { strategy_ref, interval, matching_model }
    effects: [backtest_created, performance_updated]

  - name: 信号生成
    trigger: 策略信号 / Agent Finding 审批通过
    steps:
      - 生成 Signal（source: strategy/ai_agent）
      - 写入 Signals Inbox（pending）
      - 更新 Home 待处理计数
    payload: { instrument, direction, weight, confidence, source }
    effects: [signal_pending, home_counter_updated]

  - name: 订单执行
    trigger: 人类复核通过信号
    steps:
      - 预交易检查（停牌/涨跌停/T+1 冻结/保证金/价格合理性）
      - 生成 Order
      - xtquant order_stock()
      - 接收成交报告
      - 更新持仓和 PnL
    payload: { instrument, side, quantity, price, type }
    effects: [order_submitted, position_updated, pnl_updated]

  - name: Agent Finding 审批
    trigger: Agent Plan 完成产出 Finding
    steps:
      - Finding 生成（含 Confidence + Evidence Chain）
      - 等待人类审批
      - 审批通过 → 自动生成 Signal
      - 审批拒绝 → 记录原因
    payload: { finding_id, confidence, evidence_chain }
    effects: [finding_approved_or_rejected, signal_created_if_approved]

  - name: 盘后归因
    trigger: A 股收盘（15:00）
    steps:
      - 自动切换 Review Mode
      - 每日 PnL 归因（行业/个股/因子贡献）
      - 持仓健康检查
      - 次日策略预览
    payload: { trading_date }
    effects: [daily_pnl_computed, next_day_preview_updated]

  - name: 数据刷新
    trigger: 定时调度 / 事件触发
    steps:
      - tushare: 日线 16:00
      - MiniQMT: 交易时段 3s WebSocket
      - FRED: 每日 UTC 00:00
      - 通达信: 按需交叉验证
    payload: { source, data_type }
    effects: [data_updated, stale_cleared]

# ──────────────────────────────────────
# WHERE: Integrations
# ──────────────────────────────────────
integrations:
  - name: tushare
    type: data_source
    protocol: REST API
    data_flow: outbound (Ditto → tushare)
    frequency: daily (T+1, ~16:00)
    rate_limit: 200 calls/min
    data_types: [ohlcv, adj_factor, limits, halts, financials, index, northbound, dragon_tiger, margin_trading, corporate_actions]
    fallback: 通达信本地缓存

  - name: MiniQMT (xtquant)
    type: data_source + execution
    protocol: WebSocket + Python SDK
    data_flow: bidirectional
    frequency: 3s tick (real-time)
    dependency: QMT 客户端保持登录
    data_types: [level1_realtime, order_execution, position_query, trade_query]
    critical: true

  - name: 通达信
    type: data_source
    protocol: local file / API
    data_flow: outbound (Ditto → 通达信)
    frequency: on-demand
    data_types: [minute_bars_1_5, daily_ohlcv_cross_check]
    fallback: tushare

  - name: FRED
    type: data_source
    protocol: REST API
    data_flow: outbound (Ditto → FRED)
    frequency: daily/monthly
    rate_limit: 120 calls/min
    data_types: [usd, rates, cpi, gold, oil]
    fallback: none

  - name: LLM Provider
    type: ai_service
    protocol: API (OpenAI-compatible)
    data_flow: bidirectional
    models: [Claude, GPT, DeepSeek]
    usage: [copilot_analysis, agent_reasoning, factor_discovery, sentiment_analysis]

# ──────────────────────────────────────
# CONSTRAINTS: Platform
# ──────────────────────────────────────
constraints:
  deployment:
    frontend: Cloudflare Pages (SPA, no SSR)
    backend: FastAPI (REST + WebSocket)
    database: TBD (需要评估)
    deployment_model: 内部量化平台，支持多用户

  performance:
    signal_to_order_latency: "<=100ms"
    exchange_fill_to_frontend: "<=2s"
    page_load_time: "<=3s"
    stale_threshold:
      real_time: ">10s"
      near_real_time: ">30min"
      daily: "scheduled + 2h"

  market_scope:
    primary: A 股（中国内地）
    secondary:
      - 大宗商品（期货/现货）
      - 贵金属（黄金/白银）
      - 外汇（主要货币对）
      - 国际主流指数（标普500/纳斯达克/恒生等）
    future:
      - 美股（全面支持）
      - 加密货币
    note: "多市场架构，当前以 A 股为核心，其他市场通过可插拔适配器逐步引入"

  a_stock_rules:
    settlement: T+1
    price_limit_main: "+-10%"
    price_limit_st: "+-5%"
    price_limit_gem_star: "+-20%"
    lot_size: 100 shares
    stamp_duty: "0.05% sell-only (since 2023-08-28)"
    commission: "0.025% both sides, min 5 CNY"

  data_architecture:
    pattern: pluggable_adapter
    current_adapters: [tushare, miniquant, tongdaxin, fred]
    extension: adapter_registry pattern
```

# Discovery 产出物格式模板

## assumptions.md 格式

```yaml
---
assumptions:
  - id: vision-realtime-data-needed
    statement: "用户需要实时行情数据"
    source: "Phase 1 Q3 用户回答"
    risk: high
    status: unvalidated
    evidence: []
    validationMethod: "Phase 2 竞品调研确认是否为行业标准"
    relatedEntities: [MarketData]
---

# Assumption Registry

## [vision-realtime-data-needed] 用户需要实时行情数据
- **来源**: Phase 1 Q3
- **风险**: 🔴 High
- **状态**: ⬜ 未验证
- **验证方法**: Phase 2 竞品调研确认是否为行业标准
- **关联实体**: MarketData (ENTITIES)
```

**风险评级标准**:

| 等级 | 条件 | Phase 5 行为 |
|------|------|-------------|
| 🔴 High | 错误则需架构重建或方向性调整 | 必须在 SYNTHESIS 前验证，否则警告 |
| 🟡 Medium | 错误则需功能重设计 | 建议验证，可在后续迭代中确认 |
| 🟢 Low | 错误则需微调 | 可在实现阶段确认 |

**假设生命周期**:
```
surfaced → registered → evidence-gathered → validated/invalidated
```

**假设 ID 命名规则**: `{phase}-{简短描述}`，如 `vision-realtime-data`、`landscape-competitor-wind`、`system-entity-relationship`。不使用自增编号。

---

## landscape.md 格式

在原有竞品叙述基础上追加三项分析框架：

```markdown
## Feature Matrix

| Feature | Ditto | Wind | TradingView | 同花顺 |
|---------|-------|------|-------------|--------|
| 实时行情 | ✅    | ✅✅  | ✅          | ✅     |
| 量化回测 | ✅✅  | ✅   | ❌          | ✅     |
| 现代UI   | ✅✅  | ❌   | ✅          | ⚠️     |

图例：✅✅=行业领先  ✅=具备  ⚠️=部分  ❌=不具备

## Positioning Quadrant

x-axis: 信息密度（低→高）
y-axis: 智能化程度（低→高）

- Ditto: [high, high]
- Wind: [high, low]
- TradingView: [medium, medium]

## Differentiation Statements

### [维度名称]
- **我们做**: {具体描述}
- **竞品做**: {竞品现状}
- **证据**: Phase 2 调研结果
```

---

## system-description.md Spec-grade YAML 格式

```yaml
---
schemaVersion: 1

entities:
  - name: Instrument
    type: aggregate-root       # aggregate-root | value-object | enum | event
    description: "金融标的物"
    attributes:
      - name: code
        type: string
        required: true
      - name: price
        type: decimal
        source: realtime-feed
    relationships:
      - target: MarketIndex
        type: belongs-to
    lifecycle: "长期存在，数据源驱动更新"

capabilities:
  - name: backtest
    type: core                  # core | supporting | ancillary
    description: "策略历史回测"
    primaryEntities: [Strategy, Instrument]
    actors: [quant-trader]
    steps:
      - "选择策略模板"
      - "配置参数和标的池"
      - "执行回测"
      - "查看结果报告"
    successCriteria: "生成 Sharpe/收益报告"

actors:
  - name: quant-trader
    type: primary               # primary | secondary | system
    description: "量化交易员"
    permissions:
      - "create-edit-delete:Strategy"
      - "execute:Backtest"

events:
  - name: backtest-completed
    type: domain                # domain | system | integration
    description: "策略回测完成"
    source: BacktestEngine
    payload:
      - field: strategyId
        type: string
      - field: resultSummary
        type: object
    effects:
      - "通知用户"
      - "更新策略状态"
    triggers: [backtest-submitted]

constraints:
  deployment: "本地/私有云"
  platforms: ["web-browser-desktop-first"]
  performance:
    firstLoad: "< 2s"

integrations:
  - name: market-data-feed
    direction: inbound          # inbound | outbound | bidirectional
    type: stream                # stream | batch | api | file
    protocol: WebSocket
    dataFlow: "External → Cache → UI"
    reliability: "断线重连 + 本地缓存回退"

priorities:
  - capability: backtest
    impact: high                # high | low
    feasibility: medium         # high | low
    quadrant: must-have         # quick-win | must-have | nice-to-have | defer
    mvpRequired: true
---

# System Description

## Entities
（Markdown 叙述补充）

## Capabilities
（Markdown 叙述补充）
```

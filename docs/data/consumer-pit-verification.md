# 消费者 PIT 语义与限制传播报告（#628 / 父规格 #621 P4）

交付时间：2026-11-02。覆盖 P4 四项范围：latest/as-of/冻结快照语义声明、
日期精度保守可见、财务修订与冻结重放分别验收、覆盖限制经 API/图表/导出保留。

## 能力交付（CODE）

### 1. PIT 修订收敛（读取器根因层，全部消费端一次修复）

`ditto_data.storage.base.sqlite_table_reader.SqliteTableReader._finalize`：

- **PIT 查询**（`get` / `get_range(as_of_date=…)`）下，同事实键
  （`fact_key_columns`，缺省 `(id_column, date_column)`）多条可见版本
  （披露锚不同的修订公告、双开区间行）收敛到 **knowledge 最新**（并列取
  `effective_from` 更晚）的一条；输出按 (排序键, 版本轴) 倒序**确定性排序**。
- **非 PIT 读取不收敛**：`corporate_actions` 无 as_of 路径的版本史契约
  （`test_no_as_of_date_returns_all_versions`）原样保留。
- `corporate_actions` 事实键 = `(instrument_id, action_date, action_type)`：
  同日不同行动类型是不同事实，不因修订收敛误删。
- 回测截面 `fundamental_snapshot._first_float` 取行不确定的隐患随根因消除。

修复前的真实缺陷（探索实证）：三表修订多版本经 `effective_to=NULL` 双开区间
原样漏出到 API/回测；SQLite PK `(instrument_id, report_date, effective_from)`
允许修订行共存，读取层无收敛规则。

### 2. 覆盖限制运行时真源（#622 合同的消费接通）

- `ditto_data.coverage.limits`：47 项数据集蒸馏（status/measured_start/
  measured_end/gaps/notes + `COVERAGE_MEASURED_AT=2026-10-30`）。应用运行时
  **不读取** `docs/`；守卫测试 `test_limits_sync_unit` 从 YAML 重新蒸馏比对，
  YAML 刷新未同步即响亮失败并列出差异条目。
- `DatasetCoverageQueryFacade`（application）+ `GET /datasets/coverage`
  （backend，新 operationId `datasets_list_coverage`）：限制经 API 可得，
  空数据与不覆盖可区分。

### 3. API 语义标注与时间轴分离

- `ReadSemantics` 词汇表（models/common.py）：`latest_available`（现存行，
  无 PIT 过滤——受限研究，不得包装为严格 PIT）/ `pit_asof`（as_of 可见版本，
  日粒度 as_of=上海日终）/ `frozen_snapshot`（快照重放，逐字段稳定）。
- `/market/etf-nav` 响应携带 `read_semantics` + `data_coverage`（图表链的
  限制传播入口）；`/market/bars`、`/market/indicator-series`、`/macro/*`、
  `/fx/*`、`/commodity/*` docstring 声明 `latest_available` 语义与覆盖查询路径。
- 财务族响应行级透出 `knowledge_date/effective_from/effective_to`
  （事实/公告/版本轴分离）；`corporate-actions` 语义随 as_of 有无切换
  （pit_asof ↔ latest_available），docstring 声明。

### 4. 财务链路静默丢失修复（两个生产级 bug）

- `/fundamental/financials/*`：`to_financial` 旧映射读取器从不产出的
  `data` 列 → 生产响应 `data` 恒空字典。修复：`data` 字典由读取器平铺
  业务列聚合（身份/事实日/版本轴列排除），兼容合成 `data` 列输入。
- `/fundamental/dividend`：旧映射读 `amount`/`announce_date`/`dividend_type`
  → 生产响应 `amount` 恒 0.0（缺必需输入被零填充，P4 明令禁止的形态）。
  修复：按存储真实列（`ex_dividend_date/div_proc/dividend_per_share/
  dividend_yield`）映射，未披露数值以 null 透出。oasdiff 3 条
  `response-required-property-removed` 属 #390 已批准破坏窗口
  （伪映射字段、零 web 消费者、项目未发布），失败清单引用于 PR 描述。

### 5. 缺必需输入拒绝而非填零

`resolve_identifier_or_404`（api/utils/identifier.py）：标识符解析失败
404 `NOT_FOUND`（fundamental financials/dividend/corporate-actions、
capital margin/valuation），不再 200 空列表与「无数据」不可区分。

## 验收（#621 P4 条款逐项）

| 条款 | 证据 |
| --- | --- |
| 未来哨兵 + 截止内阳性对照 | `TestVersionDeduplicationRealSqlite.test_future_sentinel_and_positive_control`（真实 SQLite，pit 标记）：as_of=2024-04-24 空、as_of=2024-04-25（knowledge 当日=日终语义）可见 |
| 晚到修订 | `test_late_revision_frozen_before_and_current_after`：修订落库后旧 as_of 读数逐字段 `equals` 冻结值；新 as_of 见修订值与修订 knowledge_date |
| 旧快照逐字段稳定 | 同上 + reader 输出确定性排序（`test_output_order_stays_date_desc_across_reports`）；provider snapshot 内容寻址重放通路既有（§2.3 pit-time-semantics） |
| 半开区间边界 | `test_effective_to_closing_day_half_open_boundary`：effective_to 当日版本关闭、旧版本重新可见 |
| 缺必需输入拒绝而非填零 | `test_unresolved_identifier_returns_404_not_empty` + `test_missing_values_stay_null_not_zero`（dividend null 不零填充） |
| 限制经 API 保留 | `GET /datasets/coverage` 47 项（`test_datasets_router_unit`：etf_nav partial/末端 10-26、fx_daily empty+gaps、measured_at=2026-10-30） |
| 限制经图表保留 | etf-nav 降级文案带覆盖窗口（web `instrument-components.test`：`库内至 2026-10-26`），title 携带 status/gaps/测量时点 |
| 限制经导出保留 | 图表 CSV/PNG 导出既有身份列（as_of/snapshot/cutoffs/missing_sessions）不变；NAV 叠加线设计上不入 CSV（「CSV 仅含 K 线」契约），其限制经响应与 UI 传播——#193/#208 导出设计若纳入 NAV 序列则接 data_coverage |

## 边界与留档

- **两套日线发布时刻规则维持现状**：选池 18:00（同日知识行）/ 图表 T+1
  15:00（daily 数据集 knowledge 时点）。两者对「T 18:00 发布声明」均为
  保守（不前视），严格度差异留档不统一——阈值变更会改写 input_hash/图表
  身份，须独立票裁决。
- **日粒度 as_of = 上海日终**语义固化：date 精度知识（披露锚）当日全天
  不视为部分可见，`knowledge_date <= as_of_date` 即保守正确；datetime
  精度消费（选池/图表/paper）已有各自时刻规则，不新增第五套。
- **观察锚数据集**（index_weight #452）：可知性=观察日，不宣称公告可知；
  IndexCompositionReader docstring 既有声明，coverage 真源 notes 重复标注。
- fina_indicator/fund_portfolio/top10 双榜/hk_hold/limit_list/index_valuation/
  cyq_perf/pledge_ratio 无读取消费者，不新建无消费者读取通路（YAGNI）；
  覆盖真源已含其限制，消费者出现时经 `/datasets/coverage` 接入。
- **非 PIT 读取的版本史语义**：corporate_actions 无 as_of 返回全部版本
  （含被取代版本），行级版本轴可区分；该契约由既有测试锁定，本票未改变。

## 复测入口

```bash
# 读取器修订收敛/边界（真实 SQLite）
cd packages/data && pytest tests/unit/storage/base/test_sqlite_table_reader.py -q
# 覆盖真源同步守卫
cd packages/data && pytest tests/unit/coverage -q
# 端点语义/404/版本轴
cd apps/backend && pytest tests/integration/api/test_datasets_router_unit.py \
  tests/integration/api/test_fundamental_router_unit.py -q
# 契约（v1.json canonical + redocly + oasdiff + generated 零漂移）
task check-contract
```

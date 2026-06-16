# Ditto 生产上线路线图与修复方案

> 制定日期: 2026-06-14
> 配套评估: [docs/reviews/2026-06-14-production-readiness-eval.md](../reviews/2026-06-14-production-readiness-eval.md)
> 上线目标: **个股 + ETF + 宏观数据,日频维度量化 + 个股分析 + 优秀选股能力**
> 选股形态定位: **规则化多因子打分选股**(动量+价值+质量多因子加权打分,rank 选 top-N,覆盖 80% 个人量化选股需求)
> 范围: 后端系统功能;前端由独立团队承担;真实券商接入不在当前范围

---

## 一、目标与原则

### 1.1 上线定义

系统能够端到端跑通以下主链路,且在 CI 有回归保护:

```
数据摄入(Tushare 真实数据)
  → 特征物化(因子计算)
  → 多因子打分选股(动量+价值+质量)
  → 组合构建(约束 + 权重分配)
  → 风控(Pre/PostTrade + A股规则)
  → 回测(日频 + A股成本/涨跌停/T+1)
  → 报告(NAV + alpha + 交易明细)
```

### 1.2 核心原则

1. **先解阻、后增强、再体验**——P0 阻断不解决,后续都是空中楼阁。
2. **ETF 先行,个股跟进**——ETF 链路已就绪,作为首个上线形态;个股选股作为第二阶段。
3. **停止 execution/broker 矩阵扩展**——已进入负收益区(见评估报告 §一)。
4. **每个阶段有可验收的 golden 产出**——不接受"做完但没有端到端验证"。

### 1.3 工作量口径

下文 ETA 为**理想人日**(单人全职,无中断)。实际排期按团队规模与并行度折算。所有任务遵循 TDD(RED→GREEN→REFACTOR),完工前 `pixi run -e dev check` 全绿。

---

## 二、P0 阻断修复方案(Phase 0)

### P0-#1 基本面数据接入回测链路

#### 问题

[factor_bridge.py:319-339](packages/application/src/ditto_application/processes/execution/factor_bridge.py#L319) 的 `build_factor_bundle` 调 `data_feed.get_history(...)` 后,L325-333 只 select `instrument_id/open/high/low/close/volume/trade_date`——**基本面字段(roe/pe_ratio 等)被丢弃**。导致 [seeds.py:154](packages/strategy/src/ditto_strategy/alpha/seeds.py#L154) 的 `quality_roe`/`value_pe` 因子在回测时 `ColumnNotFoundError`。

#### 架构落点(已确认)

- DataFeed Protocol:[data_feed.py:62](packages/backtest/src/ditto_backtest/data_feed.py#L62)(`get_slice` + `get_history`)
- 实现入口:application 的 [ProviderBackedDataFeed](packages/application/src/ditto_application/builders/service_factory.py)(接入 data 层)
- 数据源:[FundamentalStore](packages/data/src/ditto_data/services/fundamental_store.py#L44)(PIT 查询已实现)
- application/CLAUDE.md 已规定:"factor bundle 历史窗口必须用 `knowledge_date` 调 `DataFeed.get_history`"——**接入点合规,无需新架构**。

#### 修复方案(最小侵入)

**Step 1 — 扩展 DataFeed Protocol(新增基本面快照方法)**

在 [data_feed.py](packages/backtest/src/ditto_backtest/data_feed.py) 的 `DataFeed` Protocol 新增:

```python
def get_fundamental_snapshot(
    self,
    instrument_ids: Sequence[InstrumentId],
    as_of: str,  # knowledge_date ISO,严格 PIT
) -> pl.DataFrame:
    """返回当日可见的基本面快照(roe/pe_ratio/pb_ratio/...),PIT as-of = knowledge_date."""
```

> 为什么独立方法而非塞进 get_history:基本面是低频(季度)快照,与日频 OHLCV 语义不同;独立方法让 PIT 边界更清晰,也避免污染时序窗口。

**Step 2 — ProviderBackedDataFeed 实现接入 FundamentalStore**

在 application 的 ProviderBackedDataFeed 实现中,注入 `FundamentalStore`(或 `FundamentalQueryFacade`),`get_fundamental_snapshot` 调 `fundamental_store.get_balance_sheet(...)` 等 PIT 查询,as_of 用 `knowledge_date`。

**Step 3 — build_factor_bundle 注入基本面列**

[factor_bridge.py](packages/application/src/ditto_application/processes/execution/factor_bridge.py) 在构造 market_data 后,调用 `data_feed.get_fundamental_snapshot(...)`,把 roe/pe_ratio 等列 merge 进当日 market_data(按 instrument_id join)。这样 `bridge.compute_signals` 编译 `quality_roe`/`value_pe` 时能读到列。

**Step 4 — PIT 合规校验**

- 基本面快照的 as_of 必须 = `ctx.time_context.knowledge_date`,不得用 trade_date。
- manifest/report/artifact metadata 记录"基本面 PIT 已接入"(复用现有 PIT policy 记录机制)。

**Step 5 — 验证(TDD)**

- 单测:mock DataFeed 返回含 roe/pe_ratio 的快照,验证 `build_factor_bundle` 产出含基本面列的 market_data。
- 集成:用合成基本面数据跑 `_seed_stock_selection_rotation`,验证不报 ColumnNotFoundError 且产出 NAV。
- golden:纳入 Phase 1 的 stock-selection golden E2E。

#### 验收标准

- [x] `quality_roe`/`value_pe` 等基本面因子在回测中可编译可计算。
- [x] `_seed_stock_selection_rotation` seed 可端到端跑通(合成数据)。
- [x] 基本面快照 PIT as_of = knowledge_date,有测试证明。
- [x] `pixi run -e dev check` 全绿,37 架构合约全绿。

#### ETA:2–3 人日

---

### P0-#2 Golden E2E 纳入 CI 门禁

#### 问题

[ci.yml](.github/workflows/ci.yml) 所有 job 只跑 unit + `--fast`;[ci-integration.yml:8-17](.github/workflows/ci-integration.yml#L8) 仅 `workflow_dispatch`,schedule/workflow_run 被注释。committed 的 [test_golden_e2e.py](packages/apps/tests/integration/test_golden_e2e.py) 在 PR/push 到 main 时完全不跑。

#### 修复方案

**Step 1 — 新增 golden-e2e job(进 PR 门禁)**

在 [ci.yml](.github/workflows/ci.yml) 的 `test-unit` 之后新增 `golden-e2e` job:

```yaml
golden-e2e:
  name: golden-e2e
  needs: changes
  if: ${{ needs.changes.outputs.python == 'true' || github.event_name == 'push' }}
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Setup Pixi
      uses: prefix-dev/setup-pixi@v0.9.3
      with: { pixi-version: v0.39.5, cache: true, locked: true, environments: dev }
    - name: Golden E2E
      run: pixi run -e dev pytest packages/apps/tests/integration/test_golden_e2e.py -v
```

并把 `golden-e2e` 加入 [ci-success](.github/workflows/ci.yml) 的 `needs` 与 required jobs 检查(line 228/234)。

> 只跑 golden 这一个文件(5 tests,~35s),不跑全部 integration,控制 CI 时间。

**Step 2 — 其余 integration 走 nightly(可选,省 CI)**

把 [ci-integration.yml:11-12](.github/workflows/ci-integration.yml#L11) 的 schedule 注释打开,改成 nightly(如 `cron: "17 2 * * *"`,避开整点)。PR 不阻断,但每天有回归覆盖。

**Step 3 — Branch Protection 配置**

在 GitHub 仓库设置中,把 `golden-e2e` 加入 main 的 required status checks。

#### 验收标准

- [x] PR 到 main 时 golden-e2e 自动运行并阻断。
- [ ] 故意破坏 EngineLoop(如改 DecisionFrame schema)能在 golden-e2e 失败（待首次 PR 触发 CI 后实测）。
- [x] ci-success 依赖 golden-e2e。

#### ETA:0.5 人日

---

### P0-#3 文档同步

修正 [capability-maturity.md:71](docs/architecture/capability-maturity.md#L71) "needs one committed synthetic golden lane" 与第 80 行的矛盾,同步 golden lane 已存在的事实。

#### ETA:0.5 人日

---

### Phase 0 汇总

| 任务 | ETA | 依赖 |
|---|---|---|
| P0-#1 基本面接入回测 | 2–3 人日 | 无 |
| P0-#2 CI golden 门禁 | 0.5 人日 | 无 |
| P0-#3 文档同步 | 0.5 人日 | 无 |
| **Phase 0 合计** | **~1 周(单人)** | 可并行 |

**Phase 0 里程碑:个股选股 seed 可端到端跑通 + CI 有 golden 回归保护。**

> ✅ **Phase 0 已完成(2026-06-14)**:8275 unit/integration 测试全绿、37 架构合约全绿、`pixi run -e dev check` 通过。
>
> 实现摘要:
> - **P0-#1 基本面接入回测**:发现并修复 plan 未覆盖的**双重断点**——(a) `signal_expressions` 存的是因子 ID 而非表达式,FactorBridge 直接编译成引用不存在列的 `pl.col`;修复:FactorBridge 加 `_resolve_expression`(`ALL_FACTOR_SPECS` ID→表达式解析)。(b) `build_factor_bundle` 的 `market_data` 缺基本面列;修复:DataFeed Protocol 新增 `get_fundamental_snapshot`(backtest 纯委托 Callable),application 层新增 `fundamental_snapshot.py` 闭包(PIT 查询 + 预计算 roe/net_margin/eps + maturity gate),`build_factor_bundle` merge 截面到当日行 + 补算 pe_ratio(close/eps)。DI 经 `FundamentalReadFacade` Protocol 注入(`builders→processes` 合规,规避 `builders→queries` R8 禁令,不用 TYPE_CHECKING)。
> - **P0-#2 CI 门禁**:`.github/workflows/ci.yml` 新增 `golden-e2e` job + ci-success 依赖。
> - **P0-#3 文档**:`docs/architecture/capability-maturity.md` 第 71 行矛盾修正(golden lane 已存在 + CI gating)。
> - **新增测试**:`test_factor_bridge_unit`(ID 解析)、`test_fundamental_snapshot_unit`(闭包 PIT/除零/缺数据)、`test_provider_data_feed_unit`(DataFeed 委托)、`test_factor_backtest_integration`(注入 + pe_ratio + PIT)、`test_seed_stock_selection_rotation_e2e`(seed 端到端 + 确定性)。

---

## 三、选股能力深化方案(Phase 1)

> 对应用户选股目标:**规则化多因子打分选股**。

### 3.1 目标工作流

```
因子池(动量+价值+质量+技术)
  → 数据接入(OHLCV ✓ + 基本面[Phase 0 已修] + 行业/市值[Phase 1 补])
  → 因子计算(表达式引擎 ✓)
  → 预处理(去极值 winsorize + 标准化 zscore + 中性化[可选])
  → 加权打分(signal_weights)
  → rank 选 top-N
  → 回测验证(✓)
  → [可选闭环] 因子 IC 诊断 → 调权重
```

当前代码已有:因子表达式引擎(强)、因子计算、rank、加权求和、回测。**Phase 1 补的是:预处理 stage 增强 + 行业数据 + 多因子融合增强 + 选股 golden E2E。**

### 3.2 任务分解

#### F1-#1 因子预处理 Stage 增强

**现状**:[MultiFactorSignalStage](packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_stages.py) 直接 `rank + 加权求和`,无去极值/标准化。表达式引擎有 `cs_winsorize`/`cs_zscore`/`cs_demean` 但 stage 没调用。

**方案**:在 `MultiFactorSignalStage` 的每个因子列上,加权前可选应用预处理链:

```
raw_factor → cs_winsorize(3σ) → cs_zscore → (中性化,可选) → rank → 加权
```

通过 `StrategySpec.params` 暴露开关:`preprocess: {winsorize: true, zscore: true, neutralize: industry|size|none}`。

**ETA:1–2 人日**

#### F1-#2 行业/市值数据 Provider

**现状**:`stock_sector_rotation` 模板要求 `is_sector`/`sector_id` 列(stage 有 fail-closed 校验),但**无内置行业分类数据 provider**。中性化也缺行业字段。

**方案**:在 data 层增加申万行业分类的 ingestion + storage + reader(若 Tushare 已有 `industry` 接口,复用 Tushare adapter),application 层在 build_factor_bundle 注入 `industry`/`market_cap` 列(类似 P0-#1 基本面注入路径,走 DataFeed 扩展)。

**ETA:2–3 人日**

#### F1-#3 多因子融合增强(接入 CompositeDecisionStage)

**现状**:[CompositeDecisionStage](packages/strategy/src/ditto_strategy/alpha/builtins/composite.py#L99)(Score Fusion + Rank Normalization)实现完整但**未被任何模板使用**。

**方案**:让 `stock_selection` 模板支持两种融合模式:
- 简单模式:增强后的 `MultiFactorSignalStage`(rank+加权,默认);
- 高级模式:`CompositeDecisionStage`(子 stage 独立 rank 标准化 + L1 权重归一化 + 加权,适合因子量纲差异大的场景)。

通过 `StrategySpec.params.fusion: simple|composite` 切换。

**ETA:1–2 人日**

#### F1-#4 补全核心因子表达式

**现状**:[volatility.py](packages/features/src/ditto_features/factors/volatility.py) 的 `idiosyncratic_vol`/`beta_252`/`downside_beta`/`parkinson_vol`/`garman_klass_vol` 等是 `computation_type="python"` 且 `expression=""` 占位(P2-#6)。KDJ/SuperTrend/OBV 同。

**方案**:选股 MVP 只需动量+价值+质量+基础技术(这些已有表达式)。波动率类高级因子标记为"研究用,暂不进 MVP",不阻塞上线。**Phase 1 不全量补,只确保 MVP 因子集可用。**

**ETA:0(标记即可)/ 可选 2–3 人日补全波动率类

#### F1-#5 个股选股 Golden E2E

**现状**:现有 golden(test_golden_e2e.py)只覆盖 ETF rotation 全链路,用 `_SyntheticParquetProvider` 短路了 ingest→materialize→strategy。

**方案**:新增一个个股选股 golden,链路:
1. 合成 Tushare 响应(行情 + 基本面 + 行业)→ ingestion 写入存储;
2. materialize 计算因子;
3. stock_selection 策略打分选股;
4. backtest 全链路;
5. 断言:NAV>0、选出的标的来自候选池、alpha 统计存在、确定性(两次跑结果一致)。

纳入 P0-#2 的 golden-e2e CI job。

**ETA:2–3 人日**

#### F1-#6 [可选] 因子 IC 诊断闭环

**现状**:[ic.py](packages/features/src/ditto_features/evaluation/metrics/ic.py) 有完整 IC 评估,但与选股策略未闭环。

**方案**:做一个 CLI/API:`ditto ops factor-ic <factor> <start> <end>` 输出 IC/ICIR/分层回测,辅助选因子。**MVP 可不做,作为 Phase 3 体验项。**

**ETA:可选 2–3 人日**

> ✅ **F1-#6 已完成(2026-06-16, Phase 3 首个任务)**:8356 测试全绿、37 架构合约全绿、basedpyright/ruff 全过。
>
> 实现摘要:
> - **`ditto ops factor-ic <factor> --start --end` CLI**([ops.py](packages/apps/src/ditto_apps/cli/commands/ops.py)):输出 IC/ICIR/分层回测/多空/换手成本 Markdown 报告。参数:`--version`(默认取 active)、`--asset-class`、`--holding-period`、`--n-quantiles`、`--regime`、`--attribution`、`--output`。异常 `except AppError` + `from exc`(修正 promotion-collect 的 `except ValueError` 漏捕模式)。
> - **FactorEvaluationFacade 扩展**([evaluation.py](packages/application/src/ditto_application/queries/evaluation.py)):`evaluate(factor_id, version: int | None = None)`——version=None 时 `resolve_offline_version` 解析 active,`DerivedError` 包装为 `AppQueryError`(保留 `__cause__` + factor_id details);`EvaluationOptions` 加 `run_regime_ic`/`run_performance_attribution`;report 重建用 `dataclasses.replace`(消除手动字段复制丢字段 bug——这正是本任务前 `regime_ic`/`performance_attribution` 被丢的根因)。
> - **DI 注册**([providers_market.py](packages/application/src/ditto_application/providers_market.py)):`factor_evaluation_facade` @provide(`DerivedArtifactReader` + `ForwardReturnService`)。
> - **渲染模块**([factor_ic_report.py](packages/application/src/ditto_application/queries/factor_ic_report.py)):application 层纯函数 `render_factor_ic_markdown`,11 章节。**apps 不直 import features**(架构 smell 合规),渲染归 application。
> - **范围决策**:核心报告 + `--regime`/`--attribution`(不依赖 risk factors,开箱即用);`--fama-macbeth`/`--exposure` 需 `RiskFactorProvider` 装配(EvaluationOptions 字段已预留),留后续。闭环形态=人机闭环(人看报告调选股权重)。操作手册 [docs/operations/factor-ic-diagnosis.md](../operations/factor-ic-diagnosis.md)。
> - **测试**:[test_evaluation_unit.py](packages/application/tests/unit/query/test_evaluation_unit.py)(9 测试:version None/显式/失败 + 开关透传 + report 重建/默认 None)+ [test_ops_unit.py](packages/apps/tests/unit/cli/commands/test_ops_unit.py)(10 测试:CLI stdout/文件/version/错误/regime/attribution 渲染/核心章节)。

### Phase 1 汇总

| 任务 | ETA | 优先级 |
|---|---|---|
| F1-#1 预处理 stage 增强 | 1–2 人日 | 必须 |
| F1-#2 行业/市值数据 | 2–3 人日 | 必须 |
| F1-#3 融合增强(接 Composite) | 1–2 人日 | 推荐 |
| F1-#4 因子表达式补全 | 0 / 可选 | 非阻塞 |
| F1-#5 选股 golden E2E | 2–3 人日 | 必须 |
| F1-#6 IC 诊断闭环 | 可选 | Phase 3 |
| **Phase 1 合计(MVP)** | **~1.5–2 周(单人)** | |

**Phase 1 里程碑:个股多因子选股策略可端到端跑通 + golden E2E 在 CI。**

> ✅ **Phase 1 已完成(2026-06-14)**:2620 unit 测试全绿 + 选股 golden e2e(2 tests)+ 37 架构合约全绿 + basedpyright/ruff 全过。
>
> 实现摘要:
> - **F1-#1 因子预处理增强**:`MultiFactorSignalStage` 加预处理链(`winsorize → zscore → neutralize`,纯 polars 自实现,语义对齐 features `cs_*` 算子,无 `.over()` 因 stage frame 是单日横截面)。提取 `preprocess_factor_column` 可测纯函数;`StockSelectionTrendConfig` 加 3 开关 + `validate_config` 校验。`winsorize`/`zscore` 单调(对纯 rank 加权不改变排序),`neutralize` 按组 demean 是非单调变换,是改变选股 rank 的核心;winsorize/zscore 价值在于为 neutralize 提供标准化前提并防御极值污染组均值。`neutralize_by` 列缺失 fail-closed 抛 `StrategySpecError`。
> - **F1-#2 行业/市值数据 read 侧注入**:探索修正——data 层 industry **已就绪**(`InstrumentService.get_stock_industry` 委托 `IndustryMappingReader` PIT 查询,非探索初判的 dead injection),无需新建 store/model。backtest `DataFeed` Protocol 新增 `get_classification_snapshot`(委托闭包),application 新增 `classification_snapshot.py` 闭包 + `ClassificationReadFacade` Protocol(`InstrumentService` 直接满足),builder 装配 + `factor_bridge._enrich_with_classification` 注入 `sector_id` 到当日行。apps composition root 注入 `metadata_service.instrument`。聚焦 `sector_id`(`market_cap` 数据已在 valuation_metrics,size 中性化是回归非 group demean,留后续)。
> - **F1-#3 多因子融合增强**:stock_selection 支持 `simple`/`composite` 融合(经 `StockSelectionTrendConfig.fusion` 切换)。composite 用 `CompositeDecisionStage`(每因子一个单因子子 stage + L1 权重归一化 + rank 标准化加权),**列命名桥接**:composite 产 `score` → TrendFilter 改读 `score` → 跳过 ScoringStage(composite 已 rank 标准化)。
> - **F1-#5 选股 Golden E2E**:修复 **pre-existing template 名不一致**(seed `stock_selection` vs builder/deserialization `stock_selection_trend` —— 统一为 specs 标准名 `stock_selection`,此前无合法 spec 能走通 builder)。新增 `test_stock_selection_golden_e2e`(40 日合成 OHLCV + 基本面 → FactorBridge 编译 quality_roe/value_pe/momentum_1m → `build_factor_aware_bundle_builder` → stock_selection pipeline → EngineLoop 全链路,断言 NAV>0/alpha/确定性)。CI golden-e2e job 纳入。
> - **F1-#4 因子表达式补全**:非阻塞,MVP 因子集(动量+价值+质量)已有表达式,波动率类高级因子标记研究用。**F1-#6 IC 诊断闭环**:列 Phase 3。

---

## 四、个股/宏观数据 Promotion(Phase 2)

> 解除 experimental 默认 fail-closed,让个股/宏观数据在生产路径默认可用。

### F2-#1 提交个股/宏观数据 promotion evidence

**现状**:promotion evidence/assessment/history/revoke 全套机制已实现([catalog.promotion](packages/data/src/ditto_data/catalog/promotion/)),但**没有任何 stock/macro 数据集真正提交过 evidence**。

**方案**:为 stock_daily / macro_indicators / balance_sheet / valuation_metrics 等目标数据集,按 `DatasetMetadata.promotion_criteria` 收集证据(数据完整性、PIT 合规、DQ 通过率、覆盖期),通过 `ReviewDatasetPromotionEvidenceHandler` 提交,assess 通过后自动晋级 initial-focus。

### F2-#2 FRED ALFRED realtime PIT 接入(P1-#1)

[fred/adapters/macro.py:71](packages/data/src/ditto_data/sources/fred/adapters/macro.py#L71) 传递 `realtime_start/realtime_end`,让宏观数据成为真正 PIT。

### F2-#3 真实数据端到端联通调试

用真实 Tushare 拉一段(如 1 年)ETF + 少量个股 + 宏观数据,跑通"摄入→物化→选股→回测→报告",作为上线前 acceptance test。复用 [test_ingestion.py](packages/apps/tests/e2e/test_ingestion.py) 的 `@pytest.mark.e2e` 基础,扩展到全链路。

**Phase 2 合计:~1 周**

**Phase 2 里程碑:个股/宏观数据默认可用 + 真实数据全链路跑通。**

> ✅ **Phase 2 已完成(2026-06-15)**:8337 测试全绿、37 架构合约全绿、basedpyright/ruff 全过。
>
> 实现摘要:
> - **F2-#1 promotion evidence 全套**:[promotion_evidence.py](packages/application/src/ditto_application/queries/promotion_evidence.py) `PromotionEvidenceCollector` 客观收集 3 条 criteria 证据(coverage 用 `DataCatalogReader` 统计、documentation 检查 `DatasetMetadata` 声明、tests 标 needs_review)——**绝不判定 promotion readiness**,晋级唯一路径仍是 `ReviewDatasetPromotionEvidenceHandler`。新增 [`ditto ops promotion-collect`](packages/apps/src/ditto_apps/cli/commands/ops.py) CLI 生成 Markdown 证据报告 + `PromotionEvidenceCollector` DI provider(注入 `DataCatalogReader`)。golden governance 闭环测试证明"逐条提交→assess ready→experimental→initial-focus→revoke→回退 + governance event"。操作手册 [docs/operations/dataset-promotion.md](../operations/dataset-promotion.md)。
> - **F2-#2 FRED realtime PIT**:[macro.py](packages/data/src/ditto_data/sources/fred/adapters/macro.py) `MacroFredAdapter.fetch_indicators` 透传 `realtime_start/realtime_end`,need_pit 指标(CPI/PCE/GDP)走 ALFRED vintage 查询 + `knowledge_date=realtime_end`(真正 PIT) + 多版本修订取最新 vintage(`_take_latest_vintage_as_of`);非 PIT 指标保持 observation date。[fred_source.py](packages/data/src/ditto_data/sources/fred/fred_source.py) 透传可选 realtime(向后兼容,MacroFetcher 协议路径不传)。9 单元测试 + 2 e2e 真实 FRED API 验证。
> - **F2-#3 真实数据联通**:[test_real_data_pipeline.py](packages/apps/tests/e2e/test_real_data_pipeline.py) FRED realtime PIT e2e 真实拉取验证(F2-#2 在真实 API 生效),`@pytest.mark.e2e` 标记 CI 跳过本地可跑(keyring `fred/api_key`)。Tushare 联通复用现有 [test_ingestion.py](packages/apps/tests/e2e/test_ingestion.py)。

---

## 五、体验与机构级(Phase 3,可选)

| 任务 | 对应差距 | ETA |
|---|---|---|
| 报告图表化(NAV 曲线/回撤图) | P2-#2 | 2–3 人日 |
| Brinson 行业归因 + 组合收益归因 | P2-#3 | 4–5 人日 |
| 组合优化器(均值-方差/风险平价) | P1-#4 | 3–5 人日 |
| VaR/CVaR/压力测试 | P2-#4 | 3–4 人日 |
| 连续 RiskGate runtime | P2-#5 | 4–5 人日 |
| 因子 IC 诊断闭环 CLI | F1-#6 | 2–3 人日 ✅(2026-06-16) |
| AKShare/东财 第二数据源 | P1-#2 | 5–7 人日 |

> 用户选股目标为"规则化打分",组合优化器(P1-#4)非阻断,Phase 3 视"优秀"程度需求决定是否做。

**Phase 3 合计:按需,~3–4 周**

---

## 六、端到端验证计划

### 6.1 验证分层

| 层级 | 内容 | 门禁 |
|---|---|---|
| L0 单元 | 每个新功能 TDD | CI test-unit(已有) |
| L1 golden E2E(ETF) | test_golden_e2e.py | CI golden-e2e(Phase 0 新增) |
| L2 golden E2E(选股) | 合成基本面全链路 | CI golden-e2e(Phase 1 新增) |
| L3 真实数据联通 | Tushare 真实数据全链路 | @pytest.mark.e2e,上线前手动跑 |
| L4 完整合成 golden | ingest→materialize→strategy→backtest | CI golden-e2e(Phase 1 目标) |

### 6.2 上线前 Acceptance Checklist

> 复核(2026-06-16):代码与测试门禁全绿。✅ = 已达成;⚠️ = 机制就绪,但达成需真实环境 / governance 决策(非纯代码可完成)。

- [x] P0-#1 基本面接入:个股选股 seed 跑通。(Phase 0 ✅)
- [x] P0-#2 CI golden 门禁:golden-e2e 在 PR 阻断。(`golden-e2e` job + ci-success 依赖就绪;P0-#2 "故意破坏 EngineLoop"项需首次 PR 触发 CI 实测)
- [x] Phase 1 选股 MVP:多因子打分选股 golden 通过。(Phase 1 ✅)
- [ ] ⚠️ Phase 2 数据 promotion:个股/宏观数据默认可用。**机制就绪,生产数据集未实际晋级**——promotion evidence 全套(`PromotionEvidenceCollector` + `ReviewDatasetPromotionEvidenceHandler` + `ditto ops promotion-collect` + golden governance 闭环测试)已就绪;但生产 stock/macro 数据集仍为 experimental(fail-closed),晋级需 reviewer 提交真实完整性证据并审批(governance 决策,禁止自造通过)。
- [ ] ⚠️ Phase 2 真实数据:1 年真实数据全链路跑通,NAV/alpha 报告产出。**部分就绪**——FRED realtime PIT e2e 真实拉取验证(F2-#2 在真实 API 生效)+ Tushare ingestion 联通就绪;完整"1 年选股 → 回测 → NAV/alpha 报告"全链路待真实环境(Tushare VIP 积分 + FRED key)手动 acceptance。
- [x] 文档同步:capability-maturity.md 状态准确。(P0-#3 golden lane + F2-#2 FRED realtime PIT 已同步)
- [x] `pixi run -e dev check` 全绿 + 37 架构合约全绿。(2026-06-16 复核:8356 passed / 1 xfailed,37 kept / 0 broken,lint/fmt/type 全过)

---

## 七、总体里程碑与排期

| 阶段 | 内容 | ETA(单人) | 里程碑 |
|---|---|---|---|
| **Phase 0** | 解阻断链(基本面接入 + CI golden + 文档) | ~1 周 | 个股选股可跑 + CI 有保护 |
| **Phase 1** | 选股 MVP(预处理 + 行业 + 融合 + golden) | ~1.5–2 周 | 选股策略端到端可上线 |
| **Phase 2** | 数据 promotion + 真实数据联通 | ~1 周 | 个股/宏观数据默认可用 |
| **MVP 上线** | **Phase 0–2 合计** | **~4–5 周(单人)** | **个股+ETF+宏观 日频选股上线** |
| Phase 3 | 体验/机构级(可选) | ~3–4 周 | 归因/优化器/VaR |

> 多人并行可压缩:Phase 0 的 P0-#1/#2/#3 可并行;Phase 1 的 F1-#1/#2/#5 可部分并行。2–3 人团队 MVP 约 2–3 周。

---

## 八、风险与依赖

| 风险 | 影响 | 缓解 |
|---|---|---|
| 基本面接入触及 DataFeed Protocol,影响面广 | 中 | 用 TDD + 独立 `get_fundamental_snapshot` 方法最小侵入 |
| 行业分类数据 Tushare 接口积分限制 | 中 | 确认积分,必要时用静态申万分类表 |
| 真实数据联通发现未预见的 PIT/DQ 问题 | 中高 | Phase 2 预留 buffer,问题驱动修复 |
| FRED PIT 改造影响历史数据语义 | 低 | 仅 macro_indicators 受限,不影响选股 |
| 团队继续被 execution/broker 矩阵分散精力 | 高 | 明确停止该方向主动扩展(见评估报告 §一) |

### 外部依赖

- Tushare API 积分(基本面 VIP 批量、行业接口)
- FRED API key
- GitHub Actions CI minutes(golden-e2e 增加少量)

---

## 九、与既有架构/规范的合规性

本路线图所有修复方案均符合现有架构约束:

- 基本面接入走 DataFeed(application/CLAUDE.md 已规定的 factor bundle 数据接入点),不破坏分层。
- 选股 stage 增强在 strategy 包内(纯策略),不引入 strategy→data/forbidden 依赖。
- 行业数据走 data→application 注入,符合现有 maturity gate 规则。
- CI 修改只动 workflow 文件,不改架构边界。
- 所有任务遵循 TDD + `pixi run -e dev check` + 37 架构合约门禁。

---

## 十、决策记录

- **选股形态**:规则化多因子打分(用户确认,2026-06-14)。覆盖 80% 个人量化选股需求,投入产出比最优。
- **组合优化器**:列 Phase 3 可选,非 MVP 阻断。
- **真实券商**:明确 out of scope(reserved)。
- **intraday 回测**:明确 out of scope(日频目标)。
- **AKShare/东财 第二源**:列 Phase 3,单源风险 Phase 2 评估后决定是否提前。

# Ditto 质量评估报告 2026-06-16

> 评估模式: `--full`（6 维度并行评估）| 评估时间: 2026-06-16
> 项目阶段: Phase 3 F1-#6 因子 IC 诊断 CLI 完成，MVP（Phase 0-2）上线就绪
> 评估范围: code + arch + test + eng + ops + domain 六维度全量实测
> 评估方法: Phase 0 预跑基线（lint/type/test/arch-check/LOC）→ 6 个 Agent 并行评估（Explore × 4 + general-purpose × 2）→ 加权合成

---

## 综合评分

```
              测试质量
               5.0★ 🟢
                 |
    代码 4.70★ ──┼── 3.70★ 运维
    🟢          |         🟡
    架构 4.81★ ──┼── 4.85★ 领域
    🟢          |         🟢
                 |
              工程流程
               3.81★ 🟡

    综合评分: 4.56 / 5.0 ★ 🟢 优秀
```

**综合评分: 4.56 / 5.0 ★** (加权) — 🟢 优秀

| 维度 | 评分 | 评级 | 变化（vs 06-13） |
|------|------|------|------|
| ① 代码质量 | 4.70/5.0 ★ | 🟢 优秀 | ↓ -0.23 ¹ |
| ② 架构质量 | 4.81/5.0 ★ | 🟢 优秀 | ↓ -0.09 ² |
| ③ 测试质量 | 5.00/5.0 ★ | 🟢 优秀 | ↑ +0.50 |
| ④ 工程流程 | 3.81/5.0 ★ | 🟡 合格 | ↑ +0.11 |
| ⑤ 运维质量 | 3.70/5.0 ★ | 🟡 合格 | ↑ +0.10 |
| ⑥ 领域特有 | 4.85/5.0 ★ | 🟢 优秀 | ↑ +0.75 |

> ¹ 代码质量下降非客观退化：C1/C2/C3/C5/C6/C7/C8/C9/C10 九项仍全绿（生产 `# type: ignore`=0、pandas=0、TYPE_CHECKING=0、ruff/basedpyright 全过）。差异来自 C4 重复度评估口径——本次 Agent 按「未引入 jscpd/SonarQube」给 warning，而上次（06-13）实测 AST 重复率 0.086%（远低于 2% 绿线）。客观代码质量未退化，仅量化工具缺位。
> ² 架构 A1-A7/A9 全绿（37 合约 + 18 arch-smells 通过），差异来自 A8 SQALE 工具缺位（同 C4 根因：技术债量化工具未引入）。

**加权公式**: code(0.20) + arch(0.25) + test(0.15) + eng(0.10) + ops(0.15) + domain(0.15)
**计算**: 4.70×0.20 + 4.81×0.25 + 5.00×0.15 + 3.81×0.10 + 3.70×0.15 + 4.85×0.15 = **4.556 ≈ 4.56**

---

## 各维度详情

### ① 代码质量 — 🟢 优秀 (4.70★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| C1 | 类型安全 | ★★★ | ✅ pass | basedpyright strict 0 errors/warnings/notes；生产 `# type: ignore` = **0**（测试 409）；抽样 strategy/alpha/pipeline.py 全函数完整类型注解，cast 仅在 SQLite 行解码边界合理使用 | — |
| C2 | 代码复杂度 | ★★★ | ✅ pass | ruff C901 强制 select 输出空；抽样 SQLiteCatalogSourceFallbackPolicyStore 已将查询构造/行解码拆分为模块级小函数 | — |
| C3 | 函数体大小 | ★★★ | ✅ pass | ruff PLR0915 输出空；StrategyPipeline.run ~33 行细分为 4 个注释化 step；逻辑方法主体 <50 行 | — |
| C4 | 代码重复度 | ★★☆ | ⚠️ warning | **未引入 jscpd/SonarQube**，无量化重复率；抽查 fallback_policy_store 与 remediation_store 两个 SQLite store 的 list-query 构造/upsert/append_event 模式近乎同构 | 引入 jscpd 接入 CI 量化；提取 SQLite store 基类收敛结构性重复（注：06-13 实测重复率 0.086%，客观水平优秀） |
| C5 | 代码规范合规 | ★★☆ | ✅ pass | ruff 全规则 0 errors/warnings；生产 noqa 67 处，密度 **0.50/1000 行**（优于 1/1000 绿线） | — |
| C6 | 参数数量控制 | ★★☆ | ✅ pass | ruff PLR0913 输出空，零函数超 7 参；抽样均用 keyword-only + ≤5 参 | — |
| C7 | 命名与可读性 | ★★☆ | ✅ pass | data 层 CQRS 严格区分 *_reader/*_writer/*_store；factors 用 reversal_1m/momentum_3m/umd_6m 行业标准命名；context.py 动词选择准确 | — |
| C8 | 注释质量 | ★☆☆ | ✅ pass | 注释聚焦「为什么」：pipeline.py docstring 详述 DecisionFrame 列约定与 fail-closed 设计意图；context.py 解释 cooldown 边界语义 | — |
| C9 | 死代码/未用导入 | ★☆☆ | ✅ pass | ruff F401/F811 输出空；TYPE_CHECKING 0、import * 0 | — |
| C10 | 依赖合规 | ★★★ | ✅ pass | pandas 导入 **0**；2 处 stdlib json 导入均为合规用法（fallback_policy_store/remediation_store 用 json.dumps/loads 做 SQLite TEXT 列的 tuple/dict 序列化，非业务数据处理） | 可选：统一到 orjson 或加 noqa 注释说明 |

**关键指标**: 生产 `# type: ignore` = **0** | 生产 noqa = 67 (0.50/1000 行) | pandas = 0 | ruff = 0 errors | basedpyright = 0 errors | 测试/代码比 = 1.54x

### ② 架构质量 — 🟢 优秀 (4.81★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| A1 | 依赖方向合规 | ★★★ ⁽硬⁾ | ✅ pass | .importlinter **37 合约**全 KEPT（layered + kernel/platform 隔离 + 6 个 capability 边界 + 生产↛analysis + apps 边界 + R8 CQRS 互斥 ×6 + data 子域/数据源隔离 ×9 + acyclic-packages depth=10）；arch-check 37 KEPT 0 broken | — |
| A2 | 包间耦合度 | ★★★ | ✅ pass | forbidden 合约固化每条耦合边界；acyclic-packages 守护 12 包无环；例外均为显式受控豁免（platform.exceptions→kernel、apps.registry 作 Composition Root） | — |
| A3 | 模块内聚性 | ★★★ | ✅ pass | 12 包各承载单一领域能力；各包 CLAUDE.md 明确目录职责；包规模分布合理（data 35K/application 31K 为最大能力域，余 1.5K-17K），无 god-package | — |
| A4 | 组件独立性 | ★★★ ⁽硬⁾ | ✅ pass | 生产 src TYPE_CHECKING = **0**；import * = **0**；arch-check acyclic-packages KEPT 无循环依赖；re-export 链深度 ≤2 硬约束 | — |
| A5 | API 表面积控制 | ★★☆ | ✅ pass | **12/12 包**顶层 __init__.py 声明显式 __all__（100%）；6 包用 `__all__=[]` 闭包模式 + 6 包显式枚举（kernel 32/risk 20/features 8）；arch-smells check 18 强制 | 在 6 个空 `__all__` 包 CLAUDE.md 增补闭包模式说明 |
| A6 | 抽象层级一致性 | ★★☆ | ✅ pass | application 严格 CQRS（queries/commands/processes/builders，R8 用 6 个 forbidden 合约固化互斥）；data storage 统一 Reader/Writer 命名约定；capability 包统一 contracts/errors/events 结构 | — |
| A7 | Fitness Functions 覆盖 | ★★☆ | ✅ pass | arch-check(37 合约) + arch-smells(**18 项检查**) + type/lint/test 全部集成 pixi check 与 ci；arch-smells 覆盖 f-string 日志/缺失 __init__.py/>800 行超大文件/跨包 re-export/__all__ 缺失等 | — |
| A8 | 技术债管控 | ★★☆ | ⚠️ warning | Fowler 四象限正面：3 份归档技术债清理计划、mccabe max-complexity=10、src 仅 2-3 处真实 TODO、capability-maturity manifest；**但未引入 SQALE/SonarQube/radon/vulture** 等可量化工具，无法给出 SQALE<5%=A 级客观评级 | 引入 radon（CC/MI）+ vulture（死代码）接入 pixi check 建立基线，按需接入 SonarQube 获取 SQALE 评级 |
| A9 | 架构文档一致性 | ★☆☆ | ✅ pass | 根 CLAUDE.md 依赖图与 .importlinter 37 合约及 packages 实际结构三方一致；docs/architecture 含 boundaries 标准 + 5 份 ADR + 2026-05-31 architecture-review | — |

**关键指标**: importlinter 合约 = 37 全绿 | arch-smells = 18 项全过 | 循环依赖 = 0 | TYPE_CHECKING 生产 = 0 | __all__ 覆盖 = 12/12 (100%) | 最大文件 = 799 行（<800 阈值）

### ③ 测试质量 — 🟢 优秀 (5.00★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| T1 | 分支覆盖率 | ★★★ ⁽硬⁾ | ✅ pass | pyproject addopts 含 `--cov-branch` + CLI 门禁 `--cov-fail-under=85`（优秀线）+ `[tool.coverage.report] fail_under=80`；--fast 不采集但完整 CI 强制 85% 分支门禁 | — |
| T2 | 测试分层 | ★★★ | ✅ pass | 12 unit / 6 integration / 1 e2e 目录分层；定义 unit/integration/e2e/slow/snapshot/pit 标记；回测集成层含 golden_baseline/reproducibility/invariants 三类金字塔顶层验证 | 可选：将回测 golden_baseline 跨包链路归类至 e2e 层 |
| T3 | 测试独立性 | ★★★ | ✅ pass | pytest-xdist `-n auto --dist loadfile`；8356 用例并行通过无顺序依赖失败；serial 标记仅 20 文件用于 inline-snapshot 隔离 | — |
| T4 | 测试确定性 | ★★★ ⁽硬⁾ | ✅ pass | flaky 标记 **0**；xfail 3 处（cs_rank D7 polars 限制、SQL injection/engine 因 pyarrow 缺失）均带明确 reason；`--strict-markers`/`--strict-config` | 对 cs_rank xfail 添加 strict=True（缺陷行为明确，xpass 会提醒清理） |
| T5 | 测试命名与可读性 | ★★☆ | ✅ pass | TestXxx 类分组 + 中文意图 docstring + 描述性方法名；given/when/then 在注释表达 | — |
| T6 | 核心路径覆盖 | ★★★ | ✅ pass | 核心包测试文件数：execution=48 / risk=24 / backtest=41（合计 113）；覆盖 OMS FSM、broker gateway conformance、reconciliation、drawdown/loss-limit 规则 | — |
| T7 | 断言质量 | ★★☆ | ✅ pass | 精确断言（action_type/severity/rule_id 枚举值、精确返回值）；reconciliation_workflow_store 单文件 113 处断言 | — |
| T8 | Mock 合理性 | ★★☆ | ✅ pass | 仅用 MagicMock 隔离数据切片外部依赖，被测规则/账户视图用真实对象；BrokerGateway Protocol + PaperBrokerGateway 真实边界抽象，不过度 mock | — |
| T9 | 测试执行速度 | ★☆☆ | ✅ pass | --unit --fast: 8356 passed in **41.49s**，远低于 2min 优秀阈值 | — |
| T10 | 边界/异常测试 | ★★☆ | ✅ pass | 覆盖 0/负数/exact lot/tiny weight 1e-9/truncation/config error/reset noop 边界 | — |

**关键指标**: fast 套件 = 8356 passed / 1 xfailed (41.49s) | flaky = 0 | 测试文件 = 718 | 测试 LOC = 205,412 | 分支门禁 = 85% | xdist = enabled

### ④ 工程流程 — 🟡 合格 (3.81★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| P1 | 部署频率 | 2 | ⚠️ warning | 30 天 4 个 feat 提交（Phase 0→3），约每周 1 个可上线能力；量化平台「部署」=数据管道/策略上线，非传统服务部署，估算不确定性高 | 建立数据管道/策略上线的显式部署记录（release notes / strategy registry 版本号） |
| P2 | 变更前置时间 | 2 | ⚠️ warning | PR 前置时间跨度大：PR#62 15 天、PR#66 创建 05-31 至今(06-16) OPEN >15 天；feature 分支直接提交 main 为小步快跑但 PR 形态偏长 | 长期 OPEN PR 拆分为更小可合并单元 |
| P3 | 变更失败率 | 2 | ✅ pass | 60d 仅 2 个 fix 提交（均 review 主动整改非线上故障）；37 合约 + golden e2e 守护下无「变更致故障」记录 | — |
| P4 | 恢复时间 | 2 | ⚠️ warning | 未度量；无线上 incident log，MTTR 数据不可得 | 建立最小 incident log 记录回滚/热修耗时 |
| P5 | 返工率 | 2 | ✅ pass | 60d 20 提交中 fix/revert 仅 2 个 = **10%**，低于 15% 精英阈值；提交类型分布健康（refactor 7/feat 6/docs 4/fix 2/style 1） | — |
| P6 | 审查覆盖率 | 3 | ⚠️ warning | CLAUDE.md 有完整结构化审查标准，但 GitHub branch protection **未启用**（私有仓库 403），无法实证「每 PR 必须审查」强制门禁；单人开发本质无法 100% | 至少启用 branch protection 的 required status check 门禁（ci-success） |
| P7 | PR 大小 <400 LOC | 2 | ❌ **fail** | **PR 普遍严重超标**：PR#66 +92634/-9100 (694 files)、PR#63 +85547 (1864 files)、PR#61 +98880 (1932 files)、PR#64 +28771 (676 files)；最近 Phase 提交单次仍 997-1577 insertions | **按 capability package / Batch 子任务拆分为 <400 LOC 可审查单元**；进行中的 PR#66（9 万行）拆为多个子 PR |
| P8 | 审查响应 <24h | 2 | ⚠️ warning | PR#62 15 天、PR#66 >15 天；单人开发无外部审查者 | feature 分支 commit-to-main 时长作响应代理指标 |
| P9 | 审查质量 | 3 | ⚠️ warning | 方法论卓越（北极星原则/三铁律/TDD/Read≥2x Edit/Skills 强制调用/Boundaries 三级），设计-功能-复杂度-测试四维覆盖；但缺外部审查实证与 PR review comment | 保留 PR review comment（即使自审 checklist）；定期引入外部 code review（codex/peer） |
| P10 | 审查清单 | 2 | ✅ pass | CLAUDE.md「完成前验证」明确清单（basedpyright/ruff/测试/分支覆盖率≥80%）+ Boundaries Ask first/Never do 硬性清单；verification-before-completion Skill 强制 | — |
| P11 | Lint 门禁 | 2 | ✅ pass | ci.yml lint job: `ruff check` + `ruff format --check`；pre-commit ruff-lint-fix/ruff-format；ci-success required | — |
| P12 | 类型检查门禁 | 2 | ✅ pass | ci.yml 双重：audit job + type-check job 均 `type --all`（basedpyright strict）；pre-commit pyright hook | — |
| P13 | 测试+覆盖率门禁 | 2 | ✅ pass | ci.yml test-unit job 硬性 `--cov-fail-under=80`（packages + interfaces 各一）；分层 ci.yml/ci-integration.yml/e2e-validation.yml；golden-e2e 进 PR 门禁 | — |
| P14 | 架构门禁 | 2 | ✅ pass | ci.yml audit job: `arch-check`（37 合约 CI 守护）；强制依赖层级 + explicit forbidden contracts | — |
| P15 | 格式化门禁 | 2 | ✅ pass | ci.yml lint job: `ruff format --check --diff`；pre-commit ruff-format；CI 与本地工具版本一致（local pixi run） | — |

**关键指标**: CI 门禁完备性 = **5/5 齐全且硬性**（lint/type+cov80/arch/format + ci-success 汇总）| 返工率 = 10%（精英级）| 架构合约 = 37 CI 守护
**核心短板**: P7 PR 规模严重超标（唯一 fail，是 P6/P8/P9 审查问题的根因）；P1/P4 DORA 指标未度量

### ⑤ 运维质量 — 🟡 合格 (3.70★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| O1 | 结构化日志 | ★★★ | ✅ pass | logging.py 配置完整 JSONL sink：orjson 提取字段，生产强制 ditto.jsonl，rotation=1 day/retention=30 days/gz 压缩，异常拆分 ditto_error.log；loguru 537 处；extra= 上下文绑定 | — |
| O2 | 业务指标度量 | ★★★ | ⚠️ warning | 指标注册表丰富（cache/SQL/JSON/API + portfolio: portfolio_value/drawdown/rebalance_total），但**业务代码实际 record 调用仅 1 处**（sql_engine.sql_query_duration）；回测耗时/管道延迟/策略 PnL 定义未埋点 | 在回测 engine loop、数据 source.fetch、策略 PnL 处补齐 Metrics.record() |
| O3 | 分布式追踪 | ★★☆ | ⚠️ warning | OTel 基础设施完整（TracerProvider/OTLPSpanExporter/采样器/InMemorySpanExporter），但**业务包 span 埋点 = 0**（25 处 import 全在 foundation/observability/tracing.py 内）→「引依赖未铺开」 | 在关键链路（回测 loop、source.fetch、API handler、catalog fallback 决策）植入 span |
| O4 | 容错与重试 | ★★★ | ⚠️ warning | tenacity 模式正确（tushare/fred: stop_after_attempt(3)+wait_exponential+retry_if_exception_type）；catalog fallback policy 持久化降级；回测有 can_retry 语义；但**仅 2 外部数据源有重试，tdx 本地读取器无；无真正 CircuitBreaker** | DataSource base 统一重试装饰器；引入断路器（pybreaker） |
| O5 | 数据持久性 | ★★★ | ✅ pass | SQLite WAL 模式显式启用两处（sqlite_pool/execution journal，注释「并发读写 + 数据安全」）；parquet/duckdb/sqlite 栈合规；backups 目录配置；execution order journal append-only | — |
| O6 | 性能基准 | ★★☆ | ⚠️ warning | 存在 benchmark 框架（derived_benchmark.py: query/materialize/shadow_compare × S/M/L scale）；sql_engine 慢查询阈值检测；但 **CI 无 pytest-benchmark，pixi 无 bench 任务，无自动化回归门禁** | CI 增加 nightly 性能基线回归 job，对比 benchmark 耗时与历史基线 |
| O7 | 安全态势 | ★★★ ⁽硬⁾ | ⚠️ warning | 正面：keyring 密钥管理带优雅降级、硬编码密钥候选 **0**、pre-commit gitleaks + detect-private-key、SQL 参数化 + validate_identifier、PIT fail-closed、Dependabot；**扣分：API 层无认证/授权中间件（FastAPI 路由裸暴露）、CI 无 pip-audit/safety/trivy 漏洞扫描**，无法证明 Critical/High=0 | 为 API 引入认证中间件（APIKey/JWT）；CI 增加 pip-audit/osv-scanner 设 Critical/High 阻断门禁 |
| O8 | 配置管理 | ★★☆ | ✅ pass | config/{default,development,production,testing} 四环境隔离；get_environment() 统一入口带校验（非法值抛 ValueError 列举合法值）；敏感信息走 keyring | — |
| O9 | 资源效率 | ★★☆ | ⚠️ warning | granian ASGI（workers/http2）；cachebox 缓存统计齐备；但**无内存监控**（tracemalloc/RSS 全 0），无内存泄漏回归测试 | 引入 prometheus process collector 或 periodic tracemalloc snapshot |
| O10 | 灾备能力 | ★☆☆ | ⚠️ warning | 回测状态可恢复（restore_runtime_state/restore_ticket/DrawdownStateSnapshot）；但 MVP 阶段无整体灾备预案、无 backup-restore 演练、parquet/duckdb 无跨机备份 | MVP 后制定 RPO/RTO，补充异地备份与 restore 演练 |

**关键指标**: loguru = 537 处 | OTel 业务 span 埋点 = **0** | tenacity 重试 = 4 处（2 数据源）| keyring = 12 处 | 硬编码密钥 = 0 | API 认证中间件 = **无** | CI 漏洞扫描 = **无**
**系统性短板**: 可观测性「基础设施搭建质量高，但业务层实际埋点未铺开」（O2/O3 共同根因）

### ⑥ 领域特有 — 🟢 优秀 (4.85★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| D1 | 回测确定性 | ★★★ ⁽关键⁾ | ✅ pass | test_reproducibility.py 多层验证：同 manifest 两次运行一致 + manifest JSON 字节级一致（排除 created_at）+ NAV 一致 + engine_version 变更可区分；manifest 冻结 strategy_version/parameter_overrides/config_hash/input_refs | — |
| D2 | 数据完整性 | ★★★ | ✅ pass | QualityEngine 编排技术/业务/统计三类检查（含 zscore 异常 + completeness_gap 缺失日期检测）；Phase2 PromotionEvidenceCollector 客观收集 3 条 criteria 证据（不自造通过）+ golden governance 闭环；FRED realtime PIT（knowledge_date=realtime_end + vintage 去重） | — |
| D3 | 前视偏差防护 | ★★★ ⁽硬⁾ | ✅ pass | **11 处 rolling 调用中 9 处无 closed= 经核查全部合法（0 真前视偏差）**：9 处全在 features/expression/codegen/_builders.py，因 Polars Expr-level rolling_*() 不支持 closed 参数，故统一用 argument.shift(1) 实现等效 closed="left"（窗口 [T-window, T-1]）；_builders.py:41-43/94-110 注释明确 PIT 策略；test_expression_time_series_crosscheck_unit.py 反向验证（丢弃 shift(1) 的 reference 必须发散）；pit.md 固化 closed="left" 约定 | — |
| D4 | 策略隔离 | ★★★ ⁽硬⁾ | ✅ pass | arch-check 确认 strategy 禁依赖 execution KEPT；strategy 产 signal_snapshot，execution 消费 Order，二者经 application 编排解耦 | — |
| D5 | 风控独立性 | ★★★ ⁽硬⁾ | ✅ pass | pre_trade（盘前阻断）+ post_trade（盘后审计）双路径；risk 仅依赖 kernel+portfolio（窄依赖）；KillSwitch 紧急熔断；arch-check 确认 risk 依赖约束 KEPT | — |
| D6 | 订单生命周期完整性 | ★★★ | ✅ pass | OrderTicket frozen dataclass + order_events append-only（with_fill 追加事件）+ FSM 强制合法转换 + @traced 分布式追踪；超量成交抛 ValueError | — |
| D7 | 因子计算正确性 | ★★★ | ✅ pass | features/evaluation/metrics 完整交叉验证：IC/rank_IC/ICIR/分层/多空/换手/Fama-MacBeth/暴露/归因；Phase3 因子 IC 诊断 CLI（ditto ops factor-ic）输出 Markdown 报告；编译/物化/评估三层可交叉验证 | 移除 cs_rank xfail：按标注路径完成跨日期实现 |
| D8 | 策略参数可审计 | ★★☆ | ✅ pass | StrategySpecRecord 含 version + spec_version；contracts.py 提供 get_spec/list_versions/update_status；strategy_run_service 持久化 strategy_version + list_lineage；manifest 冻结 parameter_overrides + config_hash | — |
| D9 | 市场数据时效性 | ★★☆ | ⚠️ warning | catalog_freshness.py 提供 assess_catalog_freshness 按 SLA 评估 + data_freshness 可观测指标 + freshness_at 持久化；但**无自动化告警门禁**（stale 数据不阻断下游），仅评估非强制 | 回测前置/数据摄入后加 freshness SLA 硬检查，stale 抛 typed AppError 阻断 |
| D10 | 回测-实盘一致性 | ★★☆ | ✅ pass | 回测与实盘共享同一 capability 包平面（strategy/portfolio/risk/execution）；execution 禁依赖 backtest（arch-check KEPT）；差异仅在 gateway 注入层（PaperBrokerGateway vs 真实网关），核心路径最大复用 | — |

**关键指标**: 前视偏差真违规数 = **0**（9 处全 shift(1) PIT 合规）| 确定性测试文件 = 12 | 订单审计链 = frozen + append-only + @traced | 因子评估指标族 = IC/ICIR/分层/多空/换手/Fama-MacBeth/暴露/归因

---

## Top 10 改进项

按优先级（影响面 × 权重 × severity）排序：

| # | 维度 | 评价项 | 优先级 | 建议 |
|---|------|--------|--------|------|
| 1 | 工程流程 | P7 PR 规模严重超标（fail） | 🔴 P0 | 将巨型 PR（PR#66 达 92634 LOC/694 files）按 capability package / Batch 子任务拆分为 <400 LOC 可审查单元；CI/PR 模板加大小告警。这是 P6/P8/P9 审查问题的根因 |
| 2 | 运维质量 | O7 API 无认证 + CI 无漏洞扫描（硬性） | 🔴 P0 | apps 层引入认证中间件（APIKey/JWT）保护非只读路由；CI 增加 pip-audit/osv-scanner 设 Critical/High 阻断门禁，使 O7 硬性要求可被持续验证 |
| 3 | 工程流程 | P6/P9 审查强制门禁缺失 | 🟠 P1 | 启用 GitHub branch protection 的 required status checks（至少 ci-success + arch-check）；保留 PR review comment 使审查质量可追溯；定期引入外部 code review（codex/peer） |
| 4 | 运维质量 | O3/O2 可观测性未铺开 | 🟠 P1 | 在关键链路（回测 engine loop、数据 source.fetch、API handler、catalog fallback 决策）植入 OTel span 与 Metrics.record()；复用 CLAUDE.md 约定的 @traced 装饰器 |
| 5 | 运维质量 | O4 容错覆盖偏窄、无断路器 | 🟡 P2 | DataSource base 统一重试装饰器；引入断路器（pybreaker）在 source 连续失败时熔断并切 fallback；tdx 本地读取器补 IO 重试 |
| 6 | 架构质量 | A8 SQALE 技术债量化工具缺位 | 🟡 P2 | 引入 radon（CC/MI/Halstead）+ vulture（死代码）接入 pixi check 建立基线，按需接入 SonarQube 获取 SQALE A-E 评级 |
| 7 | 领域特有 | D9 数据时效性无强制门禁 | 🟡 P2 | 回测前置校验或数据摄入后加 freshness SLA 硬门禁，超阈值 stale 抛 typed AppError 阻断流程或触发告警 |
| 8 | 工程流程 | P1/P4 DORA 部署频率与 MTTR 未度量 | 🟡 P2 | 建立轻量度量：部署记录（strategy registry 版本/release notes）+ incident log（回滚/热修耗时），适配量化平台语义 |
| 9 | 代码质量 | C4 代码重复度无量化基线 | 🟢 P3 | 引入 jscpd 接入 CI 量化重复率；提取 SQLite store 基类收敛 fallback_policy_store/remediation_store 结构性重复（注：06-13 实测 0.086%，客观水平优秀，此为度量工具补全） |
| 10 | 运维质量 | O6 性能基线无 CI 自动回归 | 🟢 P3 | CI 增加 nightly 性能基线回归 job，对比 derived_benchmark S/M/L 耗时与历史基线并设退化阈值告警 |

---

## 与上次评估对比

上次全量评估（2026-06-13，quick 模式实测 code/arch/test，eng/ops/domain 沿用 06-04）：

| 维度 | 上次 (06-13) | 本次 (06-16) | 变化 | 说明 |
|------|-------------|-------------|------|------|
| ① 代码质量 | 4.93 ★ | 4.70 ★ | ↓ -0.23 | C4 评估口径差异（本次按「未引入工具」warning，上次 AST 实测 0.086%）；客观代码质量未退化（9/10 项仍全绿） |
| ② 架构质量 | 4.90 ★ | 4.81 ★ | ↓ -0.09 | A8 SQALE 工具 warning（与 C4 同根因）；A1-A7/A9 全绿 |
| ③ 测试质量 | 4.50 ★ | 5.00 ★ | ↑ +0.50 | 确认 85% 分支门禁 + 10 项全 pass + flaky=0 |
| ④ 工程流程 | 3.70 ★ | 3.81 ★ | ↑ +0.11 | CI 5 门禁齐全；P7 PR 规模 fail 持续 |
| ⑤ 运维质量 | 3.60 ★ | 3.70 ★ | ↑ +0.10 | 日志/持久性/配置正面；API 认证 + 可观测性埋点短板浮现 |
| ⑥ 领域特有 | 4.10 ★ | 4.85 ★ | ↑ +0.75 | **D3 前视偏差确认 0 真违规**（9 处 shift(1) PIT 合规）+ 因子 IC 诊断 CLI 完成 |
| **综合** | **4.41 ★** | **4.56 ★** | **↑ +0.15** | 四维度提升抵消两维度口径差异；领域维度提升最显著 |

**趋势解读**:
- 🟢 **领域质量显著提升（+0.75）**：本次 domain Agent 逐处核查了 11 处 rolling 调用，确认 9 处无 `closed=` 全部为合法 `shift(1)` PIT 守护，消除前视偏差疑虑；Phase 3 因子 IC 诊断 CLI 补齐因子评估闭环。
- 🟢 **测试质量满分（+0.50）**：85% 分支覆盖门禁 + 10 项全 pass + flaky=0 + xdist 并行稳定。
- 🟡 **工程流程（+0.11）**：CI 门禁完备性保持 5/5，但 P7 PR 规模严重超标（历史 PR 达 9 万行级）是唯一 fail 项，且是审查维度（P6/P8/P9）的根因。
- 🟡 **运维质量（+0.10）**：日志/持久性/配置/密钥管理正面，但可观测性「引依赖未铺开」（OTel 业务 span=0、Metrics 业务 record=1）与 API 无认证两大系统性短板浮现——这是 MVP 上线就绪向生产成熟演进的关键差距。
- 📉 **代码/架构微降（-0.23/-0.09）**：客观质量无退化（type:ignore/pandas/TYPE_CHECKING 仍 0、37 合约全绿），差异源于 C4/A8「量化工具缺位」评估口径，**根因同为：技术债量化工具（jscpd/radon/SQALE）未引入**。

---

## 附录

### 基线数据（Phase 0 预跑，2026-06-16）
- **核心门禁全绿**: Lint(All passed) | Type(0 errors/warnings/notes) | Test(8356 passed, 1 xfailed in 41.49s) | arch-check(37 KEPT 0 broken) + arch-smells passed
- **规模**: SRC 133,228 LOC (994 文件) / TEST 205,412 LOC (718 文件)，测试/代码比 1.54x
- **代码静态**: type:ignore 生产 0 | noqa 生产 67 (0.50/1000 行) | pandas 0 | stdlib json 2(合规) | TYPE_CHECKING 0 | import * 0
- **可观测性/安全**: loguru 537 | OTel 25(业务 span 0) | tenacity 4 | cachebox 19 | keyring 12 | 硬编码密钥 0
- **领域/测试**: rolling 调用 11(带 closed= 2；9 处 shift(1) 合规) | xfail 4 | flaky 0 | 确定性测试文件 12
- **工程流程**: 30d commit 15 / merge 0(squash) | 远程分支 3 | CI: ci.yml + ci-integration.yml + e2e-validation.yml | pre-commit 17 hooks | config: 4 环境

### 评价框架
- 完整框架: [docs/plans/2026-06-02-software-quality-evaluation-framework.md](../plans/2026-06-02-software-quality-evaluation-framework.md)
- 业界标准: ISO/IEC 25010:2023、CISQ/ISO 5055、SIG/TÜViT、SQALE、ATAM、Fitness Functions、DORA、SPACE、Fowler 技术债四象限

### 评估方法
- 6 个 Agent 并行（code/arch/test/ops 用 Explore；eng/domain 用 general-purpose）
- 每个 Agent 注入完整基线数据 + 该维度评价标准 + 统一输出 Schema
- 加权: code(0.20) + arch(0.25) + test(0.15) + eng(0.10) + ops(0.15) + domain(0.15)

### 结论
Ditto 处于 **🟢 优秀（4.56★）** 水平，MVP（Phase 0-2）已具备上线就绪质量。代码/架构/测试/领域四维度达优秀区间（4.70-5.00），工程流程与运维为合格区间的主要改进面。向生产成熟演进的两个关键差距：**(1) 工程实践——PR 拆分与审查强制门禁； (2) 运维可观测性——业务层埋点铺开与 API 安全加固**。技术债量化工具引入（jscpd/radon/SQALE）可同时补全 C4/A8 两项 warning。

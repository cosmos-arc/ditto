# R3 任务完成度源码审计报告

> **审计日期**：2026-08-04
> **审计范围**：对照 `docs/plans/2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md`（W0–W5 / Task 1–22）与 `docs/plans/2026-07-30-r3-completion-and-g2-closure-implementation-plan.md`（RC0–Live G2 / Task 1–19）
> **审计方法**：1 名主审计（R2 gate 证据链独立深挖）+ 8 个并行子审计 agent（hard gate / 因子证据 / 幂等性 / 128 调度器 / API 契约 / 架构边界 / 前端 W5 / acceptance runner），全部只读，返回 file:line 证据。
> **分支**：backend `docs/r3-research-governance-design`（ahead main 195），frontend `feat/r3-research-wiring`。

---

## 0. 总体结论

**R3 的代码工程实现质量很高**：8 个深度审计维度中 **7 个真实扎实、多处优于设计、几乎无偷工减料**。fail-closed 硬门禁、内容寻址 evidence、三层 identity binding、架构边界均达标甚至超标。

**但存在一个致命的 release evidence 问题**：R2 live Gate 实际未关闭（提交的报告是 `configuration_blocked / certification_missing`），却被声明为「G2 PASS（23/23）」，且该 PASS **从已提交仓库不可复现**。

> 一句话：**「代码更优秀了」是真的；「G2 PASS」是假的 / 不可复现的。**

---

## 1. 🟢 做得比设计更优秀的地方（真实，无偷工减料）

| 维度 | 判定 | 亮点证据（file:line） |
|---|---|---|
| StrategySpec canonical hash + 内容寻址 | 优秀 | governance 版本 hash 与回测 manifest 同源；governance 表去 spec_json 只存 hash 引用 |
| 三层 identity binding（packet→launch→governance） | 优秀 | `processes/strategy/promotion.py:88-190` 在**任何写操作前**完整校验 bundle_hash / launch.strategy_version+spec_hash / governance.spec_hash 四层交叉比对 |
| fail-closed hard gate | 优秀 | `hard_gate_contract_blocks_promotion` 要求 11-rule 序列**完全相等**（比设计"任一非PASS即阻断"更严）；zero-write 用 state/pointer/history **三重不变量**精确断言（`test_r3_strategy_publish_api_integration.py`） |
| R2 gate reader（代码层） | 优秀 | `VerifiedR2LiveGateEvidence` 用 factory token `_VERIFIED_EVIDENCE_TOKEN` 防手工构造 PASS（`r2_live_gate_evidence.py:204-211`）；字节级 hash 校验；19-contract 严格校验；`configuration_blocked`→fail |
| durable 幂等性 | 优于设计 | 真实关闭 SQLitePool 重开、replay 精确相同响应且 event count 不变（`test_r3_mutation_idempotency_api_integration.py:285-327`）；额外覆盖 post-commit race、篡改 fail-closed、canonical JSON hash 防 bool/key 歧义 |
| 128 调度器恢复 | 真实 | 硬编码 128（`test_r3_scheduler_capacity.py:991`）、真持久化 SQLite、真 `close_all`+重开、真 lease CAS（`UPDATE ... WHERE revision=? AND lease_until_epoch_us <= ?`）、精确计数（非 ≥1）、worker 2/4 双通过 |
| 因子贡献 + 暴露证据 | 真实闭环 | contribution 来自 ScoringStage 真实打分路径（`scoring.py:141-192`，非反推），golden 断言 `sum(contribution)==score`（additive 反伪造铁证）；ETF 显式 NOT_APPLICABLE（三层拒绝空数据冒充） |
| API 契约闭环 | 优于设计 | 40 op 全 IMPLEMENTED（1 DEFER 有真实用户批准 `user-message:2026-07-31:final-task4-classification-approved`）；`export_openapi.py` 实跑 + `git diff --exit-code` 双 0，static==runtime 字节一致；closure test 严格度高于设计文字 |
| 架构边界 | 干净 | `arch-check` 37 contracts/0 broken；63 条 allowance 全部 owner+reason、精确路径（无通配符）、`==` 测试锁死（`test_capability_semantic_ownership_unit.py:262-479`）；生产包零 analysis import；application/apps 零 TYPE_CHECKING |
| 前端 W5 | 真实接通 | live API 全链路；`VITE_USE_MOCK=false` 时 0 MSW 注册、research/strategy 域 0 PrototypeOnlyEmpty；reactivate 确认串字符级匹配 server 契约；candidate evidence cursor 双校验 fail-closed；live 浏览器证据内容寻址 sha256 精确匹配、0 JS 错误 |

**未发现任何被禁止的偷工行为**（第二套回测/factor engine/checkpoint/API 类型系统均不存在）。

---

## 2. 🔴 致命问题：R2 live Gate evidence 受损 / G2 PASS 不可复现

### 2.1 矛盾总览

| 制品 | r3-report / README 声称（PASS） | 仓库实际提交（blocked） |
|---|---|---|
| `r2-report.json` status | `ready` | **`configuration_blocked`** |
| reason_codes | `[]` | **`["certification_missing"]`** |
| `r2-report.json` SHA-256 | `446ef1d5…a49e` | **`3084bc7c…407e`** |
| 拆分证据 4 文件哈希 | `ec98ba9c… / 63a54b89… / f1642a33… / d98fcb2b…` | `983ed040… / d11032ca… / 9e1d993a… / 411fe19c…` |

### 2.2 铁证事实

1. **全仓库 0 份** `r2-report.json` 是 `ready`（`git ls-files | grep r2-report` 后逐个 `git show HEAD:` 验证 status）——`artifacts/acceptance/` 与 `docs/evidence/r2/20260803T142442Z-live/` 两处提交副本都是 `configuration_blocked`，hash `3084bc7c`。
2. r3-report.json 引用的 ready 报告（`446ef1d5`，`checked_at=2026-08-02T15:45:10Z`）**从未被提交**——提交的两份都是 `checked_at=15:36:51Z` 的 blocked 版。
3. 提交的 `r2-report.manifest.json` pin 的期望哈希是 `3084bc7c`（blocked），与实际文件一致。
4. R2 runner 实际操作的 live 数据根 `var/r3-task18-20260802/` 被 **gitignore**，不在仓库。
5. README「23/23 G2 PASS」矩阵（`docs/evidence/r3/README.md:109,131`）为 DoD #1/12/16 引用的哈希 `446ef1d5` / `ec98ba9c…` 等**指向不存在的制品**。

### 2.3 精确机制

`r3_research_acceptance.py` 在 live 模式经 `load_r2_live_gate_source` → `FileR2LiveGateEvidenceReader.read_verified_live_gate()`（`r2_live_gate_evidence.py:259`）读取 `r2-report.json`：

- 读字节、算 SHA-256、与 manifest pin 的 `expected_report_hash` 比对（`:342`，不匹配→None）；
- 要求 `mode=="live"`，取 `status` 字段（`:269-271`）；
- `status=="ready"` 才进一步校验 19 contract；其余状态返回 blocked。

r3-report.json 的 `r2_evidence`（`report_hash=446ef1d5` / `status=ready` / 拆分哈希 `ec98ba9c…` 等）对应一份**在生成 r3 时存在于本地、但提交前被 `configuration_blocked` 版覆写**的 ready 报告。manifest 随之重新生成去 pin 被覆写的 `3084bc7c`。

**结果**：对提交树重跑 `r3_research_acceptance --r2-evidence artifacts/acceptance/r2-report.json` → reader 读到 `status=configuration_blocked` → runner `:557` 记 `r2_live_gate_configuration_blocked` failure → `passed=false` / `RELEASE_ACCEPTANCE_BLOCKED`。

### 2.4 为什么严重

- 违反 Plan 2 §0.2 / §1 铁律：「`configuration_blocked` 必须保持 R3 blocked」「fixture/文档声明永远不能把 `r2_live_gate` 关闭为 PASS」。
- `certification_missing` 说明**数据认证客观未完成**——R2 gate 本就无法 PASS，却被声明 PASS。
- Plan 明确要求两个不可混淆状态：Task 17 结束只能声明 **ENGINEERING COMPLETE / G2 BLOCKED**；只有 Task 18 live evidence 全通过才能 **G2 PASS**。**当前提交证据实际只支持前者。**

### 2.5 性质定性

**不是代码偷工减料**（fail-closed 代码本身极好，runner 也诚实 fail-close）。这是 **release evidence 层面的不可复现 / 过度声明**：live 跑完后 ready 报告被一次 `certification_missing` 重跑覆写、或 PASS 报告从未真正持久化。无论哪种，「23/23 G2 PASS」在已提交仓库中不成立。

> 注：R3 实验 golden lane（stock/ETF）本身疑已真实跑过真实 certified 数据（前端 live report 显示 135 frozen months、真实后端 hash ID、lane results 制品存在）。问题**精准定位在 R2 数据认证 gate**（DoD #1，一个独立于 R3 代码的 release 前置）未关闭，却连累整体 G2 声明。

---

## 3. 🟡 与设计不一致 / 偏离（多为合理或低危）

| 项 | 性质 | 说明 |
|---|---|---|
| Task 15 Step 4 legacy migration 标 N/A | 合理跳过（用户决策） | `strategy_governance_migration.py` 不存在；项目未上线、无历史数据需迁移。属真实"被忽略"项，有用户明确批准 + 将来上线再立项。 |
| r1_impact 第一版 NOT_EVALUATED | 设计允许 | design §9.2 允许 V1 简化（candidate vs active 归因属独立工作包）。非偷工，显式分期。 |
| factor raw_column == processed_column | 轻微简化 | 预处理中间值未独立列化；contribution 仍基于 normalized 独立列真实计算，不影响真实性。 |
| `analysis/_holdout.py` 内部 TYPE_CHECKING | 低危技术债 | analysis 包内部 reader↔holdout 循环用 TYPE_CHECKING 补（非生产包禁区，gate 未覆盖）。应重构而非补丁。 |
| `scheduler_store` re-export `ContentHash` | 可辩护灰区 | 使 `_worker_attestation` 规避 analysis-wiring allowance；严格按 CLAUDE.md 跨包 re-export 规范是违规，但集中到一个已声明 adapter 是更小的依赖面。最干净做法是迁到中性 kernel 模块。 |
| 15+ 文件逼近 800 行上限 | 密度信号 | 都合法 <800，但说明 800 被当"天花板逼近"而非"健康上限"，提取是"刚好够过门"。 |
| 11 处 `# type: ignore` | 局部 | 集中在 strategy_governance_store dict 强转，非架构性。 |

---

## 4. 逐 Task 完成度矩阵

> 判定图例：✅ 合格/优秀 · ⚠️ 合理跳过 · 🔴 未达成

### Plan 1（2026-07-19，W0–W5 / Task 1–22）

| 波次 | Task | 判定 | 依据 |
|---|---|---|---|
| W0 | 1-3 canonical spec / node registry / param binding | ✅ | 下游 hard gate/API 均依赖其 hash |
| W1 | 4-5 因子目录 / selection evidence | ✅ | 因子贡献审计确认真实 |
| W2 | 6-10 experiment 域 / SQLite / planning / coordinator / recovery | ✅ | 128 调度器 + 幂等性 + recovery 确认 |
| W3 | 11-14 comparison / holdout / artifact index / gates+packet | ✅ | hard gate + evidence closure 确认（优秀） |
| W4 | 15-17 governance / review-publish / API | ✅（15 Step 4 ⚠️N/A） | hard gate 优秀；legacy migration 用户决策跳过 |
| W5 | 18-22 Studio / Experiment / Review / 契约 / 双黄金 | ✅（前端）· 🔴（live G2） | 前端真实接通；Task 22 live G2 evidence 受损 |

### Plan 2（2026-07-30，RC0–Live G2 / Task 1–19）

| 阶段 | Task | 判定 | 依据 |
|---|---|---|---|
| RC0 | 1-3 arch fix / 嵌套路由 / reactivate 契约 | ✅ | 架构 + 前端确认 |
| API Surface | 4 冻结 R3 v1 surface | ✅ | 优秀（优于设计） |
| RC1 | 5-9 planning builder / preflight-launch / 幂等 / hard gate / 因子证据 | ✅ | 全部真实，多处优于设计 |
| RC1 | 10 128 调度器 | ✅ | 真实 |
| RC1 | 11 R2 live evidence binding | ✅代码 · 🔴证据 | 代码 fail-closed 正确，但绑定的 R2 报告是 blocked |
| RC2 | 12-15 前端 Studio/Experiment/Review 收口 | ✅ | 真实接通 |
| RC3 | 16-17 契约闭环 / deterministic acceptance | ✅ | 真实 |
| **Live G2** | **18-19 live acceptance / DoD 对账** | **🔴** | **R2 gate 未关闭；G2 PASS 不可复现；DoD #1/12/16 失效** |

---

## 5. 最终评级

| 维度 | 评级 | 说明 |
|---|---|---|
| 代码工程质量 | **A（优秀）** | 8 维度 7 个真实扎实、多处优于设计 |
| 测试质量 | **A** | golden 是 production-path 集成测试，精确计数 + 反伪造一致性断言 |
| 架构合规 | **A−** | 37 contracts/0 broken；仅低危技术债 |
| release evidence / G2 PASS | **FAIL** | R2 gate 实际 `configuration_blocked`；r3-report PASS 引用未提交报告；不可复现 |
| 诚实度 | **有损** | README/memory 声明"23/23 G2 PASS"与提交证据矛盾；DoD 矩阵引用幽灵哈希 |

### 直接回答三个审计问题

1. **有无偷工减料？** → 代码层基本没有（实现甚至比设计更严）。唯一的水分在 release evidence 层：用一份从未提交的 ready 报告声称 G2 PASS。
2. **有无和设计不一致？** → 几处合理偏离（Task 15 Step 4 N/A、r1_impact V1 NOT_EVALUATED、raw/processed 列共用）+ 几处低危技术债。最严重的不一致是 G2 状态声明：计划要求 Task 17 只能声明 "ENGINEERING COMPLETE / G2 BLOCKED"，当前却声明了 "G2 PASS"。
3. **是更优秀了还是忽略很多？** → 代码确实更优秀了。被忽略的是 R2 数据认证 gate 这个 release 前置——它客观 `certification_missing`，却被当成已关闭。

---

## 6. 建议（按优先级）

1. **🔴 纠正 G2 状态声明**：要么 (a) 重新跑 R2 live acceptance 产出真实 `status=ready` 报告 + 匹配 manifest，再重跑 r3 runner 生成可复现 r3-report；要么 (b) 诚实降级为 **"R3 ENGINEERING COMPLETE / G2 BLOCKED"**（提交证据实际支持的状态）。README/memory 的"23/23 PASS"必须修正。
2. **🟡 修正记忆**：`memory/r3-research-governance-progress.md` 末段（2026-08-04 G2 PASS）不准确，会误导后续会话。
3. **🟢 低危技术债**：重构 `analysis/_holdout.py` 内部循环（去 TYPE_CHECKING）、将 `ContentHash` 迁到中性模块、关注 800 行密度。

---

## 附录：审计证据索引

- R2 gate 矛盾：`artifacts/acceptance/r2-report.json`（`3084bc7c…`）、`artifacts/acceptance/r3-report.json`（`r2_evidence.report_hash=446ef1d5…`）、`artifacts/acceptance/r2-report.manifest.json`、`docs/evidence/r3/README.md:109,131`
- fail-closed reader：`packages/application/src/ditto_application/processes/experiments/r2_live_gate_evidence.py`
- runner：`apps/backend/src/ditto_apps/scripts/r3_research_acceptance.py:551-561`
- hard gate / 三层 binding：`packages/application/src/ditto_application/processes/strategy/promotion.py:88-190`
- 因子贡献真实路径：`packages/strategy/src/ditto_strategy/alpha/builtins/scoring.py:141-192`
- durable 幂等：`packages/application/src/ditto_application/mutation_idempotency.py`
- 128 调度器：`packages/application/tests/integration/test_r3_scheduler_capacity.py`
- API 契约：`docs/contracts/r3-v1-api-surface.json`、`apps/backend/tests/unit/api/test_r3_api_surface_contract_unit.py`
- 架构 allowance：`scripts/architecture/check_architecture_smells.py`、`apps/backend/tests/unit/architecture/test_capability_semantic_ownership_unit.py`
- 前端：`ditto-app/src/routes/research.tsx`、`ditto-app/src/features/{strategy,research}/`、`ditto-app/docs/review/r3-research-acceptance/live/`

---

## 附录 B：2026-08-04 G2 闭环尝试与新发现

> 在本审计之后，当日尝试用现有 live 数据根（`var/r3-task18-20260802/`，含已认证 metadata.sqlite + keyring 凭证）真正闭环 G2。结论：**R2 gate 真正可闭环且已闭环；G2 仍 BLOCKED，但阻断点从 R2 转移到黄金 lane 的新鲜复现。**

### B.1 R2 live Gate 现已闭环（DoD #1 解决）

- metadata.sqlite 实际**已含全部 19 个 dataset 认证**（`dataset_certification_reports`/`_events` 各 19 行，2026-08-02 15:44 写入）。先前 `configuration_blocked` 报告是**早 8 分钟生成**的过期产物。
- 用全绝对路径 env 重跑 `r2_data_acceptance --mode live`（`DITTO_DATA_ROOT` 指向 live-data）产出新鲜的 `status=ready` 报告（recoverability/idempotency/19-certified 全过）。**R2 gate（原 G2 阻断）已真正可复现地闭环。**

### B.2 新发现：live-acceptance runner 的 replay bug（原始 G2 evidence 受损的根因）

重跑过程中暴露 r2/r3 runner 的若干 **replay 鲁棒性缺陷**（这些正是原始 G2 evidence 被覆写/不可复现的工具层根因，应作为工程债修复）：

1. **r2 runner 相对路径 bug**：`write_live_evidence_bundle` 用 `output.relative_to(root)`，但 `--output` 等接受相对路径 → `relative_to` 对绝对 root 失败；`_live_recoverability` 的 backup/restore 原子写在相对路径下抛 `R2BackupError`。**全绝对路径可绕过**，但 runner 应 resolve 路径或拒绝相对路径。
2. **r2 runner db_path 接线**：`--sqlite-path` 只用作 backup 源；认证检查/pool 用 `settings.resolved_sqlite_path`（来自 `DITTO_DATA_ROOT`）。不设该 env → 容器打开默认 `data/metadata/metadata.sqlite`（旧库）。runner 应显式接线或文档化该 env 依赖。
3. **r3 黄金 lane 不新鲜复现**：在当前数据上 stock/etf lane 在 ~210s 早期断言失败（疑似 golden 期望相对 Aug 3 后新数据的漂移）、governance lane 缺 `lanes/stock/current.json` precondition、backup lane 报 path 错误。live-acceptance 工具链不具备跨数据变化的 replay 鲁棒性。

### B.3 技术债正确修法（本轮评估，未强行实施以避免回归）

- **#1 `analysis/_holdout.py` TYPE_CHECKING 循环**：Protocol 路会与 `_facts.py`/`_review_packet_store.py` 的 `_reader: SQLiteExperimentReader` 声明在 `SQLiteExperimentWriter` 多继承处产生 `reportIncompatibleVariableOverride`。**正确修法**：把 `holdout_claim_from_row`（+其 `_integrity` 依赖）抽到叶子模块 `_holdout_claim_row.py`，让 `reader` 从叶子导入（断 reader→_holdout 循环），则 `_holdout` 可正常 import `SQLiteExperimentReader`、移除 TYPE_CHECKING。
- **#2 `ContentHash` 跨包 re-export**（定义在 analysis，`scheduler_store` re-export 给 application，~20 文件消费）：**正确修法**是把 `ContentHash` 迁到 `ditto_kernel`（或中性 contract 模块），analysis 与 application 都从 kernel 导入，消除 re-export 与 `PRODUCTION_ANALYSIS_WIRING_ALLOWANCES` 该条。属 ~20 文件重构，低危，建议单独 PR。

两项均为低危、非阻断；本轮已交付的 G2 闭环价值（R2 gate 解决）不应被侵入式重构的回归风险抵消，故记录为追踪项。

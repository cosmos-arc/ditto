# 近期 PR 审查与修复链审计

日期：2026-09-26。只读审计 GitHub 与相关提交，不修改代码、CI、规则或 GitHub 状态，不运行全套测试。

## 结论

近期审查回合确实多，但证据不支持把主因概括为“CR 角度太苛刻”。抽查发现了真实的 PIT、账本并发、身份、消费者兼容与生产装配问题；也发现了修复引入的新故障、同一不变量只补一个路径导致后续继续发现，以及被审查发现推动的共享基础设施扩展。这是实现完整性、测试代表性、修复策略和审查收敛方式共同作用的问题。

最明显的模式是：局部实现及测试通过，PR 前两轴审查报告无剩余问题；后续审查沿真实输入、共享调用者或时间边界发现缺口；修复仍围绕单条发现；下一轮再发现另一条路径或刚引入的回归。减少回合应从一次解释并闭合一个根因入手，不能靠降低 PIT/资金/审批门，也不能用反复全量“无发现”代替可复核的收敛条件。

本报告只对抽查项判断代码机制，不推算全样本有效率、误报率、实现/审查责任百分比。P1/P2 是审查者的标签，不是本报告判定。

## 证据、术语与计数边界

样本是较长修复链 #308、#307、#306、#304、#302、#288，另抽查快速合并的 #301、#300、#299。它是目的性样本，不代表全仓统计分布。GitHub 原始响应存于本机临时目录 `/tmp/ditto-review-ci-20260926/reviews/`；每个 PR 包含 `pr.json`、`reviews.json`、`review-comments.json`、`timeline.json`、`diff.diff`、`readable.txt`。相关 Issue 与选定修复提交的 API 响应也保存在该目录。临时运行输出不纳入长期仓库证据。

本报告采用以下口径：

- **正式 review 对象**：GitHub `/pulls/{n}/reviews` 的一条对象。作者回复某个 finding 也会产生一个空正文 `COMMENTED` review，不能直接计作一轮重新审查。
- **自动 CR 回合下限**：`chatgpt-codex-connector[bot]` 提交正式 review 的不同 `commit_id` 数。同一 SHA 多条 finding 只算一回合；同一 SHA 可能被触发多次，因此这是可复现的下限口径。
- **finding**：非回复的独立审查意见。inline finding 与 review 正文中的实质 finding 合并计数；作者的 `Fixed in ...` 回复不另算 finding。
- **PR 前修复**：提交时间早于 PR `createdAt`。这只是提交时间分类，不能推导用了几轮本地审查。
- **后轮新发现**：相对首个被自动 review 的 SHA 后，审查首次报告的缺陷。它可能早已存在，也可能是修复引入；不能将“新 SHA 上发现”当作“该 SHA 引入”。
- **不完整修复**：旧根因仍在另一入口、错误路径或消费者中存在，有新的可达失败路径；与重复原话而没有新证据的旧发现不同。
- **修复引入回归**：能定位到修复改变了某个生产行为，随后触发原本不发生的错误。
- **要求扩展**：原规格未明确而审查引入的行为/政策。需要与既有共享不变量的必要修复分开，不因改到了共享模块就自动判越界。

PR 正文的“Standards / Spec 已通过”属于作者对本地工作的报告。GitHub API 无法独立验证本地审查是否确实执行、覆盖了哪些源码、在哪个固定 SHA、是否有未公开发现。本报告没有读取完整本地会话，不能据此计算本地审查轮次、独立性、漏检率或人工实际工时；主报告可以另引用明确的本地会话证据。

## 样本快照

下表 `代码量` 是最终 PR diff 的新增/删除行数，包含生成物与测试，不是手写业务代码量，也不是累计返工量。#308 在快照时仍打开，结论有右截断；快照 HEAD 为 `f5019502a67778da95ce85f935e9d25f64bbe6d2`。

| PR | 状态 | 文件/代码量 | PR 前/后提交 | 正式 review 对象 | 自动 CR 回合下限 | 独立 finding |
|---|---|---:|---:|---:|---:|---:|
| [#288](https://github.com/cosmos-arc/ditto/pull/288) 历史证券池 | merged | 38 / +2894 −175 | 2 / 1 | 3 | 1 | 2 |
| [#299](https://github.com/cosmos-arc/ditto/pull/299) | merged | 21 / +1550 −46 | 1 / 0 | 0 | 0 | 0 |
| [#300](https://github.com/cosmos-arc/ditto/pull/300) ETF 比较 | merged | 22 / +2291 −9 | 3 / 0 | 1 | 1 | 3 |
| [#301](https://github.com/cosmos-arc/ditto/pull/301) 配置保存 | merged | 19 / +2090 −11 | 2 / 0 | 1 | 1 | 1 |
| [#302](https://github.com/cosmos-arc/ditto/pull/302) 配置 review | merged | 17 / +1168 −19 | 2 / 7 | 17 | 7 | 10 |
| [#304](https://github.com/cosmos-arc/ditto/pull/304) Paper 执行 | merged | 43 / +4270 −115 | 2 / 16 | 44 | 16 | 29 |
| [#306](https://github.com/cosmos-arc/ditto/pull/306) 历史复盘 | merged | 38 / +2633 −82 | 4 / 8 | 19 | 7 | 12 |
| [#307](https://github.com/cosmos-arc/ditto/pull/307) 跟踪评价 | merged | 39 / +2942 −148 | 2 / 29 | 67 | 27 | 40 |
| [#308](https://github.com/cosmos-arc/ditto/pull/308) 图表来源/时间 | open | 33 / +3978 −345 | 4 / 33 | 50 | 21 | 30 |

六个重点 PR 有 79 个自动 CR 回合下限、123 条独立 finding；首轮 13 条，后轮 110 条。这表示问题逐轮才被暴露，不表示 110 条都由修复引入，也不表示审查故意拆分报告。#304 有一条写在正式 review 正文中的账本 revision finding，不能只统计 inline 的 28 条而漏掉它。

快速合并不能视为质量良好的对照：#300 于 2026-09-23 10:03:52 UTC 合并，三条 finding 在 10:11:16 UTC 到达；#301 于 13:49:40 UTC 合并，一条 finding 在 13:51:36 UTC 到达。#299 的零正式 review 只能说明没有该类 GitHub 证据，不能证明无缺陷。三者与较长 PR 的风险、规模、审查暴露时长不同，不应比较“轮数少 = 质量高”。

## 逐轮案例

### 1. #302：一次幂等修复未闭合全部入口，随后又产生契约守卫回归

初始实现 `a389fde7` 之前已做一次 PR 前修复；PR 正文报告原子性及响应身份问题已修复，并称本地 `task check`、完整测试与两轴审查通过。

| 被审 SHA → 修复 SHA | 发现及静态核对 | 本报告分类 |
|---|---|---|
| `a389fde7` → `0c88162c` | 新 artifact enum 会被旧 reader 在过滤前反序列化；并发同 key 请求 CAS loser 返回 409，未重放已经落盘的相同结果 | 持久化兼容与并发重试的实质缺陷 |
| `0c88162c` → `22c1eb24` | receipt ID 按 action 分开，submit/approve 使用同一 key 可以创建不同 fence | 初始幂等不变量未整体闭合；不是前条 CAS finding 的简单重复 |
| `22c1eb24` → `2203ff42` | 仍手写 key 校验且持久化原 key，没有走共享 `build_mutation_idempotency` | 同一边界规则的另一缺口，原本即可发现 |
| `79bf8344` → `4647141b` | 共享校验已使用，但 API blanket handler 把其 `IDEMPOTENCY_KEY_INVALID` 改成 `ETF_ALLOCATION_INVALID` | 前次修复未沿异常到 HTTP 消费者闭合 |
| `4647141b` → `aac3f2b5` | `paper_status` 从旧值域扩为 review 状态，旧 v1 adapter 明确拒绝新值 | 可核对的语义契约问题；“/api/v1 compatible additions only”已是规则，不是本次审查新设要求 |
| `aac3f2b5` → `ee599d5e` | 添加 `review_status` 时删掉 Paper 状态检查；新 adapter 接受声称 Paper authority 的畸形响应 | 修复引入的信任边界回归 |

可溯源原始讨论：[并发重放](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4085466944)、[跨 action key](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4088529240)、[共享校验](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4088903493)、[错误码](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4089233016)、[v1 值域](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4089359363)、[修复后 Paper guard](https://github.com/cosmos-arc/ditto/pull/302#discussion_r4089607070)。

契约审查有实质依据，但严重性应分别评估：错误码、用户误点终态 reject、潜在畸形响应，与账本并发或错误审批身份不是同一种风险。P1/P2 不应替代风险判断。代码里的字符串类型使 OpenAPI diff 难以发现运行时值域变化，这是测试与契约表达的盲区，而不是 CI 绿灯证明审核意见无效。

这里的最低成本改进是：review mutation 开始时复用已有的完整幂等边界，把并发 replay、跨 action 冲突、错误映射、receipt 持久化和 UI cache 更新作为一个端到端变更审核；不需要新建幂等平台。

### 2. #304：真实生产输入与装配未被最初验收代表；修复一个身份又破坏消费者

[Issue #266](https://github.com/cosmos-arc/ditto/issues/266) 要求进入既有受控 Paper 流程、真实 UI/API 恢复以及重试不重复副作用。初始 `05d1fceb` 的 PR 报告广泛的本地验证与两轴审查通过，但后续 finding 揭示了至少三类不同问题。

**账本可知性与并发是一个共享根因，必须修复共享实现。** 初轮指出 ledger 未带执行 cutoff 以及检查余额和 append 不原子；`fa34d52a` 添加 `recorded_through` 与 CAS。不过其余额从 cutoff-visible `events` 计算，guard 却 hash `full_stream`，因此隐藏 debit 仍可与旧余额一起通过 guard；后续再次出现相应证据。最终需要以一致的 stream 定义余额、revision 和 append，并在 CAS 输掉时处理相同请求已落盘的恢复。它影响的是 Paper 钱/账本边界，修改 account journal 和共同执行入口是必要的根因修复，不能仅因触及共享模块称为需求蔓延。[初轮 cutoff](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4091384364)、[原子 append](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4091384372)、[隐藏 revision 的后续路径](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4092775685)。

**记录式夹具结构与普通 provider 保留载荷不一致。** `fa34d52a` 上 `load_etf_daily` 必须含 `instrument_id`，但普通 Tushare adapter 是 `source_ticker`，provider artifact 在 DataWriter 添加内部 ID 之前即已保留。这个真实输入会被拒绝；类似地，普通 ETF 日线没有测试所假设的涨跌停字段，需经既有规则推导。这里不是要求等待供应商数据采购，而是本地隔离测试应该走普通摄取的真实 schema，不能只造一个业务代码想要的富化 DataFrame。[ticker-only 载荷](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4091882493)、[规则推导](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4091882504)。

**确定的修复引入回归。** `58492f24` 为跨账户隔离将 run ID 改为加上 account 后缀，handoff/execution 两个调用者使用了新 helper，但 `SignalPackagePublisher.publish()` 仍只允许旧 exact batch key。于是所有走真实 publisher 的 handoff 会抛 `AppProcessError`。下一轮 `5279a107` 才改消费者校验。问题来自修复，没有证据表明是无效 CR；同时说明所谓集成验收没有覆盖本次改动影响的真实 publisher。[finding](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4093599163)、[引入提交](https://github.com/cosmos-arc/ditto/commit/58492f24)、[补齐提交](https://github.com/cosmos-arc/ditto/commit/5279a107)。

**数量计算的行为选择不够明确，但反例具有实质业务影响。** 先卖后买的 rotation 中，卖出所得已在执行账本，却仍用 signal cash 限额，买入被拒绝；随后只改 cash 又遗漏执行 holding 差异和执行日费率；再遗漏执行价上涨后的最大可买 lot。后续修复选择保留 D-day target/NAV，使用 D+1 cash/规则，holding 偏离则 fail closed。这些不全是新引入缺陷，多数是冻结信号与动态执行状态的分界没有一次定义并验证。[rotation cash](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4094007797)、[holding 变化](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4094160253)、[执行价成本](https://github.com/cosmos-arc/ditto/pull/304#discussion_r4094337445)。

这里也有需要明确的产品取舍：涨价导致资金不足时是“拒绝整条意图”还是“买最大可负担 lot”。审查指出 partial rotation 的后果是有证据的；但具体选择不应永远由下一条 CR 临时决定。Issue 对大方向有约束，未把每个动态 sizing 选择写成明确例子。应在修复前把 D/D+1 状态分工和一个卖后买反例确认下来，而非补齐完整交易系统规格。

### 3. #306：PIT 修复深入共享 metadata 是必要的，但最初只加时间过滤不够

初轮 ledger fallback 没带 `recorded_through`，URL 保存 offset-less `datetime-local`，会使同一复盘在纠正后或不同时区展示不同 evidence。后续 cache key 未含 `origin_version_id`，切目标仍可显示旧目标结果。这是可达的缓存/回放错误，不是格式偏好。[fallback](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4096983784)、[URL 时区](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4096983801)、[cache key](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4099496931)。

ticker lookup 先只按 effective date，没有 knowledge cutoff；修复加 `created_at` 后，旧 mapping 的 `effective_to` 仍可在 cutoff 后被原地改变，因此历史区间不能回放。再往下，`technical_analysis_source._instrument_rows` 用 ID 或 ticker 的 OR，身份不一致时可能混入另一证券。这里的后轮意见给出不同的可达路径，不能将其归为“同一问题反复挑”。修复 lookup/history/共享 row filter 是为当前估值调用闭合根因，不是另设产品需求。[cutoff lookup](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4099563179)、[原地 mutation](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4099742830)、[双身份 OR](https://github.com/cosmos-arc/ditto/pull/306#discussion_r4099839948)。

但它也说明 Issue 的“精确 saved version + cutoff + price snapshot”验收必须沿 metadata→payload filtering→价格→API→UI 这一整条链解释。只在 query 顶端新增时间 guard，或者只在 UI 隐藏某个错误，不能独立证明 PIT 不变量闭合。

### 4. #307：日历成为共享修订引擎，存在真实回归和边界扩张

[Issue #265](https://github.com/cosmos-arc/ditto/issues/265) 的主要切片是 252 日 NAV/index 总回报评价；初始 `e6b2f84a` 仍从可变当前 calendar 获取 tracking/liquidity sessions。后续把 retained 日历纳入 PIT 确有既有规则依据，但最后修复链扩大到多 shard overlap、可知观察顺序、coverage、ingestion checkpoint、Paper settlement 与旧 candidate 消费者。

**必要范围与新增要求的分界：** cutoff-visible sessions、真正参与窗口的 shard authority、同一历史请求在 correction 后不改变，是当前统计结果成立所必需；共享 calendar resolver 被 Paper 使用后，需要检查 Paper 的语义回归。反之，不应借一次指标需求顺手要求全面替换所有非消费者、新增无关数据平台或实时运营验收。本样本不能证明发生了后一种任意扩张；能证明“共享模块越改越广，却没有一次提前覆盖调用者”。

**明确的回归链。** 初始 candidate 查询有独立 20-day liquidity 与 253-session tracking 窗口。新增 strict calendar gate 后，calendar 缺失会让全部 candidate 以及仅用于保存 allocation 的调用者失败。`5853a633` 将 calendar failure 降级为 tracking reason，但其 `None`/`observed_since=asof` 又丢掉实际有效的近 20-day liquidity，直到 `f0553d11` 才恢复独立窗口。三条意见不是同一个 finding 重复，也不是 UI 偏好；后一条可定位到降级修复的行为。[非 tracking 消费者](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4105470426)、[独立流动性窗口](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4107331985)、[补齐提交](https://github.com/cosmos-arc/ditto/commit/f0553d11)。

**观察历史的修复循环。** A(t1)→B(t2)→A(t3) 的 revision 需求先通过更新 snapshot `created_at` 处理，破坏“首次可见”语义；随后换成 `last_observed_at` 又无法保留 A(t3)→A(t5) 时 t4 的回放顺序。最终 `84a12c80` 用观察事件历史保留首次时间和各次顺序。这是同一时点模型没有先完整定下来导致的方案往返，后轮提出的新反例具有实质性，不应标成重复无效。[首次时间](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4105035555)、[全部观察时间](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4105659699)、[最终修复](https://github.com/cosmos-arc/ditto/commit/84a12c80)。

**共享 Paper 消费者被新 overlay 改变。** 逐日 union/overlay 使 trade day 可以来自 primary，后续 settlement days 来自 secondary。此前选到一个不覆盖起点的次源会拒绝，现在却构造无人提供的 hybrid calendar。审查要求同一 consumed window 的 authority；修改 Paper resolver 是此次共享改变的必要回归防护。[混源 settlement](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4106195606)。

**IO 性能意见应与基准区分。** 末轮指出所有 cutoff-visible 年份的载荷都先读再判断是否贡献 window，既会因不相关年份坏载荷阻断当前请求，也会随着历史增长增加 IO。源码支持这条路径，但本审计没有 benchmark，不能把“无界扫描”直接当成测得的秒数。[无贡献载荷](https://github.com/cosmos-arc/ditto/pull/307#discussion_r4107532561)。


### 5. #308：相同 identity/missing 语义分散补丁；全面补查又带来性能回归

[Issue #279](https://github.com/cosmos-arc/ditto/issues/279) 明确实际 calendar、partial/stale、来源与导出身份。初轮的停牌、退市、有效日期 ticker 属于真实业务边界；不过 Issue 没列每个组合。后续生命周期 clipping、empty evidence 与修订 coverage 被逐步补齐，说明一张表里的“缺数据”在代码中混合了多种不同状态。

一条可追溯链是：

1. `70eb3e43` 上，mapping lookup 返回 `None`，Polars filter 直接丢 bar，UI 把身份未知解释为 missing price。`d752f678` 增加 ticker guard，`07d0410e` 又把 guard 放到 shard scoping。
2. `6ab6aec1` 上仍有 no-row 路径：市场全量 shard 没有该日 bar，resolver 根本不请求该日 ticker。新的 finding 用没有价格行的日期证明 identity 仍未验证；`c0dbec2f` 增加每个 expected session 检查，`42aa705f` 再补 empty auxiliary 路径。
3. 每 session 调一次 SQLite mapping，价格/因子/停牌各重复执行；下一轮指出长范围性能路径。`2a73b9fb`、`a7e2d406` 改成批量读取 effective intervals。

[初次 missing identity](https://github.com/cosmos-arc/ditto/pull/308#discussion_r4110484433)、[no-row 新证据](https://github.com/cosmos-arc/ditto/pull/308#discussion_r4110557549)、[批量性能](https://github.com/cosmos-arc/ditto/pull/308#discussion_r4110597645)。本报告静态核对了上述引入/修复 diff；没有实测“10 年 7500 SQL”的时延。性能意见里的数量是按三个数据集和交易日推算的量级。

第一、第二步属于同一不变量没有所有路径闭合；第三步是补强验证引入新的复杂度/性能问题。它们都不能因为同样提 ticker 而统称重复 CR。

另一个例子是 lifecycle 完全不相交时应返回 explicit empty chart。新 empty 分支加了，但旧 `assert_bars_allowed` 在 clipping 前运行，对默认 experimental stock_daily 仍提前拒绝。`c153fbb5` 才将 maturity gate 移到需读 bar 的分支。它是在新增生命周期行为后遗漏旧 gate 的交互，不能简化成“审核突然发明 empty requirement”。[finding](https://github.com/cosmos-arc/ditto/pull/308#discussion_r4110669573)、[修复与反例测试](https://github.com/cosmos-arc/ditto/commit/c153fbb5)。

## 审查质量的判断

抽查说明审查确实在发现较高价值问题：普通 provider payload 无法执行、跨 account 隔离修复使真实 publisher 全部拒绝、hidden ledger debit 与 CAS、错误历史 ticker、cache identity、观察时间回放等。它们有定位、路径、影响和修复链，不是只有抽象的“可能不安全”。

同时，审核与流程有三个需要改进的地方：

1. **报告未按根因收敛。** 同一 mutation identity、calendar authority、D/D+1 sizing、chart missing identity 分散到多轮。不能认定 bot 有意少报，但一条条消费 finding 的工作方式会放大随机覆盖的影响。首次命中核心不变量时，应先核对整个调用链和兄弟消费者，而不是立即修那一行并重跑全部验证。
2. **标签和判定依据混在一起。** 真实 bug、语义取舍、可达性未证实的畸形响应防护、静态性能估计应分别写清。审查可以提建议，但 blocking finding 应说明它违背哪个已确认需求/当前不变量，给触发输入和可观察错误；未确认的行为选择回到 Issue，不通过修改实现默认接受。
3. **没有清晰区分首次检查、修复检查与终态检查。** 每个新 SHA 全量寻找新问题，可能持续把既有 latent issue、修复引入问题及新范围发现混成一个无期限门禁。修复检查应优先确认原 finding 是否闭合和改动影响；新发现仍可报告，但标清引入 SHA、是否同根因、风险与本批相关性。不能因为达到轮数上限就合并有证据的资金/PIT bug。

没有统计支持“误报太多是主因”；也没有证据支持“实现者单独承担全部责任”。当前仓库 [testing.md](../engineering/testing.md) 已要求可达代码、测试证据、影响与修复方向，也明确不要求固定 reviewer 数/评分。问题更像执行未将这些规则落实成可审查证据。

## 时间解释

自动 review 的被审 commit 时间到 `submitted_at` 的中位差：#302 13.8 分钟、#304 11.5、#306 14.6、#307 12.4、#308 11.3。该差值混合了提交后本地 hook、上传、触发/排队和 review 本身，不能当作云端审核实际运行时间。#307 首条正式自动 finding 为 2026-09-25 03:56:30 UTC，最后一条为 18:35:37；#308 当前快照从 01:49:15 到 08:24:59，21 个被 review 的 SHA。

同理，#302 首条 finding 到下一次修复跨了约 6 小时，#306 部分修复跨夜；其中可能有暂停/休息/其他工作，不能称为主动修复耗时。PR 创建到合并也包含作者等待和维护者决策。CI 测量应另按 run/job/start/end、attempt、SHA 与 concurrency 分解，不用上述数字替代。

## 建议：先改工作方式，再判断是否需要工具

- **第一次有效发现触及核心不变量时，暂停逐条补丁循环。** 用现有 Issue 留一个短根因记录：失败输入、当前权威实现、受影响消费者、选定修复、一个最小反例。mutation identity、calendar 和 D/D+1 不各造新框架。
- **修复前搜全部调用者，修复后验证真实 seam。** `run_id` 变化检查 publisher，ledger guard 检查 journal transaction，mapping 变化检查 metadata history→row filter，calendar overlay 检查 tracking/liquidity/Paper，生产 payload 检查保留字节而非富化夹具。
- **以一张小场景表补齐含混语义。** 至少区分冻结 target 与实时 cash/holding；首次可见与重复观察；无交易/停牌/缺价格/身份未知；tracking 不可算与 candidate 仍可显示。对实际遇到的选择确认即可，不建立穷举政策大全。
- **修复回合优先查修复与受影响路径。** 正式审查记录固定 base/head；新 finding 标“旧代码首次漏检 / 不完整修复 / 本次引入 / 未确认要求 / 需证明”。没有触发输入或当前规则依据的意见不直接驱动改码。
- **用少量强反例替换重复的大量成功声明。** 一次真实 publisher handoff、ordinary retained ticker-only payload、同账户并发 append、A→B→A→A 的 cutoff replay、无 row 的 mapping gap，比再报一遍全库绿色更能预防这些回归。已有对应测试尽量复用。
- **全量验证安排与风险匹配。** 本仓当前规则仍要求跨包、contract、架构或工具链变更完整 `task check`；不能在本次研究中擅自改门或绕过 hook。若要缩短每轮耗时，先用真实 CI/hook 时序核查重复执行和关键路径，再提出具体可审查调整。降低正式质量合同需要另作明确决定。

报告没有据此创建 ADR 或把提议写成现行规则。根因分类是分析术语；只有用户确认难以逆转的流程取舍后，才应按 [knowledge-lifecycle](../engineering/knowledge-lifecycle.md) 将决定写入 Issue 或必要 ADR。

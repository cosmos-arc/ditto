# #709 / #710 当前候选验收

**研究未通过；Paper 历史执行链通过，但当前发布资格未通过。**
执行代码为 `7696d411d5404acb4fd22406d64cb408782ad16e`；后续证据提交只整理报告和历史清单。
完整代码树、锁文件、配置及辅助脚本身份见 [identity-and-validation.json](identity-and-validation.json)。
没有连接券商、真实下单、发布或激活生产策略。原始数据只读，账户与运行状态均在新建隔离根。

## #709：停在冻结前，不能写成 preflight / 回测通过

[research-assessment.json](research-assessment.json) 保存实际数据库中的两份 v1 策略及校验过的 spec hash。
[historical-source-inventory.json](historical-source-inventory.json) 保存实际留存 payload 的字段、行数、快照与观察时间。

| 依赖 | 股票选股 | ETF 行业轮动 |
|---|---|---|
| 策略 / 池声明 | `seed_stock_selection_rotation` / `csi_a_share` | `seed_etf_industry_rotation` / `csi_etf_broad` |
| 显式 required datasets | stock_daily、adj_factor、balance_sheet、income_statement | etf_daily |
| 信号 | quality_roe、value_pe、momentum_1m | momentum_1m、reversal_1w、volatility_factor |
| 参数 | lookback 252，月频 top 20 | lookback 252、vol_window 60，月频 top 5 |
| 成本 / 基准 | commission 0.001、slippage 10bps / 000300.SH | commission 0.0003、slippage 5bps / 000300.SH |
| 最早本地主名册观察 | 2026-10-03 14:54:11.722076 UTC | 2026-10-03 14:56:07.751340 UTC |

显式数据集声明不等于全部实际依赖：历史名册、上市/退市/旧码、成员/停复牌/ST、分类、
估值/基本面、交易日历、基准、逐日复权与交易规则仍须沿现有投影和版本选择验真。
两条 lane 的既有研究切片使用 **15:00 UTC**，不统一改成其他时刻。
两类标的都要求逐日 adj_factor；股票成交日还消费真实涨跌停价，ETF 保留既有价格带近似。
warmup 应由实际编译表达式的最大回看和各标的合资格日历推导，不能把参数 252 直接充当合资格月数；本次尚未生成认证 warmup。

本地快照重放的完整连续 eligible 月数**上界为 0**：首次观察位于十月月中，十一月尚未结束。
这尚未扣除单标的缺口和 warmup，并不证明十月三日后的每一天已经覆盖。
因此 <37 月规则已经不满足；37–95 月仅 research-only，≥96 月也只证明长度资格。
没有把 96 月改成所有普通回测的门槛，也没有指定一个近期窗口凑 ready。

[research-prefreeze.json](research-prefreeze.json) 记录当前代码的实际调用：
`r3_live_planning_builder.main` 在股票与 ETF 上分别拒绝 `stock_basic`、`etf_basic` 的历史覆盖。
旧 builder 自带 `2015-02-01..2026-07-31` 窗口；它不是本次依据 payload 认证出的可用区间。
因此 **preflight 未到达，freeze / launch / scheduler / factory / feed 未执行**。

历史信息重建单独记为 **NOT_PROVEN**：主名册留存响应缺少可证明历史公开/修订时刻的原始证据，
ETF daily 响应也没有停复牌状态。没有把晚回填伪装成早期观察，也不据此否定一切可能的历史重建。
真实除权/分红、上市/退市/更名、停复牌、成员变化、迟到修订与未来哨兵矩阵，以及新增数据后旧冻结结果不变，
均待来源与依赖合资格后执行。自动 PIT 测试通过不能代替这些真实验收。
股票 Paper 的十个固定标的、ETF Paper 的 510300.SH 均不证明全市场研究资格。
8 月 5 日 R3 与 9 月 Backtest 的既有成功记录保留，未改写为本候选通过。

## #710：当前代码的历史执行与重启

| 消费链 | 本次结果 | 范围 |
|---|---|---|
| 通用股票 Paper | 10 单：9 成交、1 涨停拒单；账本 10 条；EOD balanced | [stock-paper.json](stock-paper.json)，真实 10 月 21 日留存行情/限价，11 月 7 日事后模拟 |
| governed ETF | 1 成交；opening + buy 共 2 条账本；EOD balanced | [governed-etf.json](governed-etf.json)，510300.SH，11 月 5 日信号 / 11 月 6 日交易 |
| 20 日加速 | 10 月 12 日至 11 月 6 日，20 个真实历史交易日；20/20 balanced；HMAC 链校验通过 | [accelerated-result.json](accelerated-result.json)，新隔离根、真实留存响应重放 |
| 独立进程恢复 | 股票 10、ETF 2、加速 21 条账本在恢复/重放前后不变；22 个 session 使用新 EOD 键重算且全部 balanced | [process-restart.json](process-restart.json) |
| 复用已完成根 | `verified_existing`，`newly_recorded_days=0` | [accelerated-identity.json](accelerated-identity.json)，不记作新执行通过 |

股票脚本删除禁止外部传入的账户事实参数，账户持仓、可卖数量与资金由当前账本推导；未放宽守卫。
原始源目录以 SQLite 只读事务读取，两个快照的元数据复制到内存后经 `SnapshotReadService` 验证
内容身份、COMPLETE 记录、payload 校验和与 schema，再使用真实 retained payload。
完整历史 OHLC 的 `execution_at` 是本次运行时间，不声称执行日 09:30 已知。

ETF 使用现有 allocation save → submit → approve → Paper authorize → handoff → execute 入口；
授权仅作用于本票的隔离验收账户。报告绑定 version、authorization、signal/intent、交易日、
basic/daily/reference 快照、execution、ledger event、EOD 和代码 SHA。
隔离账户的 opening clock 是明确标注的历史模拟时钟，来源观察时间未回填。

独立进程验证在原运行进程退出后重新打开数据库，恢复持久化执行，按既有生命周期恢复/暂停 session，
重复请求返回原执行且不增加账本，并以新键对账。脚本中的同进程 close/reopen 只作为额外检查。
额外账本事实的反向对账拒绝、未入账守卫、账户事实注入拒绝与 CAS 等反例由现有针对性测试覆盖；
本次真实输入不声称穷尽这些反例。

20 日数据最初于 `6bb914a1` 在线取得并完成一次真实源加速运行；当前代码重新在线读取时，
Tushare 两次返回 `SourceAuthenticationError`。于是当前代码使用本轮已留存的同一真实响应完成全新根重放，
原始响应 SHA-256、获取时刻、当前执行身份见 [accelerated-identity.json](accelerated-identity.json)。
没有合成行情，也没有把留存重放说成新的在线抓取。

**当前发布资格仍未通过**：既有加速合同要求 current live-day anchor，而本次引用的是
2026-09-02 归档锚点。原始签名报告中的 `qualifies_as_release_acceptance=true` 是既有合同字段，
不能越过本报告的当前资格判定。自然运行不在本次声明中，也没有新增自然 20 日等待门。
补齐当前适用的 live-day anchor、恢复在线认证后，才能完成该部分放行复验。
备份/完整恢复按维护者决定 **DEFERRED**；普通进程重启已验，旧恢复结果不充当当前恢复证明。

## 清单修复、检查与复核

先实际运行 `scripts/evidence/paper_five_day_preacceptance.py`，确认新 [paper-five-day.json](paper-five-day.json)
通过且语义 evidence_hash 与受影响叶子一致，再修复旧 Q4 叶子及 OPS-10 上层引用。
[legacy-revalidation.json](legacy-revalidation.json) 记录前后 hash；[legacy/](legacy/) 保留修改前的原始清单。
旧 Q0–Q5 均经现有 `verify_gate_manifest` 递归验证，叶子数量依次为 5、11、5、6、15、20；
OPS-10 顶层 22/22 一致。这是历史内容维护，原日期、旧代码、历史 `passed` / `restore_verified` 不等于当前放行。

当前 [Q3.json](Q3.json) 与 [Q4.json](Q4.json) 复用现有 manifest 格式，并保留各自 blocker。
在仓库根用下述只读命令复核；HMAC 密钥与数据库只留在本地隔离根，不提交。
公开文件可复核摘要链，HMAC 的密码学验证由持有本地密钥的现有 verifier 完成，见独立进程回执。

```bash
uv run --no-sync python - <<'PY'
from pathlib import Path
from ditto_apps.operations.evidence_manifest import verify_gate_manifest
root = Path('docs/evidence')
for name in ('Q3', 'Q4'):
    manifest = verify_gate_manifest(root, root / 'current-acceptance-20261107' / f'{name}.json')
    print(name, manifest.status, len(manifest.artifacts))
for n in range(6):
    verify_gate_manifest(root, root / 'personal-workstation/manifests' / f'Q{n}.json')
PY
```

验证：`task verify-push` 完整门禁通过（Python 16,771 passed / 17 skipped；Web 1,928 passed）；
另有研究针对性 247、Paper 针对性 25、PIT 666 项通过。修复后 8 项针对性测试、类型与 Ruff 通过。
规范/需求两轴首审发现同一快照验证缺口；修复后的规范复审和原始篡改反例复验均已通过。
这些代码证据与真实来源/运行资格分别记录；#709、#710 均不自动关闭，PR 留待维护者合并。

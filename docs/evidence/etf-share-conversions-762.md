# ETF 份额折算进入份额与停复牌

对应 [#762](https://github.com/cosmos-arc/ditto/issues/762)，属于 [#734](https://github.com/cosmos-arc/ditto/issues/734)。本项在普通历史运行中按发行人公告声明的 ETF 份额折算（拆分/合并）重标定份额与成本，并给零成交日建立停牌语义。不照搬股票送转规则：折算无现金、无税、无独立上市日，份额只重标定不新增。

## 事件来源与可知时间

外部数据源没有 ETF 折算事件接口（tushare `fund_div` 明确不含折算；`fund_share` 是份额结果序列，不是事件声明）。维护者确认的公告声明是唯一权威口径：`config/default/etf_share_conversions.json`（`Source.CONFIG` 合法来源模式，仿 `etf_reference`，#408），每条声明 `source_ticker/ratio/announcement_date/effective_date/basis/rounding_note`，加载器（`packages/data/src/ditto_data/sources/etf_share_conversions.py`）要求 `ratio>0` 且 `≠1`、公告日先于生效日、同 `(ticker, effective_date)` 二次声明拒绝，文件不可读或结构非法 fail closed。

声明进入运行的路径与参考事实一致：声明文件经留存快照（`source=config`）被 `FrozenHistoryProvider.freeze_share_conversions` 按请求 `frozen_at` 选每标的最新声明收据，读窗口内 `effective_date` 事件为 `ShareConversion`（记快照身份与公告日），进入请求的冻结来源清单。**本声明集不做全域完整性声明**：无折算声明快照的运行看不到任何折算事件，真实折算日由执行层因子跳变守卫 fail-closed 拦住（`corporate action requires cash/share accounting`）；本地声明收据的留存不证明公告当年已可知。截至本票，声明文件→留存快照的日常摄取任务未接入夜间链（fixture 与维护者手动留存先行），真实运行补齐见下「未完成项」。

份额折算不能由 `fund_adj` 因子反推（#758 红线）。因子只做一致性验证：折算日 `current ≈ previous × ratio`，容差 `fund_adj` 四位小数来源精度 `quantum×(1+ratio)/2`（159941 为 1.0→4.0 精确命中）。除权参考价硬校验 `pre_close == round_to_tick(前收/ratio, 0.001)`，不一致即 `unverified ETF conversion reference` 拒绝。现金分红与折算同日叠加的复合参考价未验证，维持拒绝。

## 账本语义

- 生效日开盘前（与分红 settle 同一时点）`quantity × ratio`、`available_quantity` 同乘、总成本不变、`average_cost` 重摊；无现金无税，当日净资产不变（同日价格 ÷ratio）。T+1 冻结份额队列同乘，按新份额规模解冻。
- 新 entry kind `share_conversion`（数量为变动量，amount 恒 0）；事件在生效日只消耗一次——生效日无持仓也记零数量 entry，之后买入的已是折算后份额。identity `(instrument_id, effective_date)` 冲突拒绝。
- 份额换算必须整数；非整数换算 `raise fractional conversion requires evidence`（本票只实现整倍语义，公告声明取整规则前不静默取整）。
- 成交匹配（FIFO/FLAT_TO_FLAT）同日重标定开仓数量与每股成本、保留总成本；`applied_conversions` 幂等集随 checkpoint 往返，加字段使升级前 checkpoint 按键缺失/哈希漂移响亮失败（既有立场）。
- 会计可见性沿用公告日锚：公告未到下一日的折算对策略视图不可见。

## 停复牌

ETF 无状态表；已公布行（volume=0、close=携带 pre_close）是交易所事实：参与状态记 `zero_volume`、订单拒绝（`zero_volume`，可重试）、估值用当日公布 close。负量/非数值仍 `unknown ETF suspension/valuation` 拒绝；缺行日维持缺行，不以虚构补行。复牌日 volume>0 自然恢复，重试订单按新价位成交。

## 代表事实与数据核验

| 159941.SZ 广发纳斯达克100ETF | 日期 | 事实 |
| --- | --- | --- |
| 计划公告 | 2022-06-29 | 《实施份额拆分业务并调整最小申购赎回单位的公告》 |
| 实施完成 | 2022-07-04 收盘后 | 1:4 拆分；暂停仅申赎（06-30..07-04），二级市场正常交易；最小申赎单位 100万→130万份 |
| 除权日（账本事件日） | 2022-07-05 | [结果公告](http://static.cninfo.com.cn/finalpage/2022-07-05/1213942300.PDF)（含 06-29/06-30 前序公告引用） |

生产库核验：`fund_share` 07-04→07-05 353,705.2541→1,414,821.0164 万份（3,537,052,541.00→14,148,210,164.00 份，精确 ×4，整倍无碎份）；bars 07-04 close=2.384 → 07-05 pre_close=**0.596**（=2.384/4 精确），07-05 volume 5.39M 正常交易；`fund_adj` 07-04→07-05 **1.0→4.0**。

旁证签名（仅留档，未建 terms）：159231.SZ 2025-08-11 ×2（adj 1.0→2.0 精确）；159636.SZ 2025-12-08 ×2（adj 1.0→1.9986，参考价取整在四位量子内可解释的容差案例——若未来声明该事件，现容差公式 `quantum×(1+ratio)/2` 对 0.0014 的偏差不足以放行，需按公告单独核）。停牌轴的数据现实：生产库另有 90 行 ETF 零成交日（volume=0、close=pre_close 携带，如 159291.SZ 2026-10-19）。

## 固定样例、真实运行与真人验收

- **固定样例（已做）**：系统测试 `tests/system/backtest-share-conversions.spec.ts`（fixture `share_conversions_backtest_app`，登记于 `tooling/dev/system_tests.py`）走正式 UI→真实 API→持久化→重读边界：未声明先失败（corporate action 拒绝文案可见）→repair 留存声明→补证后沿原配置新建运行 completed；声明事件/份额×4/成本重摊/NAV 从实际成交与折算 entry 手算复验；07-06 零成交日 `zero_volume` 拒单且无成交、07-07 复牌按 0.61 成交；账本内事件按 identity 去重、单次折算，重提请求沿原配置新建运行而非二次入账（checkpoint resume 幂等由单测覆盖）；重开读已保存报告、键盘可达、导出 JSON、axe 无 critical/serious。
- **单测（已做）**：声明加载器校验、ShareConversion 语义（整倍/非整数拒绝/identity 冲突/可见性）、账本换算与幂等（含 checkpoint 恢复不二次折算）、执行字段（折算参考价/因子容差/未解释跳变仍拒/零成交行）、变换、冻结、checkpoint（账本+成交匹配）、序列化/DTO、Web 映射。
- **真实运行（未做）**：真实 159941 窗口的普通运行需要 (a) 真实 `etf_share_conversions` 声明快照留存（当前仅 fixture/维护者手动路径，夜间链摄取任务未接入）与 (b) 159941.SZ 的 `etf_reference` 参考规则声明（其不在 #758 六品类固定名单内）。此前真实运行在折算日按守卫拒绝，是诚实的不完整。
- **真人验收（未做）**：键盘/焦点/日期/单位的人工核验未做；系统测试的 axe 与键盘断言不代替真人签收。

## 未完成项与边界

- 声明集不全：未声明的折算日仍被因子跳变守卫拦截；新增声明需公告 URL 与数据核验随附。
- `fund_share` 采集能力已备但未接公司行动管线，仅覆盖审计使用；份额换算正确性不依赖它。
- 现金分红+折算同日复合参考价、非整倍折算取整规则、ETF 状态表化的停牌口径（零成交≠停牌的正式状态源）未做。
- 本票不关闭 #767（长期请求）、#768（三类 2014 起目标）、#779（真人验收）、#780（发布证据）；中间代表窗口成功仅证明所声明增量。

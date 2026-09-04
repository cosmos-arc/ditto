# PAP-09 真实交易日输入验收

状态：`LIVE ANCHOR PASSED / ACCELERATED 20-DAY RUN PENDING EXACT APPROVAL`

本目录承载 Manual 验收和 2026-09-02 Paper live anchor 的公开证据。操作员已精确批准 [account-acceptance-proposal-20260902.json](account-acceptance-proposal-20260902.json)，并于 2026-09-02 完成 [bootstrap](bootstrap.json)：专用 Manual 账户以 4 个不可变事件重建为现金 100,500.00、`518880.SH` 持仓 100。上海市场收盘且 Tushare 发布当日日线后，操作员又明确授权不等待次日；[live anchor](days/2026-09-02.json) 因而在当日 18:00 记录一笔 Paper-only 成交并完成日终对账。[原自然日状态](soak-progress.json) 保留为历史证据，HMAC 链有效，券商连接和真实订单均为 0。

最终发布口径改为 [加速验收提案](../pap09-accelerated-proposal-20260902.json)：在隔离 fresh root 中使用生产 Paper 路径，按日期顺序重放 20 个已经收盘且 provider bar 已发布的真实 Tushare 交易日，每日模拟进程重启并验证账本累计、EOD reconcile、snapshot 和 HMAC 链。该证据可完成 PAP-09/Q4 发布验收，但明确不宣称自然时钟 wall-clock soak；live anchor 单独证明真实当日可运行。新运行是内容寻址写操作，必须取得提案所列精确批准后才执行。

提案锁定以下边界：

- 使用专用合成 Manual 验收账户，追加期初、事件、更正并从完整事件流重建；不读取或猜测个人真实持仓。
- 使用专用 Paper 账户和 `seed_etf_industry_rotation`，每个已结束且 provider bar 已发布的交易日最多记录一笔 100 份 `518880.SH` Paper 买入。
- 提案原首日策略要求严格晚于批准日；2026-09-02 的单日证据以操作员后续明确授权作窄范围覆盖，并且仅在上海市场 15:00 后、Tushare 当日 bar 可见时生效。未来日期和缺 bar 仍 fail closed。
- 每日证据绑定 decision/execution/publication cutoff、source snapshot、fill、账本事件和 reconcile；缺 bar、未来数据、断链、重复或漂移一律 fail closed。
- 私有证据链密钥只在批准后生成于 ignored data root，权限 `0600`，不导出；公开证据只含 HMAC 签名和哈希。
- 全流程只允许 Paper，不连接券商、不发真实订单、不发布或激活策略。产品 Agent 不能启动 Paper 或写 Manual。

Live anchor 已完成：`2026-09-02`、Tushare `etf_daily`、1 个暂停态 Paper session、1 笔成交、1 个账本成交事件和 1 次平衡日终对账。Q4/PAP-09 不再等待 4/19 个未来自然交易日；待精确批准后，由加速运行器一次顺序完成 20 个已收盘真实交易日。任何核心账本、Paper 语义或 snapshot 合同变化都会使整组加速验收失效并要求重跑。

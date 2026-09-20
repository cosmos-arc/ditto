# Ditto 量化研究、ML 与 LLM Agent 再审视

审查日期：2026-09-20。源码基线：`4c968e1d3f21828ab20308cdfdea550babee6454`。范围：源码与已保存证据、当前相关 GitHub ticket、一手框架文档/源码和论文；不包含本轮训练、模型付费调用、Docker 物理重验或真实连续 Paper 运行。下文“建议”是规划判断，不是已实现能力或收益承诺。读取 research、ditto-pit-safety 及 analysis/agent/apps 近端指南。

## 核心结论

Ditto 应形成“可复现的个股截面选股与 ETF 配置研究 → 可解释决策 → Paper/手工账户反馈”的专业个人工作台。现有时间、工件、审批与试验台账是值得保留的基础，但最缺的是数据到预测到实际决策的可用闭环。新增 ML 有必要；新增模型数量、聊天框、MCP 服务或多 Agent 数量本身不是前沿能力。应衡量同一预算下，研究效率、样本外增量、成本后的可执行性、错误发现和停止能力。

本轮发现旧计划有事实过时和结论过强：会话实体已经存在；OCI 曾经完成物理验收；“业界最高档”“Qlib+LightGBM 是 A 股标准”“Qlib/RD-Agent 都没有研究纪律”均缺充分依据。应保留可证明的差异，删除排名式自评。

## 源码与证据核查

| 能力 | 本轮核实 | 正确边界 |
|---|---|---|
| 试验多重比较 | `packages/analysis/src/ditto_analysis/experiments/trial_adjustments.py` 实现 DSR 与 CSCV PBO；缺失/失败 trial、未预注册 partition plan 等会返回 NOT_EVALUATED；PBO 从原始收益组合重算、处理并列、限制组合数量 | 有真实统计实现，并非只有字段；仍不证明样本独立、试验族完整、未来 alpha 或真实运行效果 |
| 数据窗口 | `packages/application/src/ditto_application/processes/experiments/generated_candidate_pit.py:246` 起实际裁剪训练尾部 purge 和测试头部 embargo；身份绑定 cutoff/snapshot/fold | 日数间隔不能自动证明新 ML 标签观测区间无交叠；需为实际标签定义验证边界，不能写“照常生效”即结案 |
| ML | 对 packages 与 apps/backend 的 Python/TOML 搜索 sklearn/lightgbm/torch/xgboost 未命中 | 本轮未找到已交付监督学习训练/推理管线；不能由 sandbox fit/score 接口推断已具备 ML 产品 |
| 会话 | `packages/agent/src/ditto_agent/runtime/service.py:88` 有 AgentSessionCreateCommand，`:111` 起 run 绑定 session_id | 不是从零增加 session；需要审查与补齐多轮上下文、用户修订、旧证据失效、预算累计及 UI |
| OCI | 实现位于 `apps/backend/src/ditto_apps/registry/agent/oci_sandbox.py` 和 runner；包含精确依赖、image/security scope 与 trusted approval verifier | 旧票写 packages/agent 路径错误；模块头仍写 A3 pending 是与后续文档冲突的过时说明，不应据此推断状态 |
| OCI 已存验收 | 本轮读取 `docs/evidence/r5/release/sandbox-live-status.json`：status=passed、release_gate_passed=true、attack_case_count=11、approval_id=A3-2026-08-17-orbstack-2.2.1-arm64-v2；物理测试 `apps/backend/tests/integration/test_oci_sandbox_security.py` 检查攻击、fresh container、并发和无残留 | 这是已保存历史证据。本轮未重算完整 attestation，也未重跑 OrbStack。不能称从未点火，更不能称今天环境通过 |
| Agent eval | sandbox JSON 样本含 `fake_only_attested`，另外有上述 sandbox_live 物理入口 | Fake 回归、物理隔离、真实模型、连续 Campaign 必须分别报告，不能互代 |
| 成本容量 | `packages/backtest/src/ditto_backtest/simulation/slippage.py` 有固定 bps/成交额冲击；fill.py 有 participation；brokerage 默认 FixedBpsSlippage | 不是没有成本模块；ML/搜索验收要证明实际选用了什么模型、参数来自什么证据，并做敏感性，不因存在类就宣称容量已验证 |

## 与优秀开源研究体系的具体对比

[Qlib](https://github.com/microsoft/qlib) 已提供从 dataset、模型训练、预测、回测到评估的 qrun 工作流，含 LightGBM/线性与更多模型示例；[Recorder](https://github.com/microsoft/qlib/blob/main/docs/component/recorder.rst) 与 [rolling 示例](https://github.com/microsoft/qlib/blob/main/examples/model_rolling/task_manager_rolling.py) 提供实验记录与滚动任务。因此 Ditto 不能以“有台账”宣称 Qlib 没有实验管理。应该借鉴其可运行 baseline 与训练/推理连接，保留自身 A 股时点数据、人工决策、账户反馈边界。建议先原生接线性模型与 LightGBM，Qlib 用作隔离对照实验；只有真实消费需求出现才做完整适配，避免双份数据语义与双份调度器。

[RD-Agent 官方源码](https://github.com/microsoft/RD-Agent/blob/main/rdagent/app/qlib_rd_loop/quant.py) 与 [论文](https://arxiv.org/abs/2505.15155) 展示假设、因子/模型实现、运行反馈的迭代研究。Ditto 可以借鉴失败修复、实验轨迹及因子与模型联合探索，不能把框架论文中的历史收益当成自己 A 股数据上的表现。官方仓库存在 [isolate holdout evaluation from iterative research feedback](https://github.com/microsoft/RD-Agent/pull/1442) 草稿 PR，本轮页面显示 Draft；这提示需按确切版本核查反馈隔离，既不能称其已修复，也不能由此给整个框架贴无治理标签。

[QuantConnect ML 文档](https://www.quantconnect.com/docs/v2/writing-algorithms/machine-learning/key-concepts) 将模型保存、加载、研究端预计算预测与算法端消费连接起来；[训练说明](https://www.quantconnect.com/docs/v2/writing-algorithms/machine-learning/training-models) 覆盖训练事件。Ditto 应对齐的是“模型重启后还能恢复、预测与训练版本可追溯”的日常可用性，而非复制其券商执行或云服务规模。本轮不评估 LEAN 对中国本地数据/交易制度的即插即用程度。

## 模型研究方案必须补齐的合同

1. **标签先于模型。** 固定决策时刻、最早可成交时刻、收益区间、复权口径、停牌/涨跌停不可成交规则、退市样本处置。每条标签存起止与最终可知时间；训练截止时标签必须已经成熟。个股面板按交易日整体分割，不能随机按行拆分同日股票。
2. **拟合数据边界。** 缺失填补、缩尾阈值、标准化、特征选择、行业中性化估计与超参/early stopping 都有独立训练/验证边界；同日横截面处理可以使用当时可见股票集合，但不能用未来成分或全样本参数。用跨 split 标签及迟发公告做反例测试，验证实际训练入口。
3. **滚动训练与推理。** 每 fold 独立模型工件，训练窗、验证窗、预测窗及更新节奏不可含糊。推理只能加载决策时已训练完成并获选的版本；缺特征、schema 漂移、模型加载失败时明确不出信号。重启恢复和相同输入预测重现是验收项。
4. **模型工件。** 同时绑定代码、依赖、CPU/加速环境、随机种子、超参数、特征顺序/类型、数据快照、训练边界、预测与组合构建版本。哈希证明身份，不证明训练可重算；对非确定性库声明数值容差。保存可审查的原生模型格式，禁止加载不可信 pickle 作为通用交换格式。
5. **比较基准。** 等权/低换手规则、线性模型与 LightGBM 使用同一 universe、日期、特征可见性、费用和调仓规则。报告 IC/RankIC、分层与多空诊断、long-only 组合、行业/规模暴露、换手、回撤及相对基准增量。漂亮 IC 不能代替实际可买的组合结果。
6. **成本与容量。** 至少给常态/偏保守成本场景和目标资金规模的参与率；按实际生效的交易规则模拟失败或延后成交。报告收益是否依赖微盘、极低流动性和少数日期。已有成本代码需要被真实 ML 评价调用并记录，不能另造简化评价口径。
7. **重复试验。** 特征筛选、参数搜索、随机种子挑选、提示词改写和看到结果后的人工改动都可能增加选择次数；研究族需跨 Campaign/fork 延续。PBO/DSR 是特定假设下诊断，不能充当统一“安全分”。失败 trial 使统计项不可计算时，解释缺口，不删除失败记录，也不伪造收益。参考作者论文 [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)。
8. **最终测试的可见性。** 最终 holdout 的标量指标同样是反馈；若 Agent 或人据此继续改模型，后续结果不得仍称未见测试。将开发验证、一次最终评价、前向冻结观察明确分开；定期重训/晋级政策也要预先声明。

ETF 不应直接复用数千股票截面 ML 的经验：可选 ETF 数较少、同指数产品高度重叠，样本有效独立性低。先建立指数/资产暴露层面的可解释配置、费用/流动性筛选与简单趋势或风险基线，再评估 ML 是否增加信息。不要把同指数不同 ETF 当成大量独立训练样本。

## 文本与 LLM：当前规划低估的两种时间风险

公告字段的“发布时间”只是来源声明，不自动等于系统可用时间。需要分开保存原始发布时间、供应商首次可得时间（若能取得）、本地首次采集时间、修订时间、内容版本与渠道；日期精度不足时采用保守可用时刻或降级。历史回填不代表本地过去已经采集；历史模拟可声明依赖供应商时点假设，真实前向运行必须保留首次观察证据。

文本工件包含原文、附件、解析/OCR 版本、实体映射、去重、修订链与访问许可。公告和卖方研报应分开规划：权利、时间、覆盖和噪声不同。“公告+研报同时做情感”过宽。第一条建议选明确事件（业绩预告变化或回购进展等）的结构化抽取，先测字段精度、引用可追溯与时延，再测增量信号；中文模型名称不能代替本地标注样本评估。

**输入 PIT 仍挡不住模型预训练中的未来知识。** [Glasserman 与 Lin](https://arxiv.org/abs/2309.17322) 研究了历史新闻情感分析中的预训练前视与实体信息干扰；[DatedGPT](https://arxiv.org/abs/2603.11838) 探索按年度截断语料训练的模型。这些是需要纳入设计的研究证据，不是已证明适合中文 A 股的现成答案。建议存模型版本与已知训练截止声明，历史文本收益标记污染风险；匿名化/日期遮蔽是对照，不是去污染证明。优先从冻结模型后的前向样本验证，必要时以严格时点训练模型作研究对照。闭源滚动模型不可保证再次生成同一分数，故需保存完整响应与结构化打分产物，区分“审计重放”与“重新调用重算”。

## Agent 的合理前沿与安全验收

先让 Agent 能围绕一个研究对象回答“为什么入选、什么证据会推翻、与基线相比提升来自哪里、下一项最有信息量的实验是什么”，每个行动有目标、可读差异、证据链接与预算消耗。多轮上下文保存业务对象和 evidence 引用，不将无界聊天历史当事实数据库；旧报告不应越过当前 cutoff 或恢复已撤销权限。每轮仍独立 run，但累计研究族/预算不能通过新 session 洗白。

外部文档和工具结果是不可信输入。源文本中的“忽略规则/读取账户/上传文件”不得改变 host 权限；拒绝也要验证到实际执行入口，不能只看模型口头拒绝。额外覆盖恶意 PDF/OCR、记忆投毒、跨研究/账户上下文、工具输出诱导、模型伪造引用、MCP 回传敏感数据等场景。只读工具仍可能泄漏组合和有许可限制的数据。[MCP 官方安全文档](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/docs/2026-07-28/tutorials/security/security_best_practices.mdx) 明确讨论本地服务器、令牌与传输边界；协议不能替代授权。

物理沙箱计划应从已有 A3 精确 scope 出发，先核对环境/镜像/依赖是否漂移，再决定复用或重新审批；然后用一个真实搜索轴在预算内完成失败修复、候选产出、台账、评价、人工选择和恢复。Agent LLM token、墙钟、实际费用、无效试验率、有效反例率、人工节省时间与收益指标分开汇报。无需先上多 Agent 组织层或通用外部插件市场。

## 对既有 ticket 的具体修订建议

| 既有 ticket 标题 | 建议修改 |
|---|---|
| P1-Agent：对话式研究 Agent（多轮会话层，治理内核不变） | 背景改为“已有 session/run 缺连续研究交互的验收”；删“生产力减半/最高档”。以同一候选多轮比较、旧证据失效、跨 session 越权、累计预算与恢复为验收；先查现有 API/UI，避免重复建会话实体。 |
| P1-ML：治理内截面 ML 管线（LightGBM 候选纳入 holdout/PBO 门禁） | 改为“时间正确的模型训练、推理与同口径组合评价”；补上上述八项合同。PBO 按前提报告，不能要求每个单模型试验强行满足。依赖股票真实数据与执行假设；模型卡不能代替推理运行。 |
| P1-研究：LLM 文本因子线（公告/研报 → 情感/事件因子） | 先做公告事件抽取与时间/授权研究决策，再做因子；研报另设待证实问题。删除“公告时间天然 knowledge date”和“模型版本+哈希即可重放”的等同关系，补预训练污染和前向冻结验证。收费与权限由数据源专项重新核实，不能复用旧票价格。 |
| P1-Agent：Campaign OCI 沙箱点火（A3 审批与实跑验证） | 改为“已有 OCI 验收复核与真实 Campaign 闭环”；引用保存的 A3 报告，区分历史通过和现环境复验。不要重复要求早已完成的人工动作。闭环需真实搜索、失败/预算停止/恢复及明确 trial/holdout 边界。 |
| P1-架构：MCP 服务化（application 查询面封装本地 MCP server） | 保留 spike；以一个已确认外部客户端和三项只读任务验证需求。首选最简单本地传输；复用 application 权限/时间边界，增加数据外传与许可控制。只有外部使用收益被观察到再产品化，不因行业趋势设为核心前置。 |

建议执行顺序：数据与研究语义 → 线性/LightGBM 同口径最小闭环 → 模型生命周期与前向 Paper → 上下文研究交互和既有 Campaign 真实运行 → 文本事件增量试验 → 有消费者的 MCP。可以并行做文本许可/时点研究和 OCI 证据复核；不要让 MCP 或聊天重构阻塞核心选股能力。高级模型、强化学习和因子/模型联合自优化只在基线已稳定、预算有界、额外问题清晰时进入研究，不作为专业量化工作台的身份徽章。

## 本轮验证范围

已读取上述源码、相关 issue 正文、官方网页和保存的 sandbox JSON；没有执行单测/PIT/模型训练/物理沙箱/付费模型/连续运行。当前报告不构成安全签字、发布准入或策略有效性结论。任何修改后的计划都应保留 CODE、TEST、LIVE、DOGFOOD 与研究有效性各自证据，不用单一“完成”抹平差别。

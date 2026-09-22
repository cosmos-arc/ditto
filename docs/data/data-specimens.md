# 五类数据试样准入与限制传递

> 来源：#251 规格 / #259。五类试样是**逐项留证**的人工裁决证据包：财报重述、退市证券、指数调样、分红 ETF、跨境 ETF。记录实际取证结果；缺试样保持未验证，不伪造通过，也不阻塞其他已合格路径。

## 记录模型

每条 `DataSpecimen`（`ditto_data.catalog.specimen`）绑定一个类别、一个数据集和一个具体锚定标的/事件（如 `510300.SH`、`000003.SZ`），内容寻址 `specimen:{category}:sha256:{digest}`，append-only 存于 `data_specimen_records`。

字段按验收口径：原件（各来源 `provider_snapshot_id`）、时点（`knowable_from` 时区感知时刻 + `time_precision`）、覆盖（`coverage_from/to`，可空）、许可（`license_record_ids`）、缺口（`gaps` 结构化代码）、用途结论（`allowed_uses`，取值同 `DataUse`）。

fail-closed 不变量（构造时校验）：

- `verified` 必须同时具备：至少一个已取证原件、覆盖起点、可知时点、许可引用、as-of 反例、人工裁决（who/at）。`unverified` 不许声明任何 `allowed_uses` 且必须显式记录缺口。
- **主备相同上游不称独立验证**：`upstream_independent=True` 仅当 ≥2 个来源都已取证且声明了互不相同的 `upstream_group`；同组或未声明自动落 `UPSTREAM_SHARED` / `UPSTREAM_INDEPENDENCE_UNPROVEN` 缺口。两个通道（如 Tushare 代理与 fuyao）不自动等于独立上游（ADR-datasource-dual-source）。
- **口径不符不能静默替补**：多来源 `convention_alignment` 必须声明 `aligned`/`divergent`；`divergent` 自动落 `CONVENTION_DIVERGENCE` 缺口。
- **报价未知不编造**：采购轨道（`in_budget` / `professional`）的 `quote_status` 为 `unknown` 时自动落 `QUOTE_UNKNOWN`。录入不触发任何采购。
- `knowable_from` / `adjudicated_at` 拒绝 naive 时间戳（与 #287 同口径）。

## 录入与读取

- 录入：CLI `data-products record-specimen <payload.json>`（人工裁决入口，经 `DataProductSpecimenCommands` 校验后 append）。无自动取证、无自动采购。
- 读取：CLI `data-products specimens` 或 `GET /api/v1/data-products/specimens`（`DataSpecimenQuery`）。五类**始终全部返回**；缺试样的类别给 `SPECIMEN_NOT_COLLECTED`，引用悬空的快照/许可追加 `SPECIMEN_SOURCE_SNAPSHOT_MISSING` / `SPECIMEN_LICENSE_MISSING`（只读层计算，不改写记录）。
- Web：数据产品工作台「五类试样」视图（类别/状态/锚/允许用途/上游独立/缺口）。

## 限制传递（不能洗成正式证据）

- **导出**：`ResearchDatasetExport` 对来源数据集解析**全部**绑定试样，逐条参与门禁——任何一条 `verified` 且 `allowed_uses` 不含 `formal_research` 的试样都会**拒绝**导出，同数据集更晚的宽松裁决（含其他类别）不能掩盖更早的探索限制。无试样或未验证不阻塞——试样证据是可选证据，不是其他路径的前置条件（父规格：实际字段已合格的其他路径不等全部试样完成）。所有绑定试样（specimen_id、类别、用途结论、缺口，含查询层计算的悬空引用缺口）写入导出回执 `source.specimens`，随文件传播。
- **复制研究 / Agent 引用**：试样结论内容寻址、append-only、按 dataset_id 绑定；研究快照与 Agent 证据引用绑定内容寻址 snapshot id，引用本身不携带用途标签，但任何门禁从引用回查试样裁决都得到同一不可变结论——引用层不存在提升资格的通道。若未来 Agent 工具直接消费试样绑定数据集，再评估是否把用途标签内嵌进证据信封。

## 边界

- 试样结论≠字段准入：Selection/研究/ETF/Paper 的字段准入继续走 `FieldAdmissionQuery`（#256），两者互不等待。
- 预算报价与供应商权益取证归数据策略票（#191）；本结构只承载"实际取证、报价未知项与限制"的记录。
- 自动化测试使用合成证据；合成通过不证明供应商真实历史覆盖或权益已核实（父规格 Testing Decisions）。

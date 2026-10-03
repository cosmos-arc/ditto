# #196 Batch 3 ops 认证补齐——adj_factor 补数+认证（2026-10-02）

真实环境：`DITTO_STATE_ROOT=<repo>/data`（同 Batch 2 开发根），actor chevy。本目录是机器生成证据 + 如实边界记录；时间戳早于所在提交。

## 完成项

### adj_factor 补数（2025-01→2026-05）

- `data-products bootstrap adj_factor --start-date 2025-01-01 --end-date 2026-05-31`（bounded，license `license:tushare:adj_factor:sha256:dfd0592b…`，Tushare 代理按日全市场拉取）。
- 结果：338 计划交易日，17 月度锚点拉取全部成功（每次整月返回），0 失败 0 跳过。
- 盘上核验：`market/stock/adj/2025.parquet` 243 个交易日/1,321,761 行；`2026.parquet` 180 个交易日（至 09-29）；合计 5,651 标的、2,315,450 行，与 stock_daily 认证区间（2025-01-02→2026-09-29，423 交易日）对齐。

### adj_factor 认证（selection-fields-v1）

- build-certification → certify（approved，2026-10-02T16:27Z），报告 `certification:09b084688d01a119…`，绑定 21 个月度快照（2025-01-02→2026-09-29 全跨度）。
- certified field `adj_factor`：covered 2025-01-02→2026-09-29，time_precision=date，publication/available=09-29 18:00 Asia/Shanghai（同 Batch 2 日频事实约定），observed_at 由快照账本绑定（2026-09-30T10:38Z），SSE 日历可见性由构建器解析（`2026-09-30:1`）。
- consumer 证据 `consumer-read-adj_factor.json`：经生产物理契约读取 canonical 调整因子存储（全窗 231 万行、5,651 标的），`field_inputs` 留存 `adjustment.adj_factor` 绑定摘要。
- recovery 证据：复用 Batch 2 中断恢复演练 `recovery-interruption-stock_status.json`（管线级演练、三数据集同源的既有先例；adj_factor 未单独演练，如实声明）。
- 车道自证：`CertifiedSnapshotIndex` 解析 21 窗口，2025-01-02/2025-06-15/2026-09-29 抽检全覆盖——`ASSEMBLY_ADJUSTMENT_WINDOW_MISSING` 在真实组装尝试中不再出现（失败点后移至名册链，见阻塞项 A）。

### v1 车道宇宙

- `a-share-custom-202609` 在 as-of 解析 5,581 成员 ≠ 注册车道 5,922（差 341 只退市标的），组装按设计 fail-closed（`ASSEMBLY_UNIVERSE_SCOPE_UNSUPPORTED`；窄池需 membership snapshots，属后续切片）。
- 新建 `a-share-registered-lane-202610`（custom，effective 2026-09-01，成分=注册表全部 5,922 股票标的），as-of 成员与注册集相等核验通过。

## 阻塞项（首次真实组装冒烟未完成的原因）

**A（代码级）：stock_basic 留存 payload 不满足主链帧契约。** 名册链 `HistoricalUniverseQuery.pin` 要求留存帧含 `MASTER_FIELDS`（instrument_id/effective_from/effective_to/publication_at/available_at/list_date/delist_date），真实 Tushare stock_basic 留存列为原始 provider 列（source_ticker/ticker/name/exchange/list_date/delist_date/list_status）→ `HISTORY_FIELDS_MISSING`。既有测试（单元 Fake history；集成合成帧自带 HISTORY 列）从未覆盖真实留存形态。需一处权威的投影实现（摄取侧或读侧），建议与欠账清单第 1–5 条（live 读模型批量 PIT 原语，同根）合并切片。

**B（运维窗口）：黄金周期间名册认证窗口不覆盖 as-of 当日。** live 组装要求 as_of≈now（±5 分钟偏差窗）；今日上海日 2026-10-03，而 stock_basic 认证窗口止于 09-30、stock_status 止于 09-29 → as-of 日无认证窗口可绑。解锁路径：交易日（≥2026-10-09）EOD 补当日快照并纳入认证，或对 registry 类快照按"当日请求区间"补 10-02/10-03 快照（需先解决 A）。

## 未做（依赖 A/B 解锁）

- stock_basic `name`/`list_date`/`delist_date` 字段扩展重认证（现 claims 仅 `list_status`）。
- stock_daily claims 补 `pre_close`/`amount` + 覆盖窗口扩展（现仅 2026-09-01→09-29）。
- 四数据集按首个真实组装 payload 重冻结 `instruments.*` consumer_bindings（鸡生蛋：摘要依赖组装成功后的 exact payload）。

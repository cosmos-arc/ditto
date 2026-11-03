# 批次3 首个真实流程交付（#658：股票/ETF 图表＋个股资金画像）

交付时间：2026-11-04。范围＝冻结矩阵批次3（B3）行：股票/ETF 图表与
个股资金画像跨栈流程，约定窗口语义在消费面诚实表达。

## 1. ETF 复权接入图表链（core 缺口闭合）

- 数据集参数化：`MarketChartQueryFacade._load_factors` 按 asset_class 选
  因子数据集（stock=adj_factor、etf=fund_adj），贯穿快照选择、
  `DatasetSnapshot` 身份与 payload 装载
  （`technical_analysis_source.load_adjustment_factors(dataset_id=…)`）；
  成熟度门按实际消费数据集把守
  （`assert_adjustment_allowed(datasets=…)`）。
- 撤销 `unsupported source-bound chart adjustment` 的 ETF 拒绝（B1 时
  诚实降级，B3 接线后解除）；缺 fund_adj 留存快照 fail closed
  （`retained chart fund_adj snapshots are unavailable`）。
- 数值验证（`test_chart_etf_adjustment_uses_fund_adj_factors`）：hfq=价×
  当日因子、qfq=价×当日因子/末日锚因子、fund_adj 快照身份随 bars 传播
  （`source_snapshot_ids` 双证据）。
- Web：`instrument-chart-view` 解禁 ETF 复权切换（删除 disabled 与
  「暂未接入」note；服务端缺因子 fail closed，前端不再静默降级）。

## 2. 个股资金画像（四数据集同标的同窗口联看）

- Data 层：`CapitalStore.get_moneyflow/get_top_list/get_top_inst`（逐标的
  窗口读，空帧直通）＋`get_margin_trading_range`（PIT 可选窗口读）。
- Application 层：`CapitalQueryFacade` 四窗口方法（experimental 门沿
  用）；新 `CapitalProfileQueryFacade`
  （`queries/capital_profile.py`）编排四块＋末端推导＋**两融待补语义**
  （窗口尾部 5 个交易日内晚于实际末端的缺失日＝待补，与 02:00 夜修
  滑窗 #625 对齐；无行＝非两融标的不适用）。
- HTTP：`POST /capital/profile`（标识符三选一＋窗口＋
  allow_experimental_data）。必需块 moneyflow/top_list/top_inst
  （`latest_available`＝库内现存行）；可选块 margin_trading
  （`pit_asof=end_date`）带 `pending_trade_dates`＋
  `freshness_promise`（09:15 披露制度承诺，新鲜度承诺非 PIT 能力）；
  每块携带 `data_coverage`（覆盖限制快照：末端/缺口/知识轴）。
  无事件/空窗是合法状态不冒充失败。
- 契约三处再生成（v1.json＋schema.d.ts＋operation-contracts.ts，
  integrator lease 下生成）；冻结证据
  `release-preflight-etf-inputs.json` 随 OpenAPI 变更刷新（既知坑）。
- Web：instruments 工作区新「资金」页签（`instrument-capital-view`）：
  四块布局＋末端/覆盖 tooltip＋两融待补清单＋披露承诺文案；
  `useCapitalProfile` 查询钩子（experimental 显式开关）。

## 3. 窗口语义（22:30/09:15）的表达位置

- 22:30（etf_nav 当日净值可得承诺）：etf-nav 端点 `data_coverage`
  （末端/状态/缺口）即承诺的诚实消费面； LIVE 门
  （`data_live_gate`）按 SLA 滚动核验，B5 总验收逐项重测。
- 09:15（两融 T-1 发布承诺）：画像 margin 块 `freshness_promise` 字段
  ＋待补列表（见 §2）；数据到达由 02:00 夜修滑窗 force 重取保证
  （11-02 实测翻转＝B1 校准生效，见批次2 证据 §6）。

## 4. 合同消费面更新

coverage-contract.yaml 四数据集 consumers 增补画像入口：
moneyflow/top_list/top_inst＝`个股资金画像(/capital/profile)`；
margin_trading＝`个股资金画像(/capital/profile 带 09:15 待补语义)`。

## 验证

- 新集成测试 `test_capital_profile_storage_api.py`（真实 ParquetStore＋
  facade→HTTP 全链：stored/empty×四块语义、待补推导、experimental 门、
  承诺默认值）；ETF 图表复权测试改写为正向数值断言＋缺快照 fail
  closed。全量 **16,749 passed**（含 R5 preflight 冻结证据刷新后 16/16）。
- type-all 0 错误；web type/lint/tests 31/31 通过；契约检查绿。

## 复测入口

```bash
# 画像（identifier 三选一）
curl -X POST /api/v1/capital/profile -d '{"instrument_id":1000001,
  "start_date":"2026-10-01","end_date":"2026-11-03",
  "allow_experimental_data":true}'
# ETF 复权图表
curl -X POST /api/v1/market/chart -d '{"instrument_id":2000001,
  "adjustment":"qfq","period":"daily",...}'
```

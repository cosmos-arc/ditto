# fuyao 跨源对账扩展②③④ 真实运行证据（#473-#475）

- 运行日期：2026-10-05
- 代码：分支 `codex/475-etf-nav-reconcile`（含 #473/#474/#475 三票堆叠实现）
- 数据源：Tushare 代理（t.xiaodefa.top）+ fuyao（密钥经根 `.env` 环境注入，应用不读 `.env`）
- 运行环境：隔离 state root `/tmp/ditto473-reconcile`（`metadata/` 为开发根 metadata 库
  副本；`market/` 符号链接到开发根 `data/market` 只读主源存量；真实写入仅
  `quarantine/` 与隔离根内的 fundamental 表；开发根本身未写入）

## 命令形态

```bash
FUYAO_API_KEY=… TUSHARE_TOKEN=… \
DITTO_CONFIG_ROOT=<repo> DITTO_STATE_ROOT=/tmp/ditto473-reconcile \
DITTO_CACHE_ROOT=/tmp/ditto473-reconcile-cache \
python -m ditto_apps.cli.main ops reconcile <DATE> --dataset <dataset>
```

## 1. index_daily（#474，2026-09-30）

黄金集过滤后 4 指数（000001.SH/399001.SZ/000300.SH/000852.SH）：

```text
主源行数: 4
对账统计: 主侧=4 辅侧=4 匹配=4 主侧未匹配=0 辅侧未匹配=0 主侧重复键=0 辅侧重复键=0 差异数=2
对账结果: passed=True 比较=可比 issues=1
```

- 000001/000300/000852 OHLC 在 fuyao 2 位小数舍容差（tick 0.006）内匹配，
  volume/amount 在相对 0.1% 内匹配（fuyao 股/元 ÷100/÷1000 源侧归一验证成立：
  41456025000股/100 = 414560250手 ≈ Tushare 414560247）。
- **真实源间差异**（quarantine/quality_comparison 落盘）：399001 深证成指
  volume 主 1.4855e8 手 vs 辅 4.9472e8 手（×3.33）、amount 主 3.5728e8 vs 辅
  7.5862e8 千元（×2.12）——非单位换算错误（非 ×100/×1000）、非舍入，OHLC
  一致，属 Tushare 与 fuyao 对深成指量额口径的真实分歧，按 WARNING 报告不阻断。
- 覆盖不足 → not_comparable 的实路径：辅源窗口外日期（如 2018-06-01）返回
  空 item（实测），全部缺席由零交集判 not_comparable；未知代码（申万
  801951.SI → code=1002）按标的跳过记 warning。

## 2. income_statement（#473，2026-10-05 标签）

主源 = 隔离根内经正常摄取管道写入的 12 行（4 黄金股 × 3 期，`ingest
fundamental income --ticker T -s f_ann_date -e f_ann_date`；标准 income 端点
窗口模式因多 report_type 重复键被翻页守卫拒绝，按 period 单期 + 公告日
窗口绕开——摄取缺口另行落票）；辅源 = fuyao quarterly limit=20（4 标的共
80 期）：

```text
主源行数: 12
对账统计: 主侧=12 辅侧=80 匹配=9 主侧未匹配=0 辅侧未匹配=68 主侧重复键=0 辅侧重复键=0 差异数=4 披露日错配=3
对账结果: passed=True 比较=可比 issues=1
```

- **数值一致**：9 个同 vintage 键的 net_profit/operating_profit/eps 全部在
  容差内匹配（茅台 2025Q3 n_income 668.988 亿分毫不差；招行年报百万级舍入
  在相对 1e-4 内）。
- **口径差异**（4 差异行，如实报告不折算）：revenue——Tushare
  total_revenue（营业总收入）vs fuyao operating_income（营业收入）。
  茅台 2025 年报差 32.2 亿（≈财务公司利息收入科目）、2025Q3 差 24.5 亿、
  2025H1 差 0.9 亿（另有 vintage 错配未比）；美的 2026Q1 差 4.8 亿、
  2025 年报差 20.5 亿。银行/集团财务公司板块两口径系统性不同。
- **vintage 差异**（3 行单列 vintage_mismatch，不做数值比较不计 matched）：
  茅台/美的/移动 2025H1 的 fuyao report_date（2026-08-1x）比 Tushare
  f_ann_date（2025-08-0x）晚约一年——辅源披露日疑似反映最新修订而非首次
  披露（招行 2024/2025 年报 report_date_ms 完全相同的探针佐证），跨 vintage
  混比被守卫拦截。
- 辅侧未匹配=68 = fuyao 返回的其余报告期（主源仅有 12 期）。

## 3. etf_nav（#475，2026-09-30）

主源侧 ditto **无 Tushare fund_nav 摄取管道与存量**（EtfNavReader/Writer 在
但从未写入）。为完成端到端验收，在隔离根 `market/etf/nav/2026.parquet` 以
ad-hoc 脚本写入真实 Tushare fund_nav 值（9 黄金 ETF 中 7 只有 2026-09-30
净值；513100/513030 QDII 无当日 nav_date——两侧一致缺席）：

```text
主源行数: 7
对账统计: 主侧=7 辅侧=7 匹配=7 主侧未匹配=0 辅侧未匹配=0 主侧重复键=0 辅侧重复键=0 差异数=0
对账结果: passed=True 比较=可比 issues=0
```

- 7/7 unit_nav **逐位一致**（510300.SH 两侧均 4.4312，4 位小数）。
- 口径红线执行：fuyao adj_nav 为复权净值（官方明示≠累计净值），请求即不带
  `nav_type=adj`，不与主源 acc_nav 比较不折算——单位/累计口径差异以
  「不注册比较字段」显式单列（etf_nav.yml 注释留档）。
- 覆盖不足路径：目标日落辅源相对窗口（range=year）→ 该标的跳过记 warning；
  全部缺席 → not_comparable（单测覆盖）。
- 主源空库的真实行为：`主源 etf_nav 在 <date> 无存量数据(先摄取再对账)`。

## fuyao 端点契约实测备忘（写入实现注释/票评论）

| 端点 | 关键实测 |
| --- | --- |
| `/api/a-share-index/prices/historical` | 窗口基本受控但最新边缘返回窗外最近一根（10-03 查询得 09-30 bar）；约 5 年外日期空 item；`.SI` 未知代码 code=1002；价格 2 位小数 |
| `/api/a-share/financials/*` | 单标的、period=quarterly 含全部季报期；金额原币元（茅台精确到分、招行年报百万级舍入）；report_date_ms 疑似最新修订日非首次披露日 |
| `/api/fund/performance/nav` | 仅相对窗口（week…fyear）无按日寻址；unit_nav 4 位小数；nav_type=unit 可单取 adj_nav |

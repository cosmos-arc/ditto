# fuyao 真实 stock_daily 跨源对账证据（#395）

- 运行日期: 2026-10-03
- 对账交易日: 2026-09-29（开发根 stock_daily 最近成功交易日）
- 代码版本（HEAD SHA）: `60fee2948bff3081842b2168a51abc253506390c`（分支 codex/395-identity-history-fuyao，工作区含本票未提交改动）

## 命令

```bash
# FUYAO_API_KEY 取自仓库根 .env，经环境变量注入（应用不直接读 .env）
FUYAO_API_KEY="$FUYAO_API_KEY" \
DITTO_CONFIG_ROOT=/Users/chevy/Desktop/code/ditto \
DITTO_STATE_ROOT=/tmp/ditto395-reconcile \
DITTO_CACHE_ROOT=/tmp/ditto395-reconcile-cache \
uv run --no-sync python -m ditto_apps.cli.main ops reconcile 2026-09-29 --dataset stock_daily
```

## 复跑确认

2026-10-03 晚在本票全部改动（TDX 删除、身份反解迁移、lint 收口）之后复跑同一命令，输出逐字一致（主侧=10 辅侧=10 匹配=10 未匹配=0/0 重复键=0/0 差异数=0，exit=0）。

## 输出（原文）

```text
主源行数: 5562
对账统计: 主侧=10 辅侧=10 匹配=10 主侧未匹配=0 辅侧未匹配=0 主侧重复键=0 辅侧重复键=0 差异数=0
对账结果: passed=True 比较=可比 issues=0
exit=0
```

## 语义说明

- 主源（Tushare 存量 parquet）全市场 5562 行；黄金数据集过滤后 10 只股票进入比较
  （修复了 #395 前生产 handler 默认参数导致黄金集过滤从未注入的问题）。
- 辅源为 fuyao `/api/a-share/prices/historical` 逐标的原始日线（adjust=none），
  单位归一（股→手 ×100、元→千元 ×1000）在 fuyao source 内完成。
- 比较键 `instrument_id + trade_date`：辅源帧经 #395 来源映射反解
  （既有 fuyao 映射优先，缺失时按裸码前缀规则唯一匹配已注册 instrument，只读）。
- 匹配数 10 / 主辅侧未匹配 0 / 重复键 0 / 差异数 0 → 非空有效比较（匹配数 > 0）。
- 无差异 → quarantine/quality_comparison 不落差异行（符合仅在有差异时落盘的合同）。
- 除权日标记依赖 adj_factor 事件日检测（当日因子 ≠ 此前最近因子）；本日黄金集
  内无除权标的且无差异，标记位未触发。

## 运行环境（对账专用 state root）

对账运行在临时 state root `/tmp/ditto395-reconcile`：

- `metadata/metadata.sqlite` 为开发根 metadata 库的副本，并做**加列对齐**
  （`instrument_name_history`/`st_change_history` 增加 `source`/`observed_at`，
  `st_change_history` 增加 `(instrument_id, effective_from, source)` 唯一索引），
  使既有开发库与新 schema.sql 一致；开发根本身未写入。
- `market/` 为指向开发根 `data/market` 的符号链接（只读主源存量）。
- 真实数据写入仅限本对账运行（quarantine 目录）；主源与 fuyao 均为只读拉取。

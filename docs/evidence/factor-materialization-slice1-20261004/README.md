# #418 因子物化切片①验收证据（2026-10-04）

> 计算物化 → derived artifact → 研究/IC 读取最小链的**真实数据**端到端验收。
> 环境：本机 ditto-backend CLI（worktree `codex/418-factor-materialization-slice1`，
> 基线 main ab783304）；数据源 tushare 代理（t.xiaodefa.top）；state root
> `ditto-beta-state`（本日新建）。证据均为本机实测输出原文，未裁剪。

## 1. 真实摄取输入（#396 根）

前置命令（state root 为空目录起步）：

```console
$ export DITTO_STATE_ROOT=/Users/chevy/Desktop/code/ditto-beta-state \
      DITTO_CONFIG_ROOT=<repo> TUSHARE_TOKEN=…(根 .env 注入)
$ python -m ditto_apps.cli.main ingest metadata calendar 2026-05-06   # 396 行
$ python -m ditto_apps.cli.main ingest metadata basic stock           # 5,922 只
$ python -m ditto_apps.cli.main backfill market stock \
      --start 2026-05-06 --end 2026-10-04
# 总日期数: 104  成功: 5 chunk  失败: 0   （约 110 次 API 调用，代理额度内）
```

落盘事实（`market/stock/bars/2026.parquet`）：

| 事实 | 值 |
| --- | --- |
| 行数 | 574,898 |
| 交易日 | 104（2026-05-06 → 2026-09-30） |
| 证券数 | 5,585 |
| 列 | source_ticker, trade_date, knowledge_date, open, high, low, close, pre_close, volume, amount, pct_change |

> 首次回补未先摄取 `stock_basic`，ticker→instrument 解析后 0 行入库——已整
> state root 重来；该现象与 #418 无关（摄取链前置依赖顺序）。

## 2. 物化生产端（注册 → 计算 → derived artifact）

```console
$ python -m ditto_apps.cli.main ops factor-materialize momentum_1m \
      --start 2026-06-01 --end 2026-09-15
{
  "registration": {
    "derived_id": "momentum_1m", "version": 1,
    "action": "already_registered",
    "spec_hash": "15779e8992702d584c39a7f0bcab493de0cfb52c781955d7a6841a0ca796392f"
  },
  "run": {
    "run_id": "drv-0f3c76d708a3", "derived_id": "momentum_1m", "version": 1,
    "profile": "SERIES", "status": "SUCCESS",
    "rows_written": 420297, "partitions_written": ["2026"],
    "coverage_start": "2026-06-01", "coverage_end": "2026-09-15"
  }
}
```

产物身份绑定（文件 ↔ 目录 checkpoint ↔ 发布状态）：

```
sha256(derived/artifacts/series/momentum_1m/v1/2026.parquet)
  = dd27dadf1addcbbc4839308007242893003647c479bd8e1d2f89465961c0c238
derived_checkpoint   : partition=2026 status=complete rows=420297 checksum=dd27dadf1addcbbc…
derived_version      : status=published is_primary=1 is_online=1
derived_state        : active_version=1 coverage=2026-06-01..2026-09-15 total_rows=420297
```

幂等重跑（同窗口同身份，第二跑 SUCCESS `drv-2aaa73e6e9c0`，内容一致，
deterministic retry 校验通过；runs 计数 FAILED×1 + SUCCESS×2，FAILED 为下述
目录兼容修正前的首次尝试）。

## 3. 研究 / IC 读取（最高可观察入口）

```console
$ python -m ditto_apps.cli.main ops factor-ic momentum_1m \
      --start 2026-06-01 --end 2026-09-15 \
      --output docs/evidence/factor-materialization-slice1-20261004/factor-ic-momentum-1m.md
```

报告摘要（全文见同目录 `factor-ic-momentum-1m.md`）：

| 指标 | 值 |
| --- | --- |
| 交易日数 / 观测数 | 56 / 309,011 |
| **Rank IC mean** | **-0.1532**（ICIR -0.7135，t=-5.34，win rate 23.2%） |
| Pearson IC mean | -0.1422 |
| IC 一阶自相关 | 0.6826 |
| 平均换手 | 1.68% |

负 Rank IC 与 A 股 1 个月价格动量的反转经验一致（非空、量级合理的真实信号）。

## 4. 诚实状态反例（真实运行）

1. **无产物/身份未就绪 fail closed（首次尝试）**：目录兼容校验拒绝
   `schema_columns_mismatch, missing_columns=['instrument_id']`（存储目录以
   source_ticker 记录身份）→ 修复为身份别名豁免后放行，失败 run 留档。
2. **空跑拒绝且不动已发布产物**：lookback 不足窗口
   `--start 2026-05-06 --end 2026-05-08` →
   `物化失败: minimal DQ failed … failed_checks=('value_has_computable_rows',)`；
   重验 sha256 仍为 `dd27dadf…238`（字节未动）。
3. **读侧门禁单测反例**（`packages/features/tests/unit/` +
   `packages/application/tests/unit/process/materialization/`）：
   draft 版本拒读、PAYLOAD_COMMITTED/在途 tmp 分区拒读、checksum 漂移拒读、
   注册 spec_hash 漂移拒绝、空 artifact 评估 `MATERIALIZED_INPUT_MISSING`。

## 5. 修复的真实链缺陷（本切片暴露并修复）

- 存储目录身份列（source_ticker）与供数契约身份列（instrument_id）语言差
  （catalog_dependency_validation 身份别名规则）。
- 评估链 date/ISO 字符串 dtype 失配：评估器 `prepare_data` 统一归一到 date
  （此前仅夹具形态可跑通，与 #398 设计 §1 判断一致）。

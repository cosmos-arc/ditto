# Phase 2 Part 06: ParquetDataFeed

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 DataFeed 的 parquet 读取器 — 从 parquet 文件构建 Slice

**Architecture:** ParquetDataFeed 实现 DataFeed Protocol，从 parquet 文件读取 OHLCV 数据，构建 MarketSnapshot 字典，组装 Slice。使用 Polars 读取 parquet。

**Design Doc:** v3 §6.2 (DataFeed)

**Prerequisite:** Part 05 (DataFeed Protocol + Slice + MarketSnapshot)

---

## 任务清单

- [ ] Task 6.1: `ParquetDataFeed.__init__()` `[S]`
  - 验收: 接收 parquet 文件路径 + instrument_id 列名映射; 初始化时预加载交易日列表
  - 文件: `packages/core/src/ditto_core/backtest/data_feed.py`

- [ ] Task 6.2: `ParquetDataFeed.trading_days()` `[S]`
  - 验收: 从数据中提取去重排序的交易日列表
  - 文件: `packages/core/src/ditto_core/backtest/data_feed.py`

- [ ] Task 6.3: `ParquetDataFeed.get_slice(date)` `[M]`
  - 验收:
    - 读取指定日期的所有标的 OHLCV → 构建 MarketSnapshot 字典
    - 构建 Slice(trade_date, step_time, bars, benchmark_close?)
    - 缺失标的处理: 跳过（不包含在 bars 中）
    - 无数据日期: 返回空 bars 的 Slice
  - 文件: `packages/core/src/ditto_core/backtest/data_feed.py`

- [ ] Task 6.4: 包导出更新 `[S]`
  - 验收: backtest/__init__.py 导出 ParquetDataFeed
  - 文件: `packages/core/src/ditto_core/backtest/__init__.py`

- [ ] Task 6.5: 单元测试 `[M]`
  - 文件: `packages/core/tests/unit/backtest/test_data_feed_unit.py`
  - 场景:
    - 读取测试 parquet → Slice 数据正确
    - trading_days 去重排序
    - 缺失标的处理 → 不在 bars 中
    - benchmark_close 正确读取

---

## 文件清单

```
packages/core/src/ditto_core/backtest/
└── data_feed.py               # [更新] 追加 ParquetDataFeed

packages/core/tests/unit/backtest/
└── test_data_feed_unit.py     # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```

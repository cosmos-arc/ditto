---
last_synced: 2026-06-04
---

# Data Agent 指南

## 定位

数据平台 — 统一管理数据获取、存储、查询和 PIT（Point-in-Time）安全。

## 核心模块

| 模块 | 职责 |
|------|------|
| storage/ | CQRS 读写分离（Reader/Writer），按业务域组织 |
| services/ | 域服务（market/metadata/fundamental/macro/capital/source） |
| sources/ | 外部数据源接入（Tushare/FRED/TDX） |
| quality/ | 数据质量引擎（L1-L4 检查器） |
| ingestion/ | 摄入服务（游标/日志/冻结/质量记录） |
| runtime/ | 运行时基础设施（SQL 引擎/冻结管理/ID 分配） |
| models/ | 数据模型定义 |

## 依赖规则

### 允许

- data → kernel ✅
- data → platform ✅（仅 foundation）

### 禁止

- data → strategy/portfolio/risk/execution/backtest/analysis/application/apps ❌

## 关键约束

- 外部调用者禁止直接实例化 Reader/Writer，必须通过 Domain Service
- 写入自动触发 DQ 检查（L1 技术校验 + L2 业务规则）
- PIT 安全：查询时透明注入时间过滤器，防止数据泄漏
- 数据源：Tushare（A 股行情/基本面/资金）、FRED（宏观/商品）、TDX（本地数据）

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。

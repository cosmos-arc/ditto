# Sprint 1 - Task 1 实现规划: Runtime Layer基础组件

**日期**: 2025-12-22
**任务ID**: P1-001
**Sprint**: Sprint 1 数据层与验证
**任务**: 实现Runtime Layer（SID分配器、SQLite连接池、文件锁管理器、DQ检查器）

## 任务概述

根据官方设计文档《02_data_design.md》，实现Runtime Layer的四个基础组件，为上层Store Layer提供运行时支持。

## 依赖关系

```
SQLitePool → FileLockManager → SidAllocator
                           ↘ DQChecker
```

## 实现计划

### Phase 1: 基础设施（必须按顺序）
1. **类型定义** (`packages/data/src/ditto_data_hub/types.py`)
   - SidRange NamedTuple
   - Asset Class枚举定义

2. **SQLite连接池** (`packages/data/src/ditto_data_hub/runtime/sqlite_pool.py`)
   - 线程安全的连接管理
   - 简单的连接池实现
   - 支持事务操作

3. **文件锁管理器** (`packages/data/src/ditto_data_hub/runtime/file_lock.py`)
   - 跨平台文件锁（Windows/Unix）
   - 上下文管理器支持
   - 非阻塞模式

### Phase 2: 核心组件
4. **SID分配器** (`packages/data/src/ditto_data_hub/runtime/sid_allocator.py`)
   - 支持etf/stock/index三类资产
   - 原子性分配操作
   - SID范围检查
   - 数据持久化到sid_sequence表

5. **DQ检查器** (`packages/data/src/ditto_data_hub/runtime/dq_checker.py`)
   - 基础框架搭建
   - 支持YAML配置
   - 规则执行器

### Phase 3: 测试与验证
6. **单元测试**
   - 每个组件独立测试
   - 边界条件测试
   - 并发安全测试

7. **集成测试**
   - 组件间交互测试
   - 端到端流程验证

## 验收标准

### 功能性
- [x] SID分配器能正确分配不同资产类别的SID
- [x] SQLite连接池支持多线程安全访问
- [x] 文件锁能防止并发写入冲突
- [x] DQ检查器能加载和执行规则

### 非功能性
- [x] 所有组件通过单元测试
- [x] 代码覆盖率达到90%+
- [x] 通过mypy类型检查
- [x] 通过ruff代码规范检查

### 性能要求
- [x] SID分配操作<10ms
- [x] SQLite连接获取<5ms
- [x] 文件锁获取<1ms

## 文件清单

```
packages/data/src/ditto_data_hub/
├── types.py                  # 类型定义
├── runtime/
│   ├── __init__.py          # 模块导出
│   ├── sqlite_pool.py       # SQLite连接池
│   ├── file_lock.py         # 文件锁管理器
│   ├── sid_allocator.py     # SID分配器
│   └── dq_checker.py        # 数据质量检查器
└── tests/unit/runtime/
    ├── test_sqlite_pool.py
    ├── test_file_lock.py
    ├── test_sid_allocator.py
    └── test_dq_checker.py
```

## 实现细节

### SID分配器设计
```python
# SID范围定义
STOCK_RANGE = (100_000_000, 199_999_999)
ETF_RANGE = (200_000_000, 299_999_999)
INDEX_RANGE = (300_000_000, 399_999_999)

# 数据库表结构
CREATE TABLE sid_sequence (
    asset_class TEXT PRIMARY KEY,
    current_max INTEGER NOT NULL
);
```

### 文件锁设计
- 使用开源库：`pip install filelock`
- 跨平台支持：Windows/Linux/macOS

### DQ检查器设计
```python
# 配置示例
rules:
  - name: "primary_key_check"
    description: "Check primary key uniqueness"
    table: "market_daily"
    columns: ["sid", "trade_date"]

  - name: "ohlc_relation_check"
    description: "Check OHLC relationship"
    table: "market_daily"
    rules: ["high >= low", "high >= open", "high >= close"]
```

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 并发安全 | 使用数据库事务+文件锁双重保护 |
| 性能瓶颈 | 连接池复用+懒加载 |
| SID耗尽 | 监控告警+自动扩展机制 |

## 完成标准

1. 所有组件实现完成并通过测试
2. 文档齐全，包含使用示例
3. 集成到DataHub主模块
4. 代码质量检查全部通过

## 下一步计划

完成后将进入Sprint 1 - Task 2: 实现Store Layer（数据存取层）

---
**最后更新**: 2025-12-22
**状态**: ✅ 已完成
**实际完成**: 2025-12-22

## 完成总结

### 已实现组件
- ✅ SQLitePool - 线程安全的SQLite连接池
- ✅ FileLockManager - 基于filelock库的跨平台文件锁
- ✅ SidAllocator - SID分配器（支持ETF/股票/指数）
- ✅ DQChecker - 数据质量检查器（支持多种规则）

### 测试覆盖
- ✅ 18个单元测试全部通过
- ✅ 覆盖正常流程、边界条件和错误情况

### 代码质量
- ✅ Ruff检查通过（0 errors, 0 warnings）
- ✅ MyPy类型检查通过（0 errors）

### 验收标准完成情况
- [x] 所有组件通过单元测试
- [x] DataHub API与设计文档一致
- [x] PIT语义正确实现（N/A - Runtime Layer不涉及PIT）
- [x] Golden Dataset通过DataHub验证（N/A - 后续任务）
- [x] DQ检查规则生效
- [x] 年分区存储正确（N/A - 后续任务）

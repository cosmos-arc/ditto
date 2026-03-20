# 业界参考与对标

本文档总结了设计统一特征/因子引擎时参考的业界最佳实践和产品。

---

## 1. 表达式引擎与算子系统

### WorldQuant Brain

**特点**：
- 统一表达式引擎，支持 100+ 算子
- 任意 TS/CS 嵌套
- Alpha101 因子库标准

**Ditto 借鉴**：
- 命名风格（ts_rank, cs_zscore）
- 算子分类体系
- TS/CS 混合表达式支持

**参考链接**：https://platform.worldquantbrain.com/

### BigQuant

**特点**：
- 自动分层执行（TS 阶段 → CS 阶段）
- 可视化因子构建
- AutoStrategy 自动化策略生成

**Ditto 借鉴**：
- 自动分层执行策略
- TS(CS(x)) 和 CS(TS(x)) 语义处理

**参考链接**：https://bigquant.com/

### DolphinDB

**特点**：
- `context by` 分组语法
- 内置时序函数
- 流批一体架构

**Ditto 借鉴**：
- JIT 函数缓存思路
- 查询级 CSE 优化

**参考链接**：https://dolphindb.com/

### Qlib (微软)

**特点**：
- 表达式缓存（Spec 级 + CSE 级）
- Point-in-Time 正确性
- 模型全流程管理

**Ditto 借鉴**：
- 两级缓存设计
- PIT 一致性保证
- 日历数据处理

**参考链接**：https://github.com/microsoft/qlib

---

## 2. 特征存储与版本管理

### Feast

**特点**：
- Feature View 版本化
- Point-in-Time 正确性
- 在线/离线存储分离

**Ditto 借鉴**：
- Feature View 版本化概念
- PIT 查询语义
- 存储分层设计

**参考链接**：https://feast.dev/

### MLflow Model Registry

**特点**：
- Stage 指针机制（Production/Staging/Archived）
- 版本血缘追踪
- 可复现性保证

**Ditto 借鉴**：
- 因子版本管理中的 primary 指针
- 状态流转（draft → active → archived）

**参考链接**：https://mlflow.org/

### Tecton

**特点**：
- 声明式特征定义
- 增量计算支持
- 实时特征服务

**Ditto 借鉴**：
- Spec 声明式定义
- 增量计算边界推导

**参考链接**：https://www.tecton.ai/

---

## 3. 技术指标与因子库

### TA-Lib

**特点**：
- 150+ 技术指标
- C 语言实现，性能优秀
- 行业标准参考实现

**Ditto 借鉴**：
- 技术指标实现参考
- 算子语义对齐

**参考链接**：https://ta-lib.org/

### WorldQuant Alpha101

**特点**：
- 101 个公式化因子
- 学术界广泛验证
- 因子表达式标准

**Ditto 借鉴**：
- 算子覆盖范围（支持 80%+ Alpha101）
- 表达式语法设计

**参考论文**：*101 Formulaic Alphas* by Zura Kakushadze

### Barra 因子模型

**特点**：
- 风险因子体系
- 因子正交化
- 行业/风格中性化

**Ditto 借鉴**：
- 中性化算子设计
- 分组中性化支持

---

## 4. 存储与计算引擎

### DuckDB

**特点**：
- 列式存储
- 哈希表缓存
- 查询级 CSE 优化

**Ditto 借鉴**：
- 表达式缓存策略
- 列式存储优化

**参考链接**：https://duckdb.org/

### QuestDB

**特点**：
- O3 列存储（时序优化）
- DEDUP 去重机制
- SAMPLE BY 降采样

**Ditto 借鉴**：
- Hot 层时序存储选型
- 预聚合设计

**参考链接**：https://questdb.io/

### Kvrocks

**特点**：
- Redis 协议兼容
- RocksDB 持久化
- 低内存占用

**Ditto 借鉴**：
- 增量状态存储选型
- Checkpoint 管理

**参考链接**：https://github.com/apache/kvrocks

---

## 5. 标准化与中性化

### 业界主流方案

| 平台 | 标准化流程 | 说明 |
|------|-----------|------|
| WorldQuant | Rank → ZScore | 业界主流 |
| BigQuant | ZScore | 简化版 |
| MSCI Barra | 正交化 + ZScore | 风险模型 |
| **Ditto** | **Rank → ZScore** | **业界主流** |

### 标准化算子

1. **cs_rank** - 截面排名
2. **cs_zscore** - 截面标准化
3. **winsorize** - 缩尾处理
4. **neutralize** - 中性化（行业/市值）
5. **group_rank/group_zscore** - 组内标准化

---

## 6. 增量计算

### 业界趋势

| 厂商 | 方案 | 特点 |
|------|------|------|
| Two Sigma | 增量因子研究 | 秒级回测迭代 |
| Citadel | 多周期策略框架 | 流批统一 |
| BigQuant | AutoStrategy | 自动化因子挖掘 |

### 增量边界策略

1. **Watermark + Lookback** - 回退预热
2. **Invalidation Set** - 精确失效边界
3. **Full Day Flag** - CS 算子整日重算

---

## 7. PIT 一致性

### 业界实践

| 系统 | PIT 实现 |
|------|---------|
| Qlib | knowledge_date 列 |
| Feast | entity_dataframe + point_in_time |
| **Ditto** | effective_from/effective_to |

### PIT 语义

```text
as_of_date in [effective_from, effective_to)
```

- `effective_from`: 数据生效日期
- `effective_to`: 数据失效日期（null 表示当前有效）

---

## 8. 资源与成本参考

### 云存储成本（AWS us-east-1）

| 存储类型 | 成本 | 用途 |
|---------|------|------|
| S3 Standard | $0.023/GB/月 | 冷数据 |
| EBS gp3 | $0.08/GB/月 | 热数据 |

### 本地存储估算

| 组件 | 数据量 | 成本估算 |
|------|--------|---------|
| QuestDB | ~1GB | 本地 SSD |
| Kvrocks | ~11MB | 本地 SSD |
| Parquet | ~10GB | 本地 HDD |

---

## 参考链接汇总

### 开源项目

- [Qlib](https://github.com/microsoft/qlib) - 微软量化投资平台
- [Feast](https://feast.dev/) - 特征存储
- [MLflow](https://mlflow.org/) - ML 生命周期管理
- [DolphinDB](https://dolphindb.com/) - 时序数据库
- [QuestDB](https://questdb.io/) - 时序数据库
- [Kvrocks](https://github.com/apache/kvrocks) - Redis 兼容存储
- [TA-Lib](https://ta-lib.org/) - 技术指标库

### 商业平台

- [WorldQuant Brain](https://platform.worldquantbrain.com/)
- [BigQuant](https://bigquant.com/)
- [Tecton](https://www.tecton.ai/)

### 学术论文

- *101 Formulaic Alphas* by Zura Kakushadze
- *The Barra US Equity Model* by MSCI

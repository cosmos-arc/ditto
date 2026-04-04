# storage

数据存储层 — SQLite 与 Parquet 双存储，CQRS 读写分离，按业务领域组织。

## 目录结构

```
storage/
├── base/             # BaseReader/BaseWriter 抽象, ParquetStore, SQLiteStore
├── metadata/         # 元数据域（instrument, identity, industry, calendar, universe）
├── market/           # 行情域（stock/etf/index: bars, status, adj, nav, constituent）
├── fundamental/      # 基本面域（financial, corporate, forecast）
├── capital/          # 资本域（margin, pledge, valuation, futures, index_composition）
├── macro/            # 宏观域（indicator, metadata）
├── features/         # 特征域（技术指标）
├── factors/          # 因子域（因子信号）
├── runtime/          # 运行时 store
├── schemas/          # Schema 定义
└── sqlite_client.py  # SQLite 客户端
```

## CQRS 模式

每个 store 拆分为 `*_reader.py` 和 `*_writer.py`：

| 组件 | 职责 | 方法 |
|------|------|------|
| Reader | 查询（无副作用，可并发） | `read()`, `count()`, `get_*()` |
| Writer | 写入/删除（需并发控制） | `write()`, `delete()` |

## 访问规则

- **interfaces 层**：通过 Domain Service 间接访问，禁止直接实例化 Reader/Writer
- **Service 层**：组合 Reader + Writer 封装业务逻辑

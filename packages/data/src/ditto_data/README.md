# ditto_data

数据访问层 — 统一的数据模型、存储、服务与数据源适配。

## 架构定位

```
interfaces → ditto_data → ditto_kernel, ditto_infra
```

提供 instrument_id 标识体系、Point-in-Time 语义、DQ 检查与 CQRS 存储访问。

## 目录结构

```
ditto_data/
├── config/           # DataRootConfig, DQ 规则配置
├── di/               # DI 注册
├── helpers/          # 纯函数工具（adjustment, pit）
├── ingestion/        # 数据摄取工具
├── models/           # 数据模型（50+ record 类型）
├── provider.py       # DataProvider Protocol
├── errors.py         # 错误类型
├── events.py         # 数据事件
├── quality/          # DQ 引擎 + 检查器
├── query/            # 查询模型（空，待填充）
├── runtime/          # 运行时支持（SQLite, PIT, Freeze）
├── services/         # 领域服务（7 个门面 + strategy + audit）
├── sources/          # 数据源适配器（Tushare, FRED, TDX）
├── storage/          # 存储层 — Reader/Writer CQRS，按领域组织
└── utils/            # 通用工具
```

## 关键约定

- **CQRS**：storage 按 `*_reader.py`（查询）/ `*_writer.py`（写入）分离
- **Service 门面**：interfaces 层通过 Service 访问数据，禁止直接使用 Reader/Writer
- **PIT 安全**：所有因子数据必须包含 `knowledge_date`
- **双存储**：Parquet（分析型年分区）+ SQLite（事务型）
- **原子写入**：使用 `atomic_write()` 确保完整性

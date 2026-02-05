# Ditto 架构重构与代码问题修复计划（一次性落地）

## 1. 目标与原则
- **一次性重构**，不保留兼容层
- **配置只在 Port 层读取**（唯一入口）
- **引擎中心 + 模块可插拔 + 事件驱动**
- **DataFrame 作为领域语言**
- **Foundation 与 Infra 整合但强分区**

## 2. 现存问题清单（来自代码审查）
### 2.1 配置与初始化
- config/{env}/*.env 被读取但键名不匹配，实际被忽略（extra="ignore"）
- Settings/Config 多入口（Foundation/DataHub/Core/Port 各自读取 env）
- Observability profile 与 environment 双源冲突，生产可能落入开发预设

### 2.2 可观测性
- shutdown() 判断逻辑导致 provider shutdown 不执行
- tracing_enabled/metrics_enabled 参数未生效
- tracing exporter/sampler 未配置
- 业务指标定义混入基础层

### 2.3 依赖与边界
- DataCache 直接依赖 M.*，未 init 会异常
- util.checksum 含数据集业务排序规则
- Notification 属于适配器却放在基础层
- DQSeverity 放在 foundation，core 反向依赖基础层

### 2.4 文档与版本
- README 版本与包版本不一致
- 模板命名/说明与实现不一致

## 3. 一次性改造总体方案
### 3.1 架构重组（目录与边界）
目标目录结构以 `docs/designs/quant-architecture-alignment.md` 为准。

关键迁移：
- foundation → infra/common
- notification → infra/adapters/notification
- observability → infra/observability
- 业务指标 → telemetry catalog
- core → domain
- datahub 拆分为 engine/data/trading/research（或保留 datahub 包内分区）

### 3.2 配置系统统一（Port 唯一入口）
- 所有 BaseSettings → BaseModel/dataclass
- config/{env}/*.env 仅由 apps/port/config 读取
- 内层严禁读取环境变量/文件
- DI 注入配置对象

### 3.3 Observability 重构
- 修复 shutdown 逻辑（直接检查 shutdown 方法）
- tracing/metrics 开关必须生效
- 引入 Telemetry Catalog（纯定义）
- 观测实现只负责映射与导出
- 业务指标移出基础层

### 3.4 依赖清理与边界修复
- DataCache 改为注入 MetricsPort / NoOpMetrics
- util.checksum 迁移到 data/datahub
- DQSeverity 移动到 domain/quality
- 删除全局单例入口（get_paths/get_config_coordinator）

## 4. 具体执行步骤（一次性落地顺序）
1) 创建新目录结构（engine/data/trading/research/infra/telemetry/domain）
2) 迁移基础设施代码与适配器
3) 配置统一：重写 AppConfig + Port config loader
4) 迁移指标定义到 telemetry catalog
5) 改造 observability 实现
6) 重构 DataHub 与引擎分层
7) 清理全局单例与隐式 env 读取
8) 更新测试与文档

## 5. 验收标准
- 单一配置入口（仅 apps/port/config）
- 内层禁止 env/file 读取
- 观测系统开关生效、shutdown 正常
- 业务指标在 telemetry catalog 单点定义
- 基础层不含业务语义
- 引擎与数据管线插件化

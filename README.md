# Ditto: 量化投资系统

## 项目简介

Ditto 是一个面向 A 股市场的个人量化投资系统，专注于 ETF 行业轮动策略，采用工业级标准开发，追求长期稳定 Alpha。

### 核心特性

- **行业轮动策略**: 基于 Regime 识别的 ETF 行业轮动
- **多因子模型**: 相对强弱、估值、波动率、拥挤度等因子
- **严格风控**: 三层 Kill Switch 机制，回撤速度检测
- **双引擎回测**: Fast 向量化引擎 + Production 事件驱动引擎
- **数据质量**: 多源校验，PIT 安全，复权分离存储
- **ML 增强**: 机器学习因子权重学习（Phase 3+）

### 当前开发状态

**Phase 0.5-1 进行中**：
- ✅ Sprint 1: 数据层与验证（已规划，基于官方02_data_design.md）
- 🔄 Sprint 2: 核心引擎实现（基于官方03_engine_design.md）
- 📋 Sprint 3: 回测与风控（基于官方08_risk_constitution.md）

### 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web UI        │    │   FastAPI       │    │   Core Engines  │
│   (Next.js)     │◄──►│   Application   │◄──►│   - Regime      │
│                 │    │   Services      │    │   - Factor      │
│ - 仪表盘        │    │                 │    │   - Rotation    │
│ - 回测分析      │    │ - RotationSvc   │    │   - Backtest    │
│ - 调仓计划      │    │ - RiskSvc       │    │   - Risk        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   External      │    │   Data Layer    │
                       │   APIs          │◄──►│   - DataHub      │
                       │                 │    │   - Accessor     │
                       │ - Tushare       │    │   - Store       │
                       │ - MINIQMT       │    │   - Runtime      │
                       │                 │    │   - PIT Safe     │
                       └─────────────────┘    └─────────────────┘
```

## 快速开始

### 环境要求

- Python 3.12+
- Pixi (包管理器)
- Windows/Linux/macOS

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd ditto
   ```

2. **安装依赖**
   ```bash
   pixi install
   ```

3. **配置环境变量**

   系统采用双层环境架构，配置文件按环境分组在 `config/` 目录：

   ```bash
   # 配置文件结构（按需修改）
   config/
   ├── development/    # 开发环境配置
   ├── testing/        # 测试环境配置
   └── production/     # 生产环境配置
   ```

   设置运行时环境（默认为 development）：
   ```bash
   export DITTO_ENV=development  # Linux/macOS
   # 或
   set DITTO_ENV=development     # Windows
   ```

   **注意**：Tushare token 需要通过 keyring 或 `~/.ditto/secrets.toml` 配置
   ```bash
   # 方式1: Keyring（推荐）
   pixi run -e dev python -c "
   import keyring
   keyring.set_password('ditto', 'tushare', 'your_token_here')
   "
   ```

4. **初始化数据库**
   ```bash
   pixi run python scripts/init_db.py
   ```

5. **启动服务**
   ```bash
   pixi run server
   ```

### 开发命令

```bash
# 代码质量检查
pixi run lint          # 运行 ruff 检查
pixi run lint --fix    # 自动修复问题
pixi run fmt           # 格式化代码
pixi run type          # 运行 pyright 类型检查

# 测试
pixi run test              # 运行所有测试
pixi run test --unit       # 只运行单元测试
pixi run test --integration # 只运行集成测试
pixi run test --fast       # 快速测试（跳过慢速）
pixi run test tests/test_specific.py  # 运行特定测试

# 快速验证（开发时）
pixi run check         # lint + fmt + type + test --fast

# 完整检查（CI 用）
pixi run ci            # 完整的 CI 检查

# 数据更新
pixi run update-data    # 更新市场数据

# 开发模式启动
pixi run dev            # 启动开发服务器（热重载）
pixi run server         # 启动生产服务器
```

## 项目结构

```
ditto/
├── apps/
│   ├── server/                 # FastAPI 后端服务
│   │   ├── src/
│   │   │   ├── api/           # API 路由
│   │   │   ├── services/      # 应用服务
│   │   │   ├── models/        # 数据模型
│   │   │   └── main.py        # 启动入口
│   │   └── tests/             # 服务器测试
│   └── web/                   # Next.js 前端 (Phase 1+)
├── packages/
│   ├── core/                  # 核心业务逻辑
│   │   ├── src/
│   │   │   ├── engine/        # 核心引擎
│   │   │   ├── factors/       # 因子系统
│   │   │   ├── strategy/      # 策略实现
│   │   │   ├── backtest/      # 回测引擎
│   │   │   ├── risk/          # 风控引擎
│   │   │   └── portfolio/     # 组合管理
│   │   └── tests/             # 核心模块测试
│   ├── datahub/               # 数据访问层
│   │   ├── src/
│   │   │   ├── hub.py         # DataHub 统一入口
│   │   │   ├── accessors/     # 业务聚合
│   │   │   ├── stores/        # 数据存储
│   │   │   └── runtime/       # 运行时支持
│   │   └── tests/             # 数据层测试
│   └── foundation/           # 共享模块
│       ├── src/
│       │   ├── config/        # 配置管理
│       │   ├── logging/       # 日志系统
│       │   └── types/         # 类型定义
├── data/                      # 数据存储
│   ├── meta/                  # SQLite 元数据
│   ├── stock_daily/           # 股票日线
│   ├── etf_daily/             # ETF 日线
│   └── freezes/               # 冻结点
├── docs/                      # 项目文档
│   ├── design/                # 设计文档
│   └── sprints/               # Sprint 计划
├── scripts/                   # 工具脚本
└── tests/                     # E2E 测试
```

## 开发路线图

### Phase 0: 环境与数据打底 ✅
- [x] 项目脚手架搭建
- [x] 开发环境配置（pixi + pre-commit）
- [x] 基础依赖安装

### Phase 0.5: 数据质量验证 🔄
- [x] Sprint 1: 数据层实现（DataHub + Repository）
  - 实现统一数据入口（DataHub Facade）
  - 实现SID标识体系
  - 实现Point-in-Time语义
  - Golden Dataset验证

### Phase 1: 回测闭环与调仓计划
- [ ] Sprint 2: 核心引擎实现
  - RegimeEngine（自适应阈值）
  - FactorEngine（4个核心因子）
  - Strategy框架（多策略协调）
  - PortfolioManager（组合管理）

- [ ] Sprint 3: 回测与风控
  - FastBacktester（向量化）
  - ProductionBacktester（事件驱动）
  - 对齐测试（误差<0.1%）
  - RiskEngine（三级Kill Switch）

### Phase 2: 实盘接入（规划中）
- [ ] BrokerAdapter实现
- [ ] 纸面交易验证
- [ ] 实盘小资金测试

### Phase 3: ML增强（规划中）
- [ ] 因子权重学习
- [ ] 可转债策略
- [ ] 多策略组合

## 核心设计文档

本项目严格遵循官方设计文档：

### 数据层设计
- **《02_data_design.md》** - 数据层设计文档（v2.0 Final）
  - DataHub统一入口设计
  - SID标识体系（内部唯一ID）
  - Repository模式（业务聚合）
  - Point-in-Time语义

### 引擎设计
- **《03_engine_design.md》** - 引擎设计文档（v2.0 Final）
  - RegimeEngine（自适应阈值）
  - FactorEngine（健康度监控）
  - 策略框架抽象
  - 双回测引擎架构

### 风险设计
- **《08_risk_constitution.md》** - 风险宪法
  - 三级Kill Switch（10%/18%/20%）
  - 回撤速度检测
  - 仓位控制规则

## Sprint规划

详细的Sprint计划请查看 `docs/sprints/` 目录：

### Sprint 1: 数据层与验证
- **时间**: Week 1-2
- **目标**: 实现数据层基础
- **文档**: [sprint-01-data-layer.md](docs/sprints/sprint-01-data-layer.md)

### Sprint 2: 核心引擎实现
- **时间**: Week 3-4
- **目标**: 实现核心引擎和策略框架
- **文档**: [sprint-02-core-engines.md](docs/sprints/sprint-02-core-engines.md)

### Sprint 3: 回测与风控
- **时间**: Week 5-6
- **目标**: 完成回测系统和风控
- **文档**: [sprint-03-backtest-risk.md](docs/sprints/sprint-03-backtest-risk.md)

## 策略说明

### ETF 行业轮动策略

**核心思路**: 基于市场 Regime 状态，在不同行业/主题 ETF 之间进行轮动配置

**因子体系**:
- 相对强弱 (RS): 相对沪深300的超额收益
- 估值 (Value): 行业指数PE/PB分位数
- 波动率 (Vol): 价格波动率惩罚
- 拥挤度 (Crowding): 成交额和溢价率指标

**调仓规则**:
- 月度调仓为主，触发型调仓为辅
- Top N 选择，等权或 Score 加权
- 最小调仓阈值，降低交易成本

### 风险管理

**三层 Kill Switch**（严格按风险宪法）：
1. **Level 1** (≥10%回撤): 停止新开仓，回撤<8%自动恢复
2. **Level 2** (≥18%回撤): 强制减仓50%，需人工确认
3. **Level 3** (≥20%回撤): 强制清仓，需策略重构评审

**仓位限制**（Regime驱动）：
| Regime | 总仓位 | 单票上限 |
|--------|--------|----------|
| Bull   | 70-90% | 15% |
| Osc    | 50-70% | 12% |
| Bear   | 10-40% | 10% |

## 测试

### Monorepo 测试目录结构

项目采用 Monorepo 最佳实践，测试文件位于各个模块内部：

```
ditto/
├── apps/port/tests/           # 服务器应用测试
├── packages/core/tests/         # 核心模块测试
├── packages/datahub/tests/      # 数据层测试
├── packages/foundation/tests/   # 基础模块测试
└── tests/                       # E2E 测试和集成测试
```

### 运行测试

```bash
# 运行所有测试
pixi run test

# 运行特定模块测试
pixi run test packages/core/tests/
pixi run test apps/port/tests/

# 运行单元测试（并行）
pixi run test --unit

# 运行集成测试（串行）
pixi run test --integration

# 生成覆盖率报告
pixi run test --cov

# 运行pre-commit检查
pre-commit run --all-files
```

## CI/CD

### 本地检查

提交代码前必须运行:

```bash
# 安装 pre-commit 钩子
pixi run pre-commit-install

# 运行所有检查
pre-commit run --all-files

# 或使用 pixi 任务
pixi run ci            # 完整 CI 检查
pixi run check         # 快速验证（开发时）
```

### GitHub Actions

项目配置了以下 GitHub Actions:

- **CI**: 每次 PR 和 push 运行代码质量检查和测试
- **Deploy**: 自动部署到 staging/production

**CI 检查包括**:
- Ruff (lint + format)
- Pyright (type check)
- Pytest (unit + integration tests)
- **覆盖率要求: 80%** (通过 Codecov 精细化管理)

### Codecov 覆盖率

- PR 中自动显示覆盖率变化报告
- 各模块差异化目标:
  - core-strategy: 90%
  - core-engine: 85%
  - datahub: 85%
  - foundation/server: 80%
- 访问 https://codecov.io/gh/[username]/ditto 查看详细报告

详见: [.github/workflows/README.md](.github/workflows/README.md)

## 配置说明

### 环境变量

```bash
# API 服务配置
HOST=0.0.0.0
PORT=8000
SECRET_KEY=your_secret_key_here

# 数据存储
DITTO_DATA_DIR=data

# 风险管理
KILL_SWITCH_ENABLED=true
```

### Tushare Token 配置

**注意**：Tushare token 不再支持通过环境变量配置。请使用以下方式之一：

1. **Keyring（推荐）**:
   ```bash
   pixi run -e dev python -c "
   import keyring
   keyring.set_password('ditto', 'tushare', 'your_token_here')
   "
   ```

2. **~/.ditto/secrets.toml**:
   ```toml
   [tushare]
   token = "your_token_here"
   ```

## 文档

详细文档请查看 `docs/design/` 目录：

- `01_system_design.md` - 系统设计总览
- `02_data_design.md` - 数据设计
- `03_engine_design.md` - 引擎设计
- `04_deployment_topology.md` - 部署拓扑设计
- `05_observability.md` - 可观测性设计
- `06_roadmap.md` - 开发路线图
- `07_research_playground.md` - 研究环境使用说明
- `08_risk_constitution.md` - 风险宪法
- `09_data_quality_design.md` - 数据质量设计
- `10_data_ingestion_scheduler_design.md` - 数据摄取任务设计



## 贡献

### 开发流程

1. Fork 项目
2. 创建功能分支
3. 编写代码和测试（TDD）
4. 运行质量检查
5. 提交 Pull Request

### 代码规范

- 严格遵循官方设计文档
- 使用 ruff 进行格式化和检查
- 使用 pyright 进行类型检查
- 所有新功能需要测试覆盖
- 遵循 TDD 开发流程

### Commit规范

```
<type>(<scope>): <task-id> <description>

# 示例
feat(data): P0-001 implement DataHub facade
test(engine): P0-002 add RegimeEngine tests
```

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 项目仓库: [GitHub](https://github.com/your-username/ditto)
- 问题反馈: [Issues](https://github.com/your-username/ditto/issues)
- 文档: [Wiki](https://github.com/your-username/ditto/wiki)

## 免责声明

本系统仅用于学习和研究目的，不构成投资建议。使用者需要：

1. 充分理解量化交易风险
2. 自行承担投资损失
3. 遵守相关法律法规
4. 在实盘交易前进行充分测试

**风险提示**: 量化交易存在亏损风险，过去业绩不代表未来表现。

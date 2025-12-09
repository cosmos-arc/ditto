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
                       │   APIs          │◄──►│   - DuckDB      │
                       │                 │    │   - SQLite      │
                       │ - Tushare       │    │   - Data Quality│
                       │ - AkShare       │    │   - PIT Safe     │
                       │ - MiniQMT       │    └─────────────────┘
                       └─────────────────┘
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
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入 TUSHARE_TOKEN 等配置
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
pixi run format         # 格式化代码
pixi run typecheck      # 运行 mypy 类型检查

# 测试
pixi run test           # 运行所有测试
pixi run test tests/test_specific.py  # 运行特定测试

# 数据更新
pixi run update-data    # 更新市场数据

# 开发模式启动
pixi run server         # 启动开发服务器
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
│   │       ├── unit/          # 单元测试
│   │       └── integration/   # 集成测试
│   └── web/                   # Next.js 前端 (Phase 1+)
│       └── src/
│           ├── app/           # 页面路由
│           ├── components/    # UI 组件
│           └── stores/        # 状态管理
├── packages/
│   ├── core/                  # 核心业务逻辑
│   │   ├── src/
│   │   │   ├── data/          # 数据访问层
│   │   │   ├── engine/        # 核心引擎
│   │   │   ├── strategy/      # 策略实现
│   │   │   └── portfolio/     # 组合管理
│   │   └── tests/             # 核心模块测试
│   │       └── unit/          # 单元测试
│   └── foundation/            # 共享模块
│       ├── src/
│       │   ├── config/        # 配置管理
│       │   ├── types/         # 类型定义
│       │   └── contracts/     # 数据契约
│       └── tests/             # 基础模块测试
│           └── unit/          # 单元测试
├── data/                      # 数据存储
│   ├── duckdb/               # 分析型数据库
│   └── sqlite/               # 事务型数据库
├── logs/                      # 日志文件
├── docs/                      # 项目文档
├── scripts/                   # 工具脚本
├── tests/                     # E2E 测试和集成测试
│   └── e2e/                   # 端到端测试
├── .env.example               # 环境变量模板
├── pixi.toml                 # 依赖配置
├── pyproject.toml            # Python 项目配置
└── README.md                 # 项目说明
```

## 开发阶段

### Phase 0: 环境与数据打底 (当前阶段) - 37.5% 完成
- [x] 环境配置和依赖管理
- [x] 项目目录结构搭建
- [x] 本地包 editable 配置
- [x] Tushare 和 AkShare 数据源接入
- [x] 日志配置完成
- [ ] 数据库初始化
- [ ] 数据采集和存储实现
- [ ] 数据质量验证实现
- [ ] API 服务完善
- [ ] 核心模块实现
- [ ] 基础启动脚本

> 详细任务跟踪请查看: [phase0_tasks.md](phase0_tasks.md)

### Phase 0.5: 数据质量验证期
- [ ] Golden Dataset 选取和验证
- [ ] 手工数据核验
- [ ] 数据质量基线报告

### Phase 1: 回测闭环与调仓计划
- [ ] 核心引擎实现
- [ ] 双回测引擎
- [ ] 风控引擎
- [ ] 调仓计划生成
- [ ] Web UI 基础框架

### Phase 2: 实盘接入
- [ ] BrokerAdapter 接口实现
- [ ] MiniQMT 对接
- [ ] 纸面交易验证

### Phase 3: ML 增强与扩展
- [ ] ML 因子权重学习
- [ ] 可转债策略
- [ ] 多策略组合管理

## 配置说明

### 环境变量

主要配置项（详见 `.env.example`）：

```bash
# 数据源配置
TUSHARE_TOKEN=your_token_here
AKSHARE_ENABLE=true

# 数据库配置
DUCKDB_PATH=./data/duckdb/ditto.duckdb
SQLITE_PATH=./data/sqlite/ditto.sqlite

# API 服务配置
HOST=0.0.0.0
PORT=8000
SECRET_KEY=your_secret_key_here

# 风险管理配置
KILL_SWITCH_ENABLED=true
MAX_SINGLE_POSITION_WEIGHT=0.15
```

### 数据源

1. **Tushare Pro** (主数据源)
   - 需要 Pro 账户和 Token
   - 提供 ETF 日线、复权因子等数据

2. **AkShare** (备用数据源)
   - 免费开源数据源
   - 用于数据校验和降级

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

**三层 Kill Switch**:
1. Level 1: 日亏损 2% 或周亏损 5%
2. Level 2: 回撤 15% 或 3日快速回撤 5%
3. Level 3: 回撤 20% 或紧急情况 25%

**仓位限制**:
- 单只证券最大 15%
- 单行业最大 30%
- 最小现金比例 5%

## 测试

### Monorepo 测试目录结构

项目采用 Monorepo 最佳实践，测试文件位于各个模块内部：

```
ditto/
├── apps/server/tests/           # 服务器应用测试
│   ├── unit/                   # 单元测试
│   └── integration/            # 集成测试
├── packages/core/tests/         # 核心模块测试
│   └── unit/                   # 单元测试
├── packages/foundation/tests/   # 基础模块测试
│   └── unit/                   # 单元测试
└── tests/                       # E2E 测试和集成测试
    └── e2e/                    # 端到端测试
```

### 运行测试

```bash
# 运行所有测试
pixi run test

# 运行特定模块测试
pixi run test packages/core/tests/unit/
pixi run test apps/server/tests/

# 运行特定测试文件
pixi run test packages/core/tests/unit/test_data_service.py

# 运行特定标记的测试
pixi run test -m unit          # 只运行单元测试
pixi run test -m integration   # 只运行集成测试
pixi run test -m e2e          # 只运行端到端测试
pixi run test -m "not slow"   # 跳过慢速测试

# 生成覆盖率报告
pixi run test --cov=packages --cov=apps --cov-report=html
```

### 测试分类

1. **单元测试**: 各模块内部的功能测试
2. **集成测试**: 模块间的接口测试
3. **端到端测试**: 完整业务流程测试
4. **对齐测试**: Fast vs Production 回测引擎对齐
5. **Golden Dataset 测试**: 基于固定数据集的回归测试

## 文档

详细文档请查看 `docs/` 目录：

- `00_overview.md` - 系统总览
- `01_system_design_v1.md` - 系统设计
- `02_data_design.md` - 数据设计
- `03_engine_design.md` - 引擎设计
- `06_roadmap_v1.md` - 开发路线图
- `09_risk_constitution.md` - 风险宪法

## 贡献

### 开发流程

1. Fork 项目
2. 创建功能分支
3. 编写代码和测试
4. 运行质量检查
5. 提交 Pull Request

### 代码规范

- 使用 ruff 进行格式化和检查
- 使用 mypy 进行类型检查
- 所有新功能需要测试覆盖
- 遵循项目架构设计

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

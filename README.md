# Ditto: 量化投资系统

**版本**: v0.5.0
**最后更新**: 2026-01-23
**状态**: 🔄 开发中

## 概要

Ditto 是一个面向 A 股市场的个人量化投资系统，专注于 ETF 行业轮动策略，采用工业级标准开发，追求长期稳定 Alpha。

## 核心功能

- **行业轮动策略**: 基于 Regime 识别的 ETF 行业轮动
- **多因子模型**: 相对强弱、估值、波动率、拥挤度等因子
- **严格风控**: 三层 Kill Switch 机制，回撤速度检测
- **双引擎回测**: Fast 向量化引擎 + Production 事件驱动引擎
- **数据质量**: 多源校验，PIT 安全，复权分离存储
- **ML 增强**: 机器学习因子权重学习（Phase 3+）

## 架构

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
   export ENVIRONMENT=development  # Linux/macOS
   # 或
   set ENVIRONMENT=development     # Windows
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
pixi run type          # 运行 basedpyright 类型检查

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
│   ├── port/                  # FastAPI 后端服务
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

## 相关文档

- [设计文档](docs/design/README.md) - 系统架构设计
- [Sprint 规划](docs/sprints/README.md) - 迭代计划
- [ADR](docs/adr/README.md) - 架构决策记录

## 变更记录

### v0.5.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善文档结构说明
- 更新开发命令说明

### v0.4.0 (2025-12-27)
**新增**
- Sprint 1 P0 任务全部完成
- DataHub Facade 实现
- SqlEngine 实现

### v0.1.0 (2025-12-08)
**新增**
- 初始项目结构
- 基础依赖配置
- 核心设计文档

## 免责声明

本系统仅用于学习和研究目的，不构成投资建议。使用者需要：

1. 充分理解量化交易风险
2. 自行承担投资损失
3. 遵守相关法律法规
4. 在实盘交易前进行充分测试

**风险提示**: 量化交易存在亏损风险，过去业绩不代表未来表现。

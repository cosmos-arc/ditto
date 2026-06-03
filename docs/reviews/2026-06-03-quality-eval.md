# Ditto 质量评估报告 2026-06-03

> 评估模式: --full | 评估时间: 2026-06-03 | 项目阶段: 架构整改完成，V1 功能开发中

## 综合评分

```
              测试质量
               4.4★ 🟢
                 |
    代码 4.5★ ──┼── 3.6★ 运维
    🟢          |         🟡
    架构 4.6★ ──┼── 4.1★ 领域
    🟢          |         🟢
                 |
              工程流程
               3.7★ 🟡

    综合评分: 4.23 / 5.0 ★ 🟢 优秀
```

**综合评分: 4.23 / 5.0 ★** (加权)

| 维度 | 评分 | 评级 | 变化 |
|------|------|------|------|
| ① 代码质量 | 4.47/5.0 ★ | 🟢 优秀 | — (首次评估) |
| ② 架构质量 | 4.60/5.0 ★ | 🟢 优秀 | — |
| ③ 测试质量 | 4.40/5.0 ★ | 🟢 优秀 | — |
| ④ 工程流程 | 3.70/5.0 ★ | 🟡 合格 | — |
| ⑤ 运维质量 | 3.60/5.0 ★ | 🟡 合格 | — |
| ⑥ 领域特有 | 4.10/5.0 ★ | 🟢 优秀 | — |

**加权公式**: code(0.20) + arch(0.25) + test(0.15) + eng(0.10) + ops(0.15) + domain(0.15)
**计算**: 4.47×0.20 + 4.60×0.25 + 4.40×0.15 + 3.70×0.10 + 3.60×0.15 + 4.10×0.15 = **4.23**

---

## 各维度详情

### ① 代码质量 — 🟢 优秀 (4.47★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| C1 | 类型安全 | ★★★ | ✅ pass | basedpyright strict 0 errors; type:ignore 0 处; TYPE_CHECKING 0 处 | — |
| C2 | 代码复杂度 | ★★★ | ✅ pass | ruff C901 零违规；无函数超过复杂度阈值 10 | — |
| C3 | 函数体大小 | ★★★ | ✅ pass | ruff PLR0915 零违规；无函数超过行数阈值 | — |
| C4 | 代码重复度 | ★★☆ | ⚠️ warning | lineage/catalog sqlite_store 有 ~12 行重复辅助函数 (_partition_keys_json)；整体重复度估计 < 1% | 提取到共享模块消除拷贝 |
| C5 | 代码规范合规 | ★★☆ | ✅ pass | ruff check All checks passed! 零错误零警告 | — |
| C6 | 参数数量控制 | ★★☆ | ⚠️ warning | 24 处 PLR0913 noqa（DI 工厂/编排函数），占生产 noqa 的 28.6% | 收敛为 dataclass 减少裸参数 |
| C7 | 命名与可读性 | ★★☆ | ✅ pass | 抽查 5 文件命名精准；CQRS 分层命名严格；模块 docstring 全覆盖 | — |
| C8 | 注释质量 | ★☆☆ | ✅ pass | 注释解释"为什么"而非"是什么"；noqa 附带原因说明 | — |
| C9 | 死代码/未使用导入 | ★☆☆ | ✅ pass | ruff F401/F811/F841 零违规 | — |
| C10 | 依赖合规 | ★★★ | ⚠️ warning | import json 3 处（lineage/catalog sqlite_store + post_ingest）；import pandas 0 处 | 评估禁止规则豁免或统一到 orjson |

**关键指标**:
- 生产代码: 122,173 行 | 测试代码: 189,016 行
- noqa 密度: 0.69/1000 行 (优秀 < 1.0)
- type:ignore: 0 | TYPE_CHECKING: 0
- ruff: 0 errors | basedpyright: 0 errors

### ② 架构质量 — 🟢 优秀 (4.60★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| A1 | 依赖方向合规 | ★★★ | ✅ pass | 37 importlinter 合约全通过 | — |
| A2 | 包间耦合度 | ★★★ | ✅ pass | 实际依赖图与文档高度一致；每个包依赖严格受控 | — |
| A3 | 模块内聚性 | ★★★ | ✅ pass | 12 包各承载单一领域能力；子模块职责清晰 | — |
| A4 | 组件独立性 | ★★★ | ✅ pass | acyclicity 通过；TYPE_CHECKING 0 处；无循环依赖 | — |
| A5 | API 表面积控制 | ★★☆ | ⚠️ warning | 10/12 包有 __all__；backtest 和 application 缺少 | 添加缺失的 __all__ 定义 |
| A6 | 抽象层级一致性 | ★★☆ | ✅ pass | 同层模块抽象层级一致；application CQRS 四域互斥 | — |
| A7 | Fitness Functions | ★★☆ | ✅ pass | 37 合约 + 17 类 arch-smells + CI audit job | — |
| A8 | 技术债管控 | ★★☆ | ⚠️ warning | 有分类追踪（maturity manifest）；缺统一量化仪表板 | 建立自动化 tech debt 报告 |
| A9 | 架构文档一致性 | ★☆☆ | ✅ pass | 13 个 CLAUDE.md + 5 篇 ADR；arch-smells 检测陈旧引用 | — |

**关键指标**:
- 架构合约: 37/37 通过 | 循环依赖: 0 | TYPE_CHECKING: 0
- arch-smells 脚本: 17 类检查 | CI audit job: ✅
- __all__ 覆盖: 10/12 包

### ③ 测试质量 — 🟢 优秀 (4.40★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| T1 | 分支覆盖率 | ★★★ | ✅ pass | --cov-branch + --cov-fail-under=80 CI 强制执行 | — |
| T2 | 测试分层 | ★★★ | ✅ pass | unit=663, integration=68, e2e=10；单元占比 89.5% | — |
| T3 | 测试独立性 | ★★★ | ✅ pass | 默认并行执行 (-n auto)；serial 仅 20 个有合理原因 | — |
| T4 | 测试确定性 | ★★★ | ✅ pass | 零 flaky test；无 xfail；SimulatedClock 消除时间依赖 | — |
| T5 | 测试命名与可读性 | ★★☆ | ✅ pass | 抽查 5 文件命名优秀；每个测试有中文 docstring | — |
| T6 | 核心路径覆盖 | ★★★ | ✅ pass | execution 611 函数、risk 207 函数、backtest 758 函数 | — |
| T7 | 断言质量 | ★★☆ | ✅ pass | pytest.approx 676 处；pytest.raises 905 处；snapshot 2070 处 | — |
| T8 | Mock 使用合理性 | ★★☆ | ✅ pass | 平均 3.3 行 mock/文件；仅隔离外部 Protocol | — |
| T9 | 测试执行速度 | ★☆☆ | ✅ pass | 8008 tests in 35.01s；平均 4.4ms/test | — |
| T10 | 边界/异常测试 | ★★☆ | ⚠️ warning | risk 无 integration 测试；2 个 skip 集成测试需修复 | 为 risk 增加 integration 层 |

**关键指标**:
- 测试函数: 8,497 | 测试文件: 741 | 测试/代码比: 1.55x
- 单元测试占比: 89.5% | 执行时间: 35s (fast mode)
- Flaky test: 0 | 覆盖率门禁: 80% branch

### ④ 工程流程 — 🟡 合格 (3.70★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| P1 | 部署频率 | ★ | ⚠️ warning | 月均 12.4 PR 但节奏放缓；无持续部署 | 启用 staging 自动部署 |
| P2 | 变更前置时间 | ★ | ⚠️ warning | 大型 PR 前置时间长；平均 16K LOC/PR | 拆分为更小原子 PR |
| P3 | 变更失败率 | ★ | ✅ pass | 100 提交中零 revert；fix 类仅 7% | — |
| P4 | 恢复时间 | ★ | ⚠️ warning | 无生产部署历史；无回滚机制 | 建立回滚能力基线 |
| P5 | 返工率 | ★ | ✅ pass | 返工率 ~7% 远低于 15% 精英线 | — |
| P6 | 审查覆盖率 | ★★★ | ✅ pass | 全部 PR 通过 GitHub 机制合并 | — |
| P7 | PR 大小控制 | ★★☆ | ❌ fail | 48% PR > 5000 LOC；平均 16K LOC；最大 113K LOC | 设定上限 1000/3000 LOC |
| P8 | 审查响应时间 | ★★☆ | ⚠️ warning | 个人项目无外部审查；AI 审查 skill 可补充 | 引入轻量外部审查 |
| P9 | 审查质量 | ★★★ | ✅ pass | 5 维审查清单 + PR template + Skills 支持 | — |
| P10 | 审查清单 | ★★☆ | ✅ pass | 15 项 DoD checklist + 16 pre-commit 钩子 | — |
| P11 | Lint 门禁 | ★ | ✅ pass | ruff 21 规则集 + CI lint job | — |
| P12 | 类型检查门禁 | ★ | ✅ pass | basedpyright strict + CI type-check job | — |
| P13 | 测试门禁 | ★ | ✅ pass | --cov-fail-under=80 + CI test-unit job | — |
| P14 | 架构门禁 | ★ | ✅ pass | 37 合约 + CI audit job | — |
| P15 | 格式化门禁 | ★ | ✅ pass | ruff format + CI format check | — |

**关键指标**:
- PR 总数: 62 | 平均 PR 大小: 16,042 LOC
- PR 大小分布: 11% ≤400 LOC, 48% >5,000 LOC
- Pre-commit 钩子: 16 | CI workflows: 3
- CI 门禁: 5/5 全通过 | 架构合约: 37/37

### ⑤ 运维质量 — 🟡 合格 (3.60★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| O1 | 结构化日志 | ★★★ | ✅ pass | loguru JSON 格式；40+ 结构化事件点；Webhook 脱敏 | — |
| O2 | 业务指标度量 | ★★★ | ⚠️ warning | OTel 框架完整(23 指标)；缺回测耗时/管道延迟/PnL | 补充核心业务指标 |
| O3 | 分布式追踪 | ★★☆ | ⚠️ warning | @traced 30+ 处(data 层)；backtest/execution 覆盖不足 | 关键路径补充 trace |
| O4 | 容错与重试 | ★★★ | ⚠️ warning | tenacity 仅覆盖 2 外部 API；无内部管道重试/降级/circuit breaker | 扩展重试 + 降级策略 |
| O5 | 数据持久性 | ★★★ | ⚠️ warning | UnitOfWork 完善；缺 WAL 模式/备份策略/Parquet 原子写入 | 启用 WAL + 建立备份 |
| O6 | 性能基准 | ★★☆ | ⚠️ warning | 衍生引擎 benchmark 有(9 工作负载)；未覆盖回测/管道核心路径 | 扩展基准覆盖 |
| O7 | 安全态势 | ★★★ | ⚠️ warning | 密钥管理好；API 无认证/授权；CORS 过于宽松 | 添加 JWT 认证 + 收紧 CORS |
| O8 | 配置管理 | ★★☆ | ✅ pass | 4 级环境隔离；6 个 env 文件/环境；get_environment() 统一 | — |
| O9 | 资源效率 | ★★☆ | ✅ pass | SQLitePool 连接管理完善；Polars LazyFrame 延迟计算 | — |
| O10 | 灾备能力 | ★☆☆ | ⚠️ warning | checkpoint 机制存在；无备份/恢复 SOP | 建立备份策略 + 恢复文档 |

**关键指标**:
- OTel 指标: 23 定义 | @traced: 30+ 处
- 重试覆盖: 2/∞ 客户端 | 环境隔离: 4 级
- 安全钩子: 3 (detect-private-key, gitleaks, check-added-large-files)

### ⑥ 领域特有 — 🟢 优秀 (4.10★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| D1 | 回测确定性 | ★★★ | ✅ pass | random_seed=42; ReplayValidator 全字段对比；golden baseline | — |
| D2 | 数据完整性 | ★★★ | ✅ pass | 4 级 DQ 检查(L1-L4)；QualityEngine Protocol 解耦；游标管理 | — |
| D3 | 前视偏差防护 | ★★★ | ✅ pass | _rolling() 通过 shift(1) 实现 PIT 安全；TimeSlice 严格控制 | — |
| D4 | 策略隔离 | ★★★ | ✅ pass | strategy 零导入 execution/data/features；SignalStore Protocol | — |
| D5 | 风控独立性 | ★★★ | ✅ pass | risk 仅依赖 kernel+portfolio；import boundary 测试验证 | — |
| D6 | 订单生命周期 | ★★★ | ✅ pass | 7 状态 FSM；frozen dataclass；ExecutionAuditService timeline | — |
| D7 | 因子计算正确性 | ★★★ | ⚠️ warning | IC/回归/暴露分析有；缺端到端数值交叉验证 | 建立表达式 vs 手写参考回归 |
| D8 | 策略参数可审计 | ★★☆ | ✅ pass | StrategySpecRecord 版本管理；RunManifest 记录参数 | — |
| D9 | 市场数据时效性 | ★★☆ | ⚠️ warning | freshness_sla_hours 字段有；缺端到端延迟监控告警 | 建立 SLA 监控仪表板 |
| D10 | 回测-实盘一致性 | ★★☆ | ⚠️ warning | TradingLoop Protocol 统一；LiveLoop 未实现 | LiveLoop 里程碑中验证复用 |

**关键指标**:
- 架构合约: 37/37 | 前视偏差: 0 违规
- 策略隔离: 0 违规 | 风控独立性: 0 违规
- 订单 FSM: 7 状态 | DQ 检查: L1-L4 四级

---

## Top 10 改进项

| # | 维度 | 评价项 | 优先级 | 建议 |
|---|------|--------|--------|------|
| 1 | 运维 O7 | 安全态势 | P0 CRITICAL | 为生产 API 添加 JWT/API Key 认证；收紧 CORS 策略；添加 rate limiting |
| 2 | 工程 P7 | PR 大小控制 | P1 HIGH | 设定 PR 上限（普通 1000 LOC，架构 3000 LOC）；拆分巨型 PR |
| 3 | 运维 O5 | 数据持久性 | P1 HIGH | 启用 SQLite WAL 模式；建立定期备份策略；Parquet 原子写入 |
| 4 | 领域 D7 | 因子计算正确性 | P2 MEDIUM | 建立表达式引擎 vs 手写 Polars 参考的数值一致性回归测试 |
| 5 | 运维 O2 | 业务指标度量 | P2 MEDIUM | 补充回测耗时/管道延迟/策略 PnL 核心业务指标 |
| 6 | 代码 C10 | 依赖合规 | P2 MEDIUM | 3 处 import json → 统一到 platform json_types 或增加 SQLite 序列化豁免 |
| 7 | 测试 T10 | 边界/异常测试 | P2 MEDIUM | 为 risk 模块增加 integration 测试；修复 2 个 skip 的集成测试 |
| 8 | 运维 O3 | 分布式追踪 | P3 LOW | 在 EngineLoop/ExecutionStep/StrategyStep 补充 @traced |
| 9 | 运维 O4 | 容错与重试 | P3 LOW | 扩展重试覆盖至内部管道；实现数据源降级策略 |
| 10 | 架构 A5 | API 表面积控制 | P3 LOW | 为 backtest 和 application 添加 __all__ 定义 |

---

## 项目基线数据

### 质量门禁
- ✅ Lint: ruff 全通过 (0 errors, 0 warnings)
- ✅ Type: basedpyright strict 0 errors
- ✅ Test: 8,008 passed, 25 skipped
- ✅ Arch: 37/37 contracts kept

### 代码规模
- 生产代码: 122,173 行 (932 文件)
- 测试代码: 189,016 行 (741 文件, 8,497 函数)
- 测试/代码比: 1.55x

---

## 附录

- 评价框架: docs/plans/2026-06-02-software-quality-evaluation-framework.md
- 评价标准: .claude/skills/ditto-quality-eval/references/
- 业界标准: ISO/IEC 25010:2023, CISQ/ISO 5055, SIG/TÜViT, SQALE, ATAM, DORA, SPACE

# 维度③：测试质量评估

> 基于 ISO 25010 可测试性、SQALE 可测试性指数、FURPS+ 可支持性

---

## 评价项

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| T1 | **分支覆盖率** | ★★★ | ≥ 80%（Ditto 门禁硬性要求） | pytest-cov |
| T2 | **测试分层** | ★★★ | 单元/集成/E2E 分离，比例合理（金字塔模型） | 目录结构审查 |
| T3 | **测试独立性** | ★★★ | 无测试间依赖，可任意顺序/并行执行 | pytest 执行验证 |
| T4 | **测试确定性** | ★★★ | 无 flaky test，相同输入始终相同结果 | CI 历史记录 |
| T5 | **测试命名与可读性** | ★★☆ | 测试名表达意图（given/when/then 风格） | Code Review |
| T6 | **核心路径覆盖** | ★★★ | execution/risk/backtest 100% 覆盖 | 覆盖率报告 |
| T7 | **断言质量** | ★★☆ | 断言精确，验证关键业务不变量 | Code Review |
| T8 | **Mock 使用合理性** | ★★☆ | 仅隔离外部依赖，不过度 mock | Code Review |
| T9 | **测试执行速度** | ★☆☆ | 单元测试套件 < 5 min，快速测试 < 2 min | CI 时间统计 |
| T10 | **边界/异常测试** | ★★☆ | 覆盖边界条件、异常路径、错误恢复 | 测试审计 |

## 量化阈值

| 指标 | 🟢 优秀 | 🟡 合格 | 🔴 需改进 |
|------|---------|---------|----------|
| 分支覆盖率 | ≥ 85% | ≥ 80% | < 80% |
| 核心模块覆盖率 | ≥ 90% | ≥ 85% | < 80% |
| Flaky test 比例 | 0% | < 1% | ≥ 1% |
| 测试/代码比（行数） | ≥ 2.0x | ≥ 1.5x | < 1.0x |
| 单元测试占比（金字塔） | ≥ 70% | ≥ 60% | < 50% |
| 快速测试耗时 | < 2 min | < 5 min | > 10 min |

## 检查命令

```bash
# 测试运行（快速模式）
pixi run -e dev test --unit --fast 2>&1 | tail -30

# 覆盖率
pixi run -e dev test --unit --fast -- -q 2>&1 | grep -E "TOTAL|coverage|passed|failed"

# 测试文件统计
find packages/ -name "test_*.py" -o -name "*_test.py" | wc -l

# 测试代码行数
find packages/ -name "test_*.py" -o -name "*_test.py" | xargs wc -l | tail -1

# 生产代码行数
find packages/ -name "*.py" ! -path "*/tests/*" | xargs wc -l | tail -1

# 测试目录结构（分层检查）
find packages/ -type d -name "tests" | head -20

# 集成测试 vs 单元测试比例
find packages/ -path "*/tests/*" -name "test_*.py" | xargs grep -l "integration\|@pytest.mark.integration" | wc -l
find packages/ -path "*/tests/*" -name "test_*.py" | wc -l

# flaky 检测标记
grep -r "flaky\|@pytest.mark.flaky\|retry\|xfail" packages/ --include="*.py" | grep -v ".pyc" | head -20
```

## 评分规则

- T1（覆盖率）为硬性项：fail → 整个维度最高 2★
- T4（确定性）为硬性项：fail → 整个维度最高 3★
- 其余项按 pass/warning/fail 正常计分
- 测试/代码比 < 1.0x → 额外扣 0.5★

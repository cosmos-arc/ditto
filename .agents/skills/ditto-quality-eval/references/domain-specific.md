# 维度⑥：领域特有质量评估（量化平台专属）

> 基于量化金融行业实践、Ditto 项目特定需求（AGENTS.md 约束）

---

## 评价项

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| D1 | **回测确定性** | ★★★ | 相同参数+数据 → 相同结果，零随机性泄漏 | 确定性测试 |
| D2 | **数据完整性** | ★★★ | 数据管道无泄漏、无重复、时间戳连续 | 数据质量检查 |
| D3 | **前视偏差防护** | ★★★ | 所有时间窗口操作 `closed="left"` | ruff 规则 + Grep |
| D4 | **策略隔离** | ★★★ | strategy 不依赖 execution，信号与订单解耦 | arch-check |
| D5 | **风控独立性** | ★★★ | risk 可独立于 strategy/execution 工作 | 架构审查 |
| D6 | **订单生命周期完整性** | ★★★ | 从生成到成交完整审计链，无状态丢失 | 执行路径测试 |
| D7 | **因子计算正确性** | ★★★ | 因子编译/物化/评估结果可交叉验证 | 因子测试套件 |
| D8 | **策略参数可审计** | ★★☆ | 所有策略参数变更可追溯 | Git + 配置管理 |
| D9 | **市场数据时效性** | ★★☆ | 数据摄入延迟在可接受范围内 | 监控指标 |
| D10 | **回测-实盘一致性** | ★★☆ | 回测与实盘代码路径最大程度复用 | 架构审查 |

## 量化阈值

| 指标 | 🟢 优秀 | 🟡 合格 | 🔴 需改进 |
|------|---------|---------|----------|
| 回测确定性 | 100%（自动化测试验证） | 100%（手动验证） | 不确定 |
| 前视偏差规则覆盖 | 100%（ruff 规则） | 主要场景覆盖 | 无自动防护 |
| 策略↔执行隔离 | 0 违规（arch-check） | 0 违规 | > 0 违规 |
| 风控审计路径 | 完整可追溯 | 部分可追溯 | 不可追溯 |
| 数据质量门禁 | 自动化检查 + 告警 | 有检查 | 无检查 |

## 检查命令

```bash
# 前视偏差防护
grep -r "rolling_mean\|rolling.*closed\|\.shift\|\.rolling" packages/ \
  --include="*.py" | grep -v "closed=" | grep -v test | grep -v ".pyc" | head -20

# 策略↔执行隔离
grep -r "from.*execution.*import\|from.*strategy.*import" packages/strategy/ packages/execution/ \
  --include="*.py" | grep -v test | head -20

# 风控独立性
grep -r "from.*strategy.*import\|from.*execution.*import" packages/risk/ \
  --include="*.py" | grep -v test | head -10

# 数据质量相关代码
grep -r "data_quality\|quality_check\|validation" packages/data/ \
  --include="*.py" | grep -v test | wc -l

# 因子测试覆盖
find packages/features/ -path "*/tests/*" -name "test_*.py" | wc -l
find packages/features/ -name "*.py" ! -path "*/tests/*" | wc -l

# 回测确定性测试
grep -r "deterministic\|determinism\|reproducib" packages/backtest/ \
  --include="*.py" | head -10

# 架构约束检查（领域相关合约）
pixi run -e dev arch-check 2>&1 | grep -E "strategy|execution|risk|backtest" | head -20
```

## 评分规则

- D3（前视偏差）、D4（策略隔离）、D5（风控独立性）为硬性项：fail → 整个维度最高 2★
- D1（回测确定性）为关键项：fail → 扣 1.5★
- 其余项按 pass/warning/fail 正常计分
- 总分映射到 1-5 星

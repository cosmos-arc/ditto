# 维度①：代码质量评估

> 基于 ISO 25010 可维护性、SIG 8 大可度量属性、CISQ/ISO 5055 弱点计数

---

## 评价项

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| C1 | **类型安全** | ★★★ | basedpyright strict 零错误，无 `# type: ignore` | `pixi run -e dev type` |
| C2 | **代码复杂度** | ★★★ | 圈复杂度 < 10（多数）；> 25 的函数 < 2% | ruff C901 |
| C3 | **函数体大小** | ★★★ | 多数 < 50 行；> 100 行的函数 < 5% | ruff PLR0915 |
| C4 | **代码重复度** | ★★☆ | 重复代码 < 3% | jscpd / SonarQube |
| C5 | **代码规范合规** | ★★☆ | ruff 全规则通过，零 warning/error | `pixi run -e dev lint` |
| C6 | **参数数量控制** | ★★☆ | 函数参数 ≤ 5；> 7 个的 < 2% | ruff PLR0913 |
| C7 | **命名与可读性** | ★★☆ | 命名语义清晰、风格一致 | Code Review |
| C8 | **注释质量** | ★☆☆ | 注释解释"为什么"而非"是什么" | Code Review |
| C9 | **死代码/未使用导入** | ★☆☆ | 零死代码、零未使用导入 | ruff F401/F811 |
| C10 | **依赖合规** | ★★★ | 无禁止依赖（pandas/json/pip 等） | ruff + 自定义检查 |

## 量化阈值

| 指标 | 🟢 优秀 (SIG 4-5★) | 🟡 合格 (SIG 3★) | 🔴 需改进 (<3★) |
|------|-------------|-----------|-------------|
| 类型检查通过率 | 100% strict 零错误 | 100% basic 零错误 | 有错误 |
| `# type: ignore` 数量 | 0 | 0（硬性要求） | > 0 |
| 平均圈复杂度 | < 5 | < 10 | > 15 |
| 高复杂度函数占比 (>25) | < 0.5% | < 2% | > 5% |
| 超长函数占比 (>100行) | < 1% | < 5% | > 10% |
| 重复代码率 | < 2% | < 3% | > 5% |
| 代码规范违规 | 0 | 0（CI 门禁硬性） | > 0 |
| `# noqa` 密度 | < 1/1000 行 | < 3/1000 行 | > 5/1000 行 |

## 检查命令

```bash
# 类型安全
pixi run -e dev type 2>&1 | tail -20

# 代码规范
pixi run -e dev lint 2>&1 | tail -20

# 复杂度统计（ruff 输出）
pixi run -e dev ruff check --select C901 --statistics packages/ 2>&1 | tail -20

# 函数长度统计
pixi run -e dev ruff check --select PLR0915 --statistics packages/ 2>&1 | tail -20

# 参数数量统计
pixi run -e dev ruff check --select PLR0913 --statistics packages/ 2>&1 | tail -20

# 未使用导入
pixi run -e dev ruff check --select F401,F811 packages/ 2>&1 | tail -20

# 禁止依赖检查
pixi run -e dev grep -r "import pandas\|import json\b" packages/ --include="*.py" | head -20

# type:ignore 计数
pixi run -e dev grep -r "# type: ignore" packages/ --include="*.py" | wc -l

# noqa 计数
pixi run -e dev grep -r "# noqa" packages/ --include="*.py" | wc -l

# 生产代码行数
find packages/ -name "*.py" ! -path "*/tests/*" | xargs wc -l | tail -1
```

## 评分规则

- 每个 pass 项 → 满分（权重分）
- 每个 warning 项 → 权重分的 60%
- 每个 fail 项 → 0 分
- 总分 = Σ(各项得分) / Σ(各项满分) × 5.0 → 映射到 1-5 星

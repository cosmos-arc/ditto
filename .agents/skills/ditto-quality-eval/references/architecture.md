# 维度②：架构质量评估

> 基于 ATAM 质量属性评估、SIG 组件独立性、Fitness Functions 演化架构、ISO 25010 模块化/可重用性

---

## 评价项

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| A1 | **依赖方向合规** | ★★★ | `.importlinter` 全部合约通过 | `pixi run -e dev arch-check` |
| A2 | **包间耦合度** | ★★★ | outgoing dependency ≤ 规定上限（SIG: < 20 incoming/module） | import 分析 |
| A3 | **模块内聚性** | ★★★ | 每个包只承载单一领域能力 | 架构审查 |
| A4 | **组件独立性** | ★★★ | 无循环依赖、无 TYPE_CHECKING 逃逸 | pyright + import-linter |
| A5 | **API 表面积控制** | ★★☆ | 每个包的 `__all__` 明确且最小化 | 代码审查 |
| A6 | **抽象层级一致性** | ★★☆ | 同层模块处于同一抽象层级 | 架构审查 |
| A7 | **Fitness Functions 覆盖** | ★★☆ | 关键架构属性有自动化守护 | CI pipeline 审查 |
| A8 | **技术债管控** | ★★☆ | 技术债可分类、可量化（SQALE < 5% = A 级） | SonarQube / 等效 |
| A9 | **架构文档一致性** | ★☆☆ | AGENTS.md 与实际代码依赖图一致 | 定期审计 |

## 量化阈值

| 指标 | 🟢 优秀 (4-5★) | 🟡 合格 (3★) | 🔴 需改进 (<3★) |
|------|-------------|-----------|-------------|
| 架构合约通过率 | 100% | ≥ 95% | < 95% |
| 跨包 TYPE_CHECKING | 0 处 | 0（硬性要求） | > 0 处 |
| 循环依赖 | 0 处 | 0（硬性要求） | > 0 处 |
| 公开 API 明确度 | 100% 包有 `__all__` | ≥ 80% | < 80% |
| 技术债比率 (SQALE) | < 5% (A级) | 5-10% (B级) | > 10% |
| 跨包 re-export 链深度 | ≤ 2 层 | ≤ 2（硬性要求） | > 2 层 |

## 检查命令

```bash
# 架构边界检查
pixi run -e dev arch-check 2>&1 | tail -30

# TYPE_CHECKING 使用检查
grep -r "TYPE_CHECKING" packages/ --include="*.py" | grep -v "test" | head -20

# 循环依赖（import-linter 已覆盖，辅助检查）
grep -r "from.*import" packages/ --include="*.py" | \
  python3 -c "
import sys, collections
deps = collections.defaultdict(set)
for line in sys.stdin:
    parts = line.strip().split(':')
    if len(parts) >= 2:
        pkg = parts[0].split('/')[1] if '/' in parts[0] else '?'
        deps[pkg].add(line)
# 简单检测双向导入
for a in deps:
    for b in deps:
        if a != b and any(a in x for x in deps[b]) and any(b in x for x in deps[a]):
            print(f'Potential circular: {a} <-> {b}')
"

# __all__ 覆盖率
for d in packages/*/; do
  pkg=$(basename $d)
  if [ -f "$d/src/__init__.py" ]; then
    has_all=$(grep -c "__all__" "$d/src/__init__.py" 2>/dev/null || echo "0")
    echo "$pkg: __all__=$has_all"
  elif [ -f "$d/__init__.py" ]; then
    has_all=$(grep -c "__all__" "$d/__init__.py" 2>/dev/null || echo "0")
    echo "$pkg: __all__=$has_all"
  fi
done

# re-export 链深度检查
grep -r "from.*import \*" packages/ --include="*.py" | grep -v test | head -20
```

## Fowler 技术债四象限

```
                    | Deliberate（有意）         | Inadvertent（无意）
--------------------|---------------------------|---------------------------
Prudent（审慎）      | "先上线，后重构"          | "现在理解了，但已太迟"
                    | （战略性捷径）              | （学习型债务，不可避免）
--------------------|---------------------------|---------------------------
Reckless（鲁莽）     | "没时间做设计"            | "什么是好设计？"
                    | （有意识的疏忽）           | （无知型混乱）
```

## 评分规则

- A1/A4 为硬性项：fail → 整个维度最高 2★
- 其余项按 pass/warning/fail 正常计分
- 总分映射到 1-5 星

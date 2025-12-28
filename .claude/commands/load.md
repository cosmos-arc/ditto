---
name: load
description: 手动加载 Ditto Skills
---

# /load 命令

手动加载指定的 Skill 文件。

## 用法

```
/load <skill-name>
/load all
```

## 可用的 Skills

| 简写 | 完整路径 |
|------|----------|
| `polars` | `.claude/skills/polars-guide/SKILL.md` |
| `engine` | `.claude/skills/engine-template/SKILL.md` |
| `factor` | `.claude/skills/factor-dev/SKILL.md` |
| `pit` | `.claude/skills/pit-guide/SKILL.md` |
| `risk` | `.claude/skills/risk-guide/SKILL.md` |
| `fastapi` | `.claude/skills/fastapi-guide/SKILL.md` |
| `obs` | `.claude/skills/observability/SKILL.md` |
| `backtest` | `.claude/skills/backtest-guide/SKILL.md` |
| `docs` | `.claude/skills/docs-guide/SKILL.md` |

## 示例

```
/load polars        → 加载 Polars 指南
/load pit risk      → 加载 PIT 和风控指南
/load all           → 加载所有核心 Skills (polars, pit, risk, engine)
```

## 执行动作

收到此命令后，立即使用 Read 工具读取对应的 SKILL.md 文件。

### /load all 加载列表
1. `.claude/skills/polars-guide/SKILL.md`
2. `.claude/skills/pit-guide/SKILL.md`
3. `.claude/skills/risk-guide/SKILL.md`
4. `.claude/skills/engine-template/SKILL.md`

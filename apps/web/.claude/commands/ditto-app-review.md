---
name: ditto-app-review
description: 并行代码审查
---

# /ditto-app-review 命令

使用 `superpowers:requesting-code-review` 并行审查，再用 `code-review:code-review` 最终审核。

## 规范参考

- **架构规范**: [architecture.md](../rules/architecture.md)
- **组件规范**: [components.md](../rules/components.md)
- **SKILLS**: [`CLAUDE.md`](../../CLAUDE.md)

## 输入

`$ARGUMENTS` - 文件/目录/范围

## 审查范围

| 用法 | 范围 |
|------|------|
| `/ditto-app-review` | 当前 git diff / PR |
| `/ditto-app-review src/` | 指定目录 |
| `/ditto-app-review file.tsx` | 指定文件 |
| `/ditto-app-review --all` | 全量审查 |
| `/ditto-app-review --focus {type}` | 单维度审查 |

## 并行审查（6 维度）

| 维度 | 检查项 |
|------|--------|
| **架构** | Feature 边界、依赖方向 |
| **类型** | `any` 使用、类型完整性 |
| **规约** | 编码规范、.claude/rules |
| **组件** | shadcn 复用、CVA 模式 |
| **质量** | biome、tsc、测试覆盖 |
| **样式** | Tailwind 合规、Design Token |

## 单维度

```bash
/ditto-app-review --focus architecture
/ditto-app-review --focus types
/ditto-app-review --focus quality
```

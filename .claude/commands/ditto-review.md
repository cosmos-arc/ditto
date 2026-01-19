---
name: ditto-review
description: 并行代码审查
---

# /ditto-review 命令

使用 `superpowers:requesting-code-review` 并行审查，再用 `code-review:code-review` 最终审核。

## 规范参考

- **架构规范**: [`.claude/rules/architecture.md`](.claude/rules/architecture.md)
- **PIT 规范**: [`.claude/rules/pit.md`](.claude/rules/pit.md)
- **SKILLS**: [`.claude/CLAUDE.md`](.claude/CLAUDE.md#⚠️-skills-执行规则)

## 输入

`$ARGUMENTS` - 文件/目录/范围

## 审查范围

| 用法 | 范围 |
|------|------|
| `/ditto-review` | 当前 git diff / PR |
| `/ditto-review src/` | 指定目录 |
| `/ditto-review file.py` | 指定文件 |
| `/ditto-review --all` | 全量审查 |
| `/ditto-review --focus {type}` | 单维度审查 |

## 并行审查（6 维度）

| 维度 | 检查项 |
|------|--------|
| **架构** | 分层职责、依赖方向 |
| **PIT** | `closed="left"`、knowledge_date |
| **规约** | 编码规范、.claude/rules |
| **可维护** | 无废弃代码、保持简洁 |
| **质量** | ruff、pyright、嵌套≤3 |
| **文档** | README、Sprint、API |

## 单维度

```bash
/ditto-review --focus architecture
/ditto-review --focus pit
/ditto-review --focus quality
```

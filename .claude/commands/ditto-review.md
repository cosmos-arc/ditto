---
name: ditto-review
description: 并行代码审查
---

# /review 命令

使用`superpowers:requesting-code-review`并行执行多维度代码审查。 再使用 `/code-review:code-review` 做最终审核决定是否可合并

## 输入

$ARGUMENTS

## 审查范围

| 用法 | 范围 |
|------|------|
| `/review` | 当前 git diff 或者 当前PR 变更 |
| `/review src/data/` | 指定目录 |
| `/review src/engines/momentum.py` | 指定文件 |
| `/review --all` | 全量审查（src/目录） |
| `/review --module data` | 按模块（data/engines/risk/api） |

## 执行流程

### Step 1: 确定范围
根据输入参数确定要审查的文件列表。

### Step 2: 并行审查（6个Task）

**同时启动：**

| Task | 职责 | 检查项 |
|------|------|--------|
| 架构 | 分层职责和依赖方向 | 1. 导入语句检查（Server 不应导入 Store/Runtime）<br>2. 职责检查（数据访问应在 Repository）<br>3. 代码重复检查（与 DataHub 重复的逻辑）|
| PIT安全 | 时间处理 | `closed="left"`、knowledge_date、无未来泄露 |
| 规约 | 编码和项目规约 | .claude/下规则文件严格遵守|
| 可维护性 | 遗留及兼容代码，代码简化 | 非数据格式破坏的兼容外，不保留任何兼容和废弃代码，保持代码简洁|
| 代码质量 | 静态检查 | ruff、pyright、嵌套≤3、无重复 |
| 文档 | 同步状态 | README、Sprint状态、API记录 |

### Step 3: 汇总报告

```markdown
## Review Report: {范围描述}

### ✅ 通过
- [x] 代码质量: 全部检查通过

### ❌ 需修复
- [ ] PIT安全: `file:line` 问题描述

### 结论: 🔴 不可合并 / 🟢 可合并
```

## 单维度审查（不并行）

```bash
/review --focus architecture  # 仅架构
/review --focus pit           # 仅PIT
/review --focus risk          # 仅风控
/review --focus quality       # 仅质量
/review --focus docs          # 仅文档
```

## 示例

```bash
/review                          # 审查当前变更
/review src/engines/             # 审查引擎模块
/review --all --focus pit        # 全量PIT审查
/review --module risk            # 审查风控模块
```

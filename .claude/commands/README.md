# Claude Code 自定义命令

> 将这些文件放入 `.claude/commands/` 目录即可使用

## 可用命令

| 命令 | 说明 | 用法 |
|------|------|------|
| `/start-dev` | 启动日常开发 | `/start-dev` 或 `/start-dev [任务描述]` |
| `/plan-sprint` | 基于设计文档拆解 Sprint | `/plan-sprint [设计文档路径]` |

## 部署

```bash
mkdir -p /path/to/ditto/.claude/commands
cp start-dev.md /path/to/ditto/.claude/commands/
cp plan-sprint.md /path/to/ditto/.claude/commands/
```

## 使用示例

### /start-dev

```bash
# 交互式选择任务
/start-dev

# 直接指定任务
/start-dev 实现 SecurityRepository
/start-dev 修复 SID 分配器的并发问题
```

### /plan-sprint

```bash
# 交互式选择设计文档
/plan-sprint

# 指定设计文档
/plan-sprint docs/design/02_data_design.md
```

## 与 Superpowers 的配合

这些命令会自动触发相关的 Superpowers skills：

| 命令场景 | 触发的 Skill |
|---------|-------------|
| `/start-dev` 新任务 | `brainstorming` → `writing-plans` |
| `/start-dev` 继续任务 | `executing-plans` |
| `/plan-sprint` | `brainstorming`（拆解讨论） |

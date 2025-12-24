## 关联任务

- 任务 ID: P0-XXX
- 规划文档: `docs/plans/YYYY-MM-DD-sprint*-task*.md`

## 变更概述

<!-- 简要描述本次变更的内容 -->

## 变更类型

- [ ] 新功能 (feat)
- [ ] Bug 修复 (fix)
- [ ] 重构 (refactor)
- [ ] 文档更新 (docs)
- [ ] 测试 (test)
- [ ] CI/CD (ci)

## 代码质量检查

提交前请确认：

- [ ] 运行 `pixi run -e dev ci-check` 通过
- [ ] 运行 `pre-commit run --all-files` 通过
- [ ] 本地测试通过
- [ ] 更新相关文档

## CI/CD 检查项

创建 PR 后，GitHub Actions 自动运行以下检查：

| 检查项 | 说明 | 状态 |
|--------|------|------|
| `lint` | Ruff 代码检查 | [ ] |
| `type-check` | MyPy 类型检查 | [ ] |
| `security` | Bandit + Gitleaks 安全扫描 | [ ] |
| `test-unit` | 单元测试（覆盖率 ≥80%） | [ ] |
| `ci-success` | CI 状态汇总 | [ ] |

## 测试说明

<!-- 描述如何验证本次变更 -->

## 截图/日志

<!-- 如适用，添加截图或日志 -->

## 其他说明

<!-- 任何其他需要审查者注意的信息 -->

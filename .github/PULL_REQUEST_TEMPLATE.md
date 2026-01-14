## 变更类型

- [ ] 🚀 feat: 新功能
- [ ] 🐛 fix: Bug 修复
- [ ] 📝 docs: 文档变更
- [ ] ♻️ refactor: 重构
- [ ] ⚡ perf: 性能优化
- [ ] ✅ test: 测试相关
- [ ] 🔧 chore: 杂项
- [ ] 🔨 ci: CI/CD

## 变更描述

<!-- 简要描述这个 PR 做了什么 -->

## 影响范围

- [ ] `packages/core` - 核心业务逻辑
- [ ] `packages/datahub` - 数据存储层
- [ ] `packages/foundation` - 基础设施
- [ ] `apps/server` - 后端服务
- [ ] `apps/web` - 前端应用
- [ ] 其他:

## Definition of Done

### 工程质量
- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 测试覆盖率达标（整体 ≥80%，风控 100%）
- [ ] 类型注解完整，Pyright 0 错误

### 代码审美
- [ ] 命名符合项目约定
- [ ] 无冗余的 AI 生成代码
- [ ] 通过所有ci-check检查

### PIT 安全（如涉及数据）
- [ ] 使用 `knowledge_date` 过滤
- [ ] rolling 指定 `closed="left"`

### 文档
- [ ] README.md 已更新（如有接口变更）

## 测试说明

<!-- 描述如何测试这些变更 -->

## 其他说明

<!-- 任何需要注意的事项 -->

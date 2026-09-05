# ditto-platform

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.2.0
**最后更新**: 2026-04-27
**状态**: 稳定

## 概要

基础设施层（Platform Layer）是 Ditto 量化系统的横切层，提供跨所有层的基础设施服务。

## 架构定位

```
┌─────────────────────────────────────┐
│         apps/backend               │
│     (应用边界层)                     │
├─────────────────────────────────────┤
│      packages/application           │
│     (应用编排层)                     │
├─────────────────────────────────────┤
│      packages/analysis              │
│     (research control-plane)         │
├─────────────────────────────────────┤
│  packages/strategy/portfolio/risk/  │
│  execution/backtest/features        │
│     (领域能力平面)                   │
├─────────────────────────────────────┤
│      packages/data                  │
│     (数据平台)                       │
├─────────────────────────────────────┤
│      packages/kernel                │
│     (共享内核 — 零业务行为类型)       │
├─────────────────────────────────────┤
│      packages/platform (当前层)      │
│     (基础设施层)                     │
└─────────────────────────────────────┘
```

**依赖规则**: Platform 层零依赖其他层，可被所有层访问。

目录结构、核心功能、导入规范详见 [AGENTS.md](AGENTS.md)。

## 测试

```bash
pixi run -e dev pytest packages/platform/tests/
```

## 变更记录

### v0.2.0 (2026-04-27)
- 新增 config/providers/、notification/channels/ 子目录
- 通知模板由 apps composition root 管理，platform 仅保留通用通知基础设施
- 扩展 observability 细节（日志/追踪/指标/生命周期）

# Ditto 架构规范索引

> 本目录记录跨包架构规则、命名词典、抽象层级和扩展放置标准。它面向后续 agent 与个人开发者，回答“新代码应该放哪里、叫什么、依赖谁、不能做什么”。

## 文档

| 文档 | 状态 | 用途 |
|---|---|---|
| [boundaries-and-abstraction-standards.md](boundaries-and-abstraction-standards.md) | Draft | 分层、模块化、命名、抽象层级一致性与扩展方式规范 |

## 使用方式

开发或审查前先阅读对应包的 `CLAUDE.md`，再用本目录文档判断跨包边界和抽象层级。若两者出现冲突，以当前代码门禁和最新 `CLAUDE.md` 为执行约束，并补充 ADR 或修订本文档。

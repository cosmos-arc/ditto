# Ditto Analysis

**版本**: v0.1.0 | **日期**: 2026-06-04 | **状态**: 稳定

## 概要

研究分析 control-plane — 研究数据集契约、纯研究层（非生产路径）。

## 核心子域

| 子域 | 职责 |
|------|------|
| research | 研究数据集 control-plane，契约定义 |
| experiments | reserved — 预留实验管理命名空间 |
| storage | 研究 SQLite 存储 |
| di | DI 注册，研究模块依赖注入 |

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 详细架构规则与导入约束

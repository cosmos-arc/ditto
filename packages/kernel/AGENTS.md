# Kernel 包指南

## 定位与依赖

跨包共享的领域原语、值对象和 Protocol。不得依赖任何其他 Ditto 包或第三方库，不得执行 I/O。

## 关键不变量

- 新类型仅在跨至少两个包复用、行为稳定且具纯值语义时进入 kernel。
- frozen value object 只允许无副作用、无 I/O 的纯计算属性。
- barrel 保持窄小；低频符号从叶模块导入，禁止用 re-export 隐藏依赖。
- 新增共享契约需说明提供者、消费者和机器依赖边界，遵循下方边界标准。

## 验证与参考

- `uv run --no-sync pytest packages/kernel/tests`
- `task arch-check`
- [边界标准](../../docs/architecture/boundaries-and-abstraction-standards.md)

# Expression Pratt ADR Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐自建 Pratt 表达式引擎，使其与 ADR-004 / ADR-014 对齐，并为后续语法扩展保留稳定扩展点。

**Architecture:** 继续保留仓库内自建 Pratt parser，不引入第三方解析库。实现范围覆盖 `lexer -> ast -> parser -> analyzer -> diagnostics -> codegen -> compiler` 全链路，并通过 span-aware 诊断、注册式 parselet、语法/语义黄金测试锁定行为。

**Tech Stack:** Python 3.13, Polars, orjson, pytest, basedpyright, Ruff

---

### Task 1: 锁定目标语法与诊断行为

**Files:**
- Modify: `packages/core/tests/unit/engine/test_expression_parser_unit.py`
- Modify: `packages/core/tests/unit/engine/test_expression_engine_unit.py`
- Create: `packages/core/tests/unit/engine/test_expression_diagnostics_unit.py`

**Steps:**
1. 写 parser 失败测试，覆盖 `dataset.column`、`@derived`、`STRING`、`and/or/not`、比较与算术优先级。
2. 跑定向测试，确认当前 lexer/parser 无法通过。
3. 写 compiler/diagnostics 失败测试，覆盖未知算子建议、字符串参数类型错误、括号不匹配位置。
4. 跑定向测试，确认失败原因来自缺失能力而非测试错误。

### Task 2: 升级词法与 AST 契约

**Files:**
- Modify: `packages/core/src/ditto_core/engine/expression/lexer.py`
- Modify: `packages/core/src/ditto_core/engine/expression/ast.py`
- Create: `packages/core/src/ditto_core/engine/expression/diagnostics.py`

**Steps:**
1. 为 token 增加 source span/line/column。
2. 补齐 `STRING`、`@`、`.`、逻辑关键字等词法能力。
3. 扩展 AST 节点：列引用、派生引用、字符串字面量，并给节点携带 span。
4. 定义结构化编译错误与格式化器，统一词法/语法/语义/类型错误代码。

### Task 3: 完成 Pratt 扩展点与完整语法支持

**Files:**
- Modify: `packages/core/src/ditto_core/engine/expression/parser.py`

**Steps:**
1. 保持 parselet 注册结构不变，新增 `@` 前缀、`.` 后缀、`and/or/not`、字符串字面量解析。
2. 固定优先级：`or < and < compare < +/- < */ < unary < call/dot`。
3. 让 parser 在报错时返回带 span 的结构化异常，不再只抛裸 `ValueError`。

### Task 4: 补齐分析、校验与 codegen

**Files:**
- Modify: `packages/core/src/ditto_core/engine/expression/analyzer.py`
- Modify: `packages/core/src/ditto_core/engine/expression/codegen.py`
- Modify: `packages/core/src/ditto_core/engine/expression/compiler.py`
- Modify: `packages/core/src/ditto_core/engine/expression/registry.py`

**Steps:**
1. 让 analyzer 正确收集列依赖、派生依赖、operator 名称、lookback、scope、output schema。
2. 在 registry 中补充 operator 元数据，支持未知算子建议和基本签名校验。
3. 在 codegen 中补齐 `STRING`、`and/or/not`、列引用与派生引用的编译语义。
4. 把复杂度限制与结构化错误串到 compiler 主线。

### Task 5: 回归、清理与验证

**Files:**
- Modify: 受影响测试文件

**Steps:**
1. 运行 expression 相关定向单测，确认 RED -> GREEN。
2. 视需要做小幅重构，保持 parselet/diagnostics/registry 边界清晰。
3. 运行 `pixi run -e dev check` 做全量验证。

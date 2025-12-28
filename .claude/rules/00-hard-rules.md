---
alwaysApply: true
---

# 硬性规则

> 以下规则无条件适用，违反即为错误

---

## 开发流程

- **必须 TDD**：先写测试，再写实现，RED→GREEN→REFACTOR
- **必须分支开发**：禁止直接提交 main
- **必须小步提交**：每个 TDD 循环独立提交

## 环境依赖

- **只用 pixi**：禁止 pip/poetry/conda
- **六核心依赖**：polars / duckdb / sqlite / fastapi / prefect / opentelemetry

## 代码规范

- **Polars 不是 Pandas**：禁止 `import pandas`
- **类型注解必须**：公开函数 100% 类型注解
- **函数长度**：≤50 行
- **嵌套深度**：≤3 层

## PIT 安全

- **knowledge_date 必须**：所有数据表必须有此字段
- **closed="left"**：rolling 函数必须显式指定
- **T日信号→T+1执行**：禁止使用当日数据做当日决策

## 风控

- **Kill Switch 同步检查**：交易前必须检查
- **风控测试 100% 覆盖**：Kill Switch 每个级别都要测试
- **禁止吞异常**：风控异常必须上抛

## 测试

- **AAA 模式**：Arrange → Act → Assert
- **测试隔离**：禁止测试间依赖
- **边界覆盖**：正常/边界/异常路径都要测

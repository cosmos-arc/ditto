# Batch 6 设计文档：AI-Ready 基础 + 产品路线

> 创建：2026-05-31
> 基线：`docs/plans/2026-05-25-architecture-remediation-roadmap.md` Batch 6
> 状态：实施中

---

## 概述

Batch 6 为 Ditto 量化平台铺设 AI 集成的架构基础，包含 4 个原子任务。目标使 AI-Ready 评分从 4.0 提升到 6.0。

---

## B6-1: Features Hypothesis → Expression 桥接点

### 设计

在 features expression pipeline 中创建 AI 假设接入点，遵循**依赖倒置原则** — features 不依赖 AI/LLM，只定义桥接契约。

### 数据模型

```python
@dataclass(frozen=True)
class Hypothesis:
    """AI 生成的投资假设，可转化为表达式。"""
    natural_language: str           # "高动量+低波动率的ETF表现更好"
    expression_draft: str           # "ts_momentum(close, 20) / ts_std(close, 20)"
    metadata: dict[str, str]        # 来源/置信度等
```

### 桥接函数

```python
def hypothesis_to_expression(hypothesis: Hypothesis) -> str:
    """将假设转化为可编译的表达式。

    当前为占位实现（透传 expression_draft）。
    未来 LLM 可替换此函数，将 natural_language 翻译为合法 expression。
    """
    return hypothesis.expression_draft
```

### 文件

- `packages/features/src/ditto_features/expression/hypothesis.py`（新建）

### 验收

- [x] Hypothesis 数据类定义
- [x] hypothesis_to_expression 占位实现返回合法 expression string
- [x] 编译器可编译输出

### 测试

- [x] 单测：hypothesis → expression → 编译成功

---

## B6-2: Strategy CompositeDecisionStage

### 设计

基于业界 Score Fusion + Rank-Based Normalization 最佳实践（参考 QuantConnect LEAN CompositeAlphaModel）。

采用 **并行独立 + Rank-Based Score Fusion** 方案：

```
Input Frame ──┬──▶ Stage A ──▶ score_A (rank-normalized)
              ├──▶ Stage B ──▶ score_B (rank-normalized)  ──▶ weighted_avg ──▶ unified "score"
              └──▶ Stage C ──▶ score_C (rank-normalized)
```

### 数据模型

```python
class FusionMethod(StrEnum):
    """信号聚合方法。"""
    RANK_WEIGHTED = "rank_weighted"  # Rank 标准化后加权（默认）
    EQUAL = "equal"                  # 等权（Rank 后简单平均）

@dataclass(frozen=True)
class CompositeDecisionStage:
    """多信号聚合 Stage，将多个 DecisionStage 的输出合并为统一评分。

    对每个子 stage 独立执行 process()，提取 score 列，
    rank 标准化后加权求和，产出统一 score 列。
    """
    stages: tuple[DecisionStage, ...]
    weights: tuple[float, ...]
    method: FusionMethod = FusionMethod.RANK_WEIGHTED
```

### 核心流程

1. 对每个子 stage，在输入 frame 的**副本**上独立执行
2. 从每个子 stage 输出中提取 `score` 列（fallback: `signal_value` → fill_null(0.0)）
3. Rank 标准化每列到 [0, 1]
4. 按 weights 加权求和 → 统一 `score` 列
5. L1 范数归一化权重，全零自动退化为 equal weight

### 文件

- `packages/strategy/src/ditto_strategy/alpha/composite.py`（新建）
- `packages/strategy/src/ditto_strategy/alpha/builtins/__init__.py`（更新导出）

### 验收

- [x] isinstance(CompositeDecisionStage(), DecisionStage) 通过
- [x] 多信号加权合并逻辑正确
- [x] 权重归一化（L1范数，全零退化）

### 测试

- [x] 单测：2 个 stage 加权合并
- [x] 单测：权重归一化
- [x] 单测：空 frame / 无 score 列

---

## B6-3: Analysis Experience Memory 基础

### 设计

在 analysis research/ 下创建 AI agent 经验记忆基础设施。

### 数据模型

```python
@dataclass(frozen=True)
class DecisionLog:
    """一条 AI 决策日志。"""
    timestamp: str                  # ISO 8601
    context: str                    # "回测 2024-01 ETF轮动"
    decision: str                   # 采取的决策
    outcome: str                    # 结果
    reflection: str                 # AI 反思
    tags: tuple[str, ...]           # 分类标签
```

### Protocol

```python
@runtime_checkable
class ExperienceMemory(Protocol):
    def record(self, log: DecisionLog) -> None: ...
    def query(self, tags: tuple[str, ...] | None = None, *, limit: int = 50) -> tuple[DecisionLog, ...]: ...
    def summarize(self) -> str: ...
```

### Markdown 实现

- `MarkdownExperienceMemory` 读写 markdown 文件
- 每个 DecisionLog 一个 `##` 段落
- 格式人类可读、AI 可解析
- 仅依赖 stdlib + pathlib

### 文件

- `packages/analysis/src/ditto_analysis/research/experience.py`（新建）
- `packages/analysis/src/ditto_analysis/research/__init__.py`（更新导出）

### 验收

- [x] 可记录和查询决策历史
- [x] Markdown 格式可读
- [x] isinstance 检查通过

### 测试

- [x] 单测：record → query 一致性
- [x] 单测：Markdown 文件格式正确

---

## B6-4: Analysis Reserved Namespace 评估

### 决策

| Namespace | 决策 | 理由 |
|-----------|------|------|
| `diagnostics` | **删除** | 无近期产品需求，研究诊断由 research/ 覆盖 |
| `screeners` | **删除** | 股票筛选由 strategy/builtins + data query 覆盖 |
| `reports` | **删除** | 报告生成由 application query + features evaluation 覆盖 |
| `experiments` | **保留** | AI 实验性功能预留 |

### 变更

- 删除 `diagnostics/`、`screeners/`、`reports/` 目录
- 更新 `test_placeholder_honesty_unit.py` 只保留 experiments
- 更新 `packages/analysis/CLAUDE.md`
- 更新 `docs/architecture/boundaries-and-abstraction-standards.md`

### 验收

- [x] 3 个 namespace 已删除
- [x] experiments 保留为空壳
- [x] 测试通过

---

## 依赖关系

```
B6-4 (namespace 清理) ── 无依赖，可先执行
B6-1 (hypothesis)     ── 独立
B6-2 (composite)      ── 独立
B6-3 (experience)     ── 独立
```

全部 4 个任务相互独立，可并行开发。

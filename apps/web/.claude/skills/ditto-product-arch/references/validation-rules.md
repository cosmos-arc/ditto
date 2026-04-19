# 验证规则

> 定义 `/ditto-product-arch` 的审计维度和验证协议。
> Phase 5 VALIDATE 按此规则执行。

---

## 6 维审计规则

### 维度 1: 完整性

| 检查项 | 通过标准 |
|--------|---------|
| IA 文档覆盖所有已知页面 | 0 遗漏 |
| 蓝图文档覆盖 IA 中定义的所有页面 | 0 遗漏 |
| 每个页面有 Tab Content Sections | 0 缺失 |
| 每个 tab 有子模块清单 + 数据字段 + 交互说明 | 0 缺失 |
| 每个数据组件有 Component × State Matrix 定义 | 0 缺失 |
| 数据组件至少定义 loading/empty/failed 三态 | 0 缺失 |

### 维度 2: 一致性

| 检查项 | 通过标准 |
|--------|---------|
| 标签/术语跨文档一致 | 0 不一致 |
| 层级关系无矛盾 | 0 矛盾 |
| 页面间关系与导航矩阵一致 | 0 偏差 |
| Blueprint 数据字段引用与 IA 字段定义一致 | 0 孤立引用 |

### 维度 3: 可达性

| 检查项 | 通过标准 |
|--------|---------|
| 所有页面在导航中可达 | 0 不可达 |
| 所有流程有出口 | 0 死端 |
| 跨页面流程路径无断裂 | 0 断裂 |

### 维度 4: 时效性

| 检查项 | 通过标准 |
|--------|---------|
| 与最新设计决策同步 | 0 不同步 |
| 与原型对齐（如存在） | 0 偏差 |
| 状态定义与 04_interaction_state_spec.md 一致 | 0 遗漏 |

### 维度 5: 扩展性

| 检查项 | 通过标准 |
|--------|---------|
| 新增页面时 IA 无需大规模重构 | 无结构性障碍 |
| 导航模型支持新增顶级区域 | 无硬编码上限 |
| 标签体系支持新增资产类别 | 无命名冲突 |

### 维度 6: 状态覆盖

| 检查项 | 通过标准 |
|--------|---------|
| Tab Content Sections 覆盖率 | M/N = 100% |
| Overlay Registry 覆盖率 | 破坏性操作 100% 有 Confirm |
| Component × State Matrix 覆盖率 | L/N 组件，每个至少 3 态 |

---

## Constitution 合规检查

### 检查协议

逐条检查 Discovery 产出的 23 条 Constitution 约束（T1-T6 / P1-P5 / U1-U8 / C1-C4）。

### 检查方式

Phase 2 DESIGN: 将相关约束注入每个角色的 Agent prompt，设计时遵守。
Phase 5 VALIDATE: 逐条检查最终产出物是否违反，输出合规报告。

### 违规分级

| 级别 | 定义 | 处理 |
|------|------|------|
| P0 | 产出物直接违反 MUST NOT 约束 | MUST 修复后才能通过 Gate |
| P1 | 产出物未充分体现 SHOULD 约束 | SHOULD 修复，记录到待改进清单 |
| P2 | 产出物可以更好地体现约束精神 | 记录到优化建议 |

### 合规报告格式

```
## Constitution 合规检查

| 约束 ID | 约束描述 | 合规状态 | 违规详情 |
|---------|---------|---------|---------|
| T1 | 可插拔数据源架构 | ✅ / ❌ | ... |
```

---

## 状态定义覆盖率报告

Phase 5 VALIDATE MUST 输出：

```
## 状态定义覆盖率

- Tab Content Sections: M/N (100%)
- Overlay Registry: K 个 overlay，破坏性操作 Confirm 覆盖 100%
- Component × State Matrix: L/N 组件
  - loading 态: L/N
  - empty 态: L/N
  - failed 态: L/N
- Page Contract Mapping: M/N 页面
  - route 格式正确: M/N
  - shellFamily 在枚举内: M/N
  - pagePattern 在枚举内: M/N
  - 模块→Slot 映射完整: M/N
```

---

## 页面合同映射完整性验证

| 检查项 | 通过标准 |
|--------|---------|
| 每个页面有 Page Contract Mapping section | 0 缺失 |
| route 格式以 `/` 开头 | 0 违规 |
| shellFamily 在 7 个枚举值中 | 0 违规 |
| pagePattern 在 8 个枚举值中 | 0 违规 |
| 模块→Slot 映射覆盖所有核心模块 | 0 遗漏 |

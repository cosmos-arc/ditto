# Phase 15: SHIP — 收尾

> 代码简化 + 最终质量 pass + 文档同步 + 状态推进。

**前置条件**：`docs/contracts/pages/<page>.contract.json` 的 `status === "contract-ready"`

```
检查 contract.status：
├─ "contract-ready" → 继续执行
└─ "draft" → STOP，提示用户先运行 $ditto-page-contract --promote <page>
```

---

## 执行步骤

1. **最终质量 pass** — 检查 alignment、spacing、typography、color、interaction states、micro-interactions、content consistency、icons/images、forms、edge cases、responsiveness、performance 和 code quality
2. **代码简化** — 删除重复、收紧接口、降低分支复杂度，避免无收益抽象
3. **全量验证** — `bun run check`（lint + type + test）
4. **文档更新**
   - 更新实现计划文档，标记任务完成状态
   - 如有 `[proto-deviation]` 记录，同步到原型反馈清单
5. **Edition manifest 推进**
   - 更新 `.edition-manifest.json` 中对应页面的实现状态
   - `done`（原型审查通过）→ `implemented`（实现完成）
6. **反馈聚合** — 扫描实现过程中的原型偏差和设计改进建议
   ```
   1. 扫描当前页面所有 [proto-deviation] doc comments
   2. 扫描 Phase 14 Gap 分析中分类为"原型缺陷"的项
   3. 如果反馈项 > 0:
      → 写入 docs/contracts/feedback/<page>.md
        格式: 分类（原型缺陷 / 设计改进）→ 模块 → 描述 → 建议
      → 输出建议: "发现 N 项实现反馈，建议运行
        $ditto-design-cycle <prototype> --review-feedback <page>"
   4. 如果反馈项 = 0: 跳过
   ```
7. **输出实现报告**
   ```
   实现报告（per page）：
   ├── Audit 5 维评分（a11y/perf/theming/responsive/anti-patterns）
   ├── L1/L2/L3 验证结果
   ├── 交互状态覆盖矩阵
   ├── [proto-deviation] 列表（如有）
   ├── 新增/复用/扩展的组件清单
   └── 测试覆盖率
   ```

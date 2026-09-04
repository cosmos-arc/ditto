# Discovery 特殊模式

## --validate（完整性检查）

只跑 Phase 5 的 Step 1-4 检查，不修改任何文件。

```
INIT
→ Zachman 覆盖度检查 + YAML 字段完整性
→ Brief/Research/Constitution 一致性检查
→ 假设盘点（列出 unvalidated High risk）
→ 下游衔接检查
→ 输出检查报告（pass/warning/fail）
```

**通过标准**：
- Zachman 6 维度覆盖 ≥ 5/6
- YAML 关键字段完整性通过（entities/capabilities/actors 至少各 1 个带完整字段）
- 一致性检查 0 个 fail 项
- 所有产出文件存在且非空
- assumptions.md 存在且 High risk 假设均已标记状态

## --sync（反向同步）

当下游 spec 变更时，反向更新 Brief/Research/Assumptions 保持一致。

```
INIT
→ 读取当前 spec 文档（docs/designs/specs/00-18）
→ Diff Brief/Research/Assumptions vs Spec
→ 识别不一致项
→ 宿主原生用户提问能力 确认每个变更
→ 更新 Brief/Research/Assumptions
→ 如 spec 变更导致假设不再成立 → 标记 invalidated
→ git commit
```

## --from-existing（补救路径）

从现有 spec 反推生成 Brief + Research + Assumptions（适用于历史 spec 缺少上游文档的情况）。

```
INIT
→ 读取所有 spec 文档
→ AI 提取：定位/用户/痛点/竞品/系统描述/约束
→ 反向填充 Brief + Research + Assumptions 结构
→ 标注置信度（高/中/低）——AI 推导的内容需要用户确认
→ 宿主原生用户提问能力 逐项确认
→ 落盘 + git commit
```

## --phase `<N>`（恢复/重跑）

从指定 Phase 恢复或重跑。Phase 1-4 的已产出文件保留，只重新执行指定 Phase 的提问和落盘。

```
--phase 1  → 重跑 VISION
--phase 2  → 重跑 LANDSCAPE（重新调研）
--phase 3  → 重跑 SYSTEM（重新提问）
--phase 4  → 重跑 CONSTRAINTS
--phase 5  → 重跑 SYNTHESIS
```

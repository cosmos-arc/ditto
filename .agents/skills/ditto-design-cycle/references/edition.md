# Edition 机制

> **Edition** = 一个产品 UI 版本的全部页面原型集合，以 manifest 清单跟踪状态。

---

## Manifest 文件

- **路径**: `docs/designs/specs/prototypes/.edition-manifest.json`
- **版本标识**: manifest 中 `edition` 字段 + git tag `edition/<ver>/*`

---

## 页面状态

```
created → audit-passed → reviewed → needs-refinement → done
```

| 状态 | 含义 | 触发 |
|------|------|------|
| created | --create-all 生成，通过 per-page gate + 批量后检查 | Phase 0.5 完成后 |
| audit-passed | 零 Inline Style 门禁 + 三区结构验证通过 | Phase 8 Step 8.1-8.4 |
| reviewed | 六角色审查完成，评分记录 | Phase 8 Step 8.12 |
| needs-refinement | 审查发现 P0 需要修复 | Phase 8 有 P0 未修复 |
| done | 全部门禁通过 + 合同创建/验证成功 | Phase 8 Step 8.16 完成 |

---

## 风格锚点 (styleAnchor)

- 首个页面是基准
- 后续页面以 manifest 中最高分 done 页面为参考
- --create-all 逐页创建时自动传入 anchor 页面 HTML 作为 --reference

---

## --create-all 批量创建

详见 [create-mode.md](create-mode.md) §--create-all 批量创建。

---

## Edition 状态推进（Phase 8 Step 8.15）

当 manifest 存在时，Phase 8 FINAL 中执行：

1. 确认页面当前 status === "reviewed"
2. 执行合同桥接（Step 8.16a → 8.16b → 8.16c）
3. 更新对应 page 的 `{status:"done", score, rounds}`
4. 如所有页面 status="done" → manifest.status = "reviewing"
5. 写入 .edition-manifest.json → git add

---

## Edition Review（--edition-review）

### 执行流程

1. 读取 manifest，获取所有 status="done" 的页面
2. 逐页使用 Playwright 打开：
   - page.setViewportSize(1536x1080)
   - navigate → page.screenshot({ fullPage: true })
   - analyze_image 检测：
     - 布局 bug（溢出、截断、重叠）
     - 风格偏差（与 Edition 整体不一致的元素）
     - 排版问题（字号层级混乱、间距异常）
3. 生成 Edition 级验收报告
   - 逐页截图 + 问题标记
   - 跨页一致性摘要
   - 只标记 P0/P1 问题，不跑完整七角色审查
4. 更新 manifest：
   - crossPageAudit.lastRun / issues
   - 如无 P0 → manifest.status = "reviewed"
5. git commit + tag edition/v1/reviewed
6. 如有 P0 问题 → 逐页运行审查修复
7. 修复后 tag edition/v1/final

---

## 约束

- 不引入 git worktree：在当前分支操作，通过 manifest + tag 管理
- 不同 Edition 的 manifest 互相独立

# 时空之门 (CrossGate) — 全自主开发迭代系统设计

> 日期：2026-04-08
> 状态：Draft
> 作者：Chevy + Claude

## 1. 愿景

一个 AI 全自主驱动的开发迭代系统。用户设定目标、方向和偏好后，AI 独立完成：
目标拆解 → 任务执行 → 自动修复 → 自主评审 → 知识沉淀 → 持续进化

用户只做三件事：**设定目标、偶尔纠偏、最终把关 PR。**

本质是一个"AI 驱动的开发操作系统"——无论是白天交互式使用还是无人值守长程运行，都是同一个系统。

### 1.1 核心原则

- **AI 全权驱动** — 从目标解析到代码提交，全链路自主决策
- **结构化自主评审** — AI 的主观判断被四层评估框架约束，不靠自觉
- **无状态循环** — 每次迭代是独立 agent session，通过文件传递状态
- **知识积累** — 每次迭代都在变强，不只是完成任务
- **安全隔离** — 工作在独立分支，PR 是唯一的合入路径

---

## 2. 系统架构

### 2.1 整体结构

```
┌─────────────────────────────────────────────────────────┐
│                   User Interface                         │
│          /crossgate (slash command / CLI)                │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              Orchestrator (Python CLI)                   │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │
│  │ Task Manager │  │ Evaluator   │  │ Knowledge     │   │
│  │ (queue +     │  │ (四层评估   │  │ Engine        │   │
│  │  discovery)  │  │  框架)      │  │ (积累+进化)   │   │
│  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘   │
│         │                │                  │           │
│  ┌──────▼────────────────▼──────────────────▼───────┐   │
│  │              State Machine (文件系统)              │   │
│  │  progress.json | learnings.json | metrics.json   │   │
│  │  patterns.md | anti_patterns.md | rubric.md      │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │           Agent Spawner (claude -p)              │   │
│  │     每个 iteration 启动独立 Claude Code 进程       │   │
│  │     在独立 feature 分支上执行                      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              Feature Branch (分支隔离)                    │
│         commit + tag per iteration                      │
│         feature branch → PR → human review               │
└─────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Orchestrator | Python CLI (pixi) | 项目内工具，`pixi run crossgate` |
| Agent | `claude -p "..."` | 无交互模式，每次迭代独立进程 |
| 状态存储 | JSON + Markdown | `docs/crossgate/session/` 目录 |
| 代码隔离 | Git feature branch | 独立分支，不影响用户工作区 |
| 质量门禁 | `pixi run check` | 现有基础设施直接复用 |
| 会话管理 | 进程信号 (SIGINT/SIGTERM) | 优雅暂停/恢复，状态持久化 |

---

## 3. 触发与调度

### 3.1 启动方式

```bash
# 方式 1: 斜杠命令 (在 Claude Code 内)
/crossgate start --goal "Phase 4 代码质量全面提升" --mode goal-driven

# 方式 2: CLI (任何终端)
pixi run crossgate start \
  --goal "Phase 4 代码质量全面提升" \
  --mode goal-driven \
  --reference docs/reviews/industry-benchmark.md \
  --tasks "修复 data 层 type errors" "拆分过胖 Service" \
  --budget 100

# 方式 3: CLI (Karpathy 模式)
pixi run crossgate start \
  --goal "优化 ingestion_coordinator 代码质量" \
  --mode karpathy \
  --metric "coverage≥80% complexity<10 lines<50" \
  --budget "100 iterations / 8 hours"
```

### 3.2 调度方式

```bash
# 查看状态
pixi run crossgate status

# 暂停 (完成当前迭代后停止)
pixi run crossgate pause

# 恢复
pixi run crossgate resume

# 追加约束 (运行中)
pixi run crossgate redirect "不要修改 xxx 模块"

# 中止 (保留所有已提交内容)
pixi run crossgate abort

# 查看报告
pixi run crossgate report
```

### 3.3 会话生命周期管理

编排器是一个长驻进程，通过循环调度 agent 迭代。

**核心理念：不追求进程永不崩溃，而是保证状态在磁盘上，随时可恢复。**
（借鉴 GSD v2 的磁盘状态机模式）

```bash
# 启动 (前台运行，可随时 Ctrl+C 中止)
pixi run crossgate start --goal "..." --budget 100

# 恢复 (从上次中断处继续，读取磁盘状态)
pixi run crossgate resume

# 暂停 (完成当前迭代后优雅停止，保存状态)
pixi run crossgate pause   # 或直接 Ctrl+C

# 中止 (立即停止，保留所有已提交内容)
pixi run crossgate abort
```

**编排器内部循环：**

```
while budget_remaining:
    1. 读取状态文件 (progress, learnings, metrics)
    2. 检查暂停信号 (pause file 或 SIGINT)
    3. 启动 claude -p "迭代 prompt" (传入当前状态)
    4. 三级超时监控 (软超时 / 空闲检测 / 硬超时)
    5. 等待进程结束，收集结果
    6. 验证 (pixi run check)
    7. 评估 (四层评估框架)
    8. 决策 (commit / 修复 / 跳过)
    9. 更新状态文件 (每次迭代后立即持久化)
    10. 检查终止条件 (全部完成 / 预算耗尽 / 断路器连跳)
```

**关键设计：**

- **每次迭代是新进程** — 不使用 `--resume`，避免 context 污染；状态通过文件传递
- **磁盘即真相** — 所有状态在 `docs/crossgate/session/` 中，进程崩溃不丢失任何已保存的进度
- **预算控制** — 迭代次数上限或时间上限，任一达到即停止
- **优雅退出** — SIGINT/SIGTERM 时完成当前迭代后保存状态，下次 `resume` 可继续
- **终止条件** — 全部任务完成、预算耗尽、连续 N 个任务触发断路器

---

## 4. 目标解析 (Goal Resolution)

### 4.1 Goal 输入格式

用户输入可以是从模糊到精确的任意粒度：

```
模糊: "Phase 4 代码质量全面提升"
中等: "让 data 层达到项目代码质量标准"
精确: "修复 data 层 12 个 basedpyright type error，coverage 提升到 85%"
```

### 4.2 解析流程

AI 第一轮 session 专门做 Goal Resolution：

1. **分析 Goal** — 理解意图，识别关键指标和约束
2. **建立基线** — 运行 `pixi run check`，记录当前 coverage、type errors、lint issues 等
3. **拆解 Phases** — 将 Goal 分解为有序的里程碑
4. **定义完成判据** — 每个 Phase 的可验证完成条件（量化 + 质化）
5. **输出结构化计划** — 写入 `docs/crossgate/session/plan.json`

### 4.3 完成判据的类型

| 类型 | 示例 | 验证方式 |
|------|------|---------|
| 硬指标 | coverage ≥ 80%, type errors = 0 | 自动度量 |
| 软指标 | 代码可读性提升, 架构更清晰 | AI 评审 |
| 对标指标 | 与业界最佳实践差距缩小 | AI 评审 + 对比分析 |
| 任务完成 | 所有已知 tasks 执行完毕 | 进度跟踪 |

---

## 5. 执行循环 (Execution Loop)

### 5.1 单次迭代生命周期

每次迭代是一个**独立的 Claude Code 进程**，在独立 feature 分支上执行：

```
┌─ Iteration N ─────────────────────────────────────────┐
│                                                        │
│  1. READ CONTEXT                                       │
│     ├─ progress.json (进度、已完成、失败记录)            │
│     ├─ learnings.json (历史经验教训)                     │
│     ├─ metrics.json (度量基线 + 趋势)                   │
│     └─ design_rubric.md (设计评价标准)                   │
│                                                        │
│  2. PICK TASK                                          │
│     ├─ Queue 非空 → 取下一个任务                         │
│     └─ Queue 空 → 自主发现（审计代码 / 对标业界）         │
│                                                        │
│  3. IMPLEMENT (TDD: RED → GREEN → REFACTOR)            │
│     ├─ 写测试 → 写实现 → 重构                           │
│     └─ 记录决策理由                                     │
│                                                        │
│  4. HARD GATE                                         │
│     └─ pixi run check → 失败则进入修复循环               │
│                                                        │
│  5. FIX LOOP (最多 10 次)                              │
│     ├─ 分析失败原因                                     │
│     ├─ 修复 → 重新验证                                 │
│     └─ 10 次仍失败 → 断路器触发（跳过，记录，下一个）      │
│                                                        │
│  6. SOFT REVIEW (四层评估)                             │
│     ├─ L1: 客观度量 → 对比趋势                          │
│     ├─ L2: Before/After 对比 → 整体变好还是变差          │
│     ├─ L3: 标准评审 → Rubric 逐条对照                    │
│     └─ L4: 交叉评审 → 多角度 review                      │
│                                                        │
│  7. DECIDE                                            │
│     ├─ 全部通过 → git commit + tag                      │
│     ├─ 软评有问题 → 修复 (同样受 10 次断路器约束)        │
│     └─ 方向完全错误 → 回滚 (极少数)                      │
│                                                        │
│  8. UPDATE STATE                                       │
│     ├─ progress.json → 更新进度                         │
│     ├─ learnings.json → 记录经验                        │
│     ├─ metrics.json → 记录度量                          │
│     └─ session_log.md → 人类可读日志                    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 5.2 修复循环策略

**核心原则：像程序员一样，修而不是 revert。**

| 情况 | 行为 |
|------|------|
| lint/type 报错 | 自动修复，重跑 |
| 测试失败 | debug → fix → 重跑 |
| review 有意见 | address → re-review |
| 连续 10 次修复仍失败 | 断路器 → 暂停此任务，记录分析，继续下一个 |
| 方向完全错误 (极少数) | git revert，换思路重来 |

### 5.3 断路器设计

```
重试计数器: 0
每次修复失败: count += 1
每次新迭代成功: count = 0

count >= 10:
  ├─ 记录失败分析到 failure_log.json
  ├─ 记录经验教训到 learnings.json
  ├─ 跳过当前任务，进入下一个
  └─ 如果是连续多个任务触发断路器 → 暂停整个循环，等人工介入
```

---

## 6. 四层评估框架

**核心原则：让 AI 的主观判断被结构和流程约束，而不是靠自觉。**

### 6.1 L1: 客观度量 (Quantitative)

自动运行，不讨论：

```json
{
  "pixi_run_check": "PASS",
  "coverage_branch": 0.85,
  "coverage_change": "+0.03",
  "type_errors": 0,
  "type_errors_change": -5,
  "lint_issues": 0,
  "test_count": 342,
  "test_count_change": "+12"
}
```

### 6.2 L2: Before/After 对比 (Comparative)

不问"好不好"，问"比改之前好还是差"：

```
本次改动涉及: data/models/ingestion.py (+45/-30)
对比维度:
├─ 职责清晰度: 改善 (单体函数拆为 3 个职责明确的函数)
├─ 可测试性: 改善 (新增 4 个单元测试覆盖边界情况)
├─ 复杂度: 无显著变化 (总体圈复杂度持平)
└─ 引入风险: 低 (仅内部重构，无 API 变更)
结论: PASS (整体改善，无退化)
```

### 6.3 L3: 标准评审 (Rubric-based)

预定义设计评价标准，AI 逐条对照：

```markdown
## Design Rubric

### 结构
- [ ] 单一职责：每个模块/类/函数只有一个变更的理由
- [ ] 低耦合：模块间依赖最小化，符合分层架构约束
- [ ] 高内聚：相关逻辑内聚在同一个模块中

### 可读性
- [ ] 命名清晰：变量/函数/类名自解释
- [ ] 控制流简单：避免深层嵌套，early return 优先
- [ ] 注释克制：只在逻辑不自解释时添加注释

### 可维护性
- [ ] 易于测试：核心逻辑可独立单元测试
- [ ] 易于扩展：新功能不需要修改已有代码 (OCP)
- [ ] 易于推理：读者能在 30 秒内理解函数意图

### 项目特有
- [ ] 符合 CLAUDE.md 架构约束
- [ ] 符合 .importlinter 分层规则
- [ ] 数据处理使用 polars (禁止 pandas)
- [ ] JSON 使用 orjson (禁止 json)
```

### 6.4 L4: 交叉评审 (Multi-perspective Review)

多轮、不同角度的 review（复用 `/ditto-review` 的六维模式）：

| 评审角度 | 关注点 |
|---------|--------|
| 架构 | 是否违反分层？是否引入循环依赖？ |
| 可读性 | 风格一致？命名清晰？逻辑易懂？ |
| 可维护性 | 测试充分？扩展容易？修改安全？ |
| 性能 | 是否引入不必要的开销？ |
| 安全 | 是否引入注入/XSS/信息泄漏风险？ |
| 一致性 | 是否与项目已有模式一致？ |

### 6.5 评估决策

```
L1 PASS + L2 PASS + L3 PASS + L4 PASS → ✅ 保留，提交
L1 FAIL → 修复循环 (最多 10 次)
L2/L3/L4 FAIL → 修复循环 (最多 10 次)
全部 PASS 但方向存疑 → 记录，继续 (保守策略，不阻止)
```

---

## 7. 知识积累与自主进化

### 7.1 三层进化模型

```
Layer 1: 经验沉淀 (每次迭代)
├─ learnings.json     — "做了什么、为什么、结果如何"
├─ failure_log.json   — 失败模式 + 根因分析
└─ decision_log.json  — 关键决策 + 理由 + 后果

Layer 2: 知识合成 (定期反思)
├─ patterns.md        — 从经验中提炼的可复用模式
├─ anti_patterns.md   — 项目特有的反模式清单
├─ design_lessons.md  — 架构/设计层面的经验教训
└─ rubric_evolution.md — 评价标准自身的迭代记录

Layer 3: 自我进化 (触发式)
├─ 评价标准迭代    — 基于积累经验提议更新 rubric
├─ 工作流优化      — 发现低效环节，提议改进循环流程
├─ 技能库扩展      — 新发现的最佳实践写入项目 knowledge base
└─ 架构洞察        — 跨迭代的架构趋势观察，提前预警
```

### 7.2 进化触发条件

| 触发条件 | 行为 |
|---------|------|
| 连续 5 次迭代积累后 | 触发一次反思合成 |
| 连续 3 次同类失败 | 立即触发根因分析 |
| 每个 Phase 完成后 | 全面反思 + 报告 |
| 发现新的设计模式 | 自动添加到 patterns.md |
| Rubric 项反复不适用 | 提议修改或删除该条目 |

### 7.3 知识进化示例

```
迭代 1-3: AI 发现 "Service 类过胖" 问题反复出现
  → 记入 decision_log: "拆分了 XService，从 300 行降到 80 行，测试更清晰"

迭代 5 (反思合成): 提炼为 anti_pattern
  → "Service 超过 200 行时职责模糊，必须拆分"

迭代 8 (进化): AI 提议将此条写入 rubric
  → rubric.md 新增: "项目特有 — Service 类不超过 200 行"

后续所有迭代: 代码自动按新标准评审，质量基线整体抬升
```

### 7.4 复用现有基础设施

| 现有设施 | 在系统中的角色 |
|---------|---------------|
| `.claude/rules/` | Rubric 的自然载体 |
| `memory/` | 经验沉淀的长期存储 |
| `/ditto-review` | L4 交叉评审的执行引擎 |
| `CLAUDE.md` | 架构约束的权威来源 |

---

## 8. 运行模式

### 8.1 模式 A: Goal-Driven (目标驱动)

适合有明确追赶目标和设计方向的场景。

```
输入: Goal + Preferences + Reference + Tasks (可选)

执行流程:
┌──────────────────────────────────────────────────┐
│ Phase 1: Goal Resolution                         │
│ ├─ 分析差距文档 → 拆解为可执行子目标               │
│ ├─ 建立度量基线                                   │
│ └─ 输出结构化计划                                 │
│                                                  │
│ Phase 2: Queue Execution                         │
│ ├─ 优先执行用户给的 Tasks                         │
│ └─ 每个任务: TDD → 实现 → 修复循环 → 四层评估      │
│                                                  │
│ Phase 3: Autonomous Supplement                   │
│ ├─ Queue 清空后，自主审计剩余改进点               │
│ ├─ 对标业界差距，发现新优化机会                    │
│ └─ 自主补充任务继续执行                           │
│                                                  │
│ Phase 4: Reflection & Report                     │
│ ├─ 全面对比 Goal → 评估完成度                     │
│ ├─ 合成知识 → 更新 knowledge base                 │
│ └─ 输出报告 → 创建 PR                             │
└──────────────────────────────────────────────────┘
```

### 8.2 模式 B: Karpathy Loop (度量驱动)

适合开放探索——让 AI 自主发现优化机会。

```
输入: Goal + Metric 定义 + Budget

执行流程:
┌──────────────────────────────────────────────────┐
│ Loop (直到目标达成或预算耗尽):                     │
│ ├─ 观察当前代码 + 度量                            │
│ ├─ 自主决定改什么                                 │
│ ├─ TDD → 实现 → 验证                             │
│ ├─ 重新度量                                      │
│ ├─ 评分提升? → 保留, 记录 "什么有效"               │
│ ├─ 评分下降? → 修复循环 (10 次) → 仍降则回滚      │
│ ├─ 记录本轮经验                                  │
│ └─ 达到目标 / 预算耗尽 → 报告 + PR                │
└──────────────────────────────────────────────────┘
```

### 8.3 模式串联

两种模式可串联执行：

```
Goal-Driven (执行主任务)
  → Karpathy Loop (开放优化剩余代码)
    → Report + PR
```

---

## 9. 用户交互

### 9.1 交互流程

```
1. START — 用户设定目标
2. RUNNING — AI 自主执行，用户不需要在场
3. CHECK — 用户随时可选查看进度 (非必须)
4. INTERVENE — 极少需要的人工干预
5. DONE — 用户 review PR
```

### 9.2 命令参考

```bash
# 启动
pixi run crossgate start --goal "..." [--mode goal-driven|karpathy] \
  [--reference file] [--tasks t1 t2] [--budget N|Nh]

# 状态
pixi run crossgate status

# 控制
pixi run crossgate pause|resume|abort
pixi run crossgate redirect "追加约束说明"

# 结果
pixi run crossgate report
```

### 9.3 输出产物

```
docs/crossgate/session/
├── plan.json           # 结构化执行计划
├── progress.json       # 实时进度
├── metrics.json        # 度量历史 (含趋势)
├── learnings.json      # 经验教训
├── failure_log.json    # 失败记录
├── decision_log.json   # 决策记录
├── session_log.md      # 人类可读日志
├── patterns.md         # 提炼的模式
├── anti_patterns.md    # 反模式清单
├── design_rubric.md    # 当前设计评价标准
└── report.md           # 最终报告
```

---

## 10. 容错与恢复 (借鉴 GSD v2 模式)

**核心理念：磁盘状态机 + 新鲜上下文 + 机械反馈。不依赖 heartbeat/watchdog/systemd。**

### 10.1 三级超时监控

每次 `claude -p` 子进程受三级超时约束：

```
┌─ 三级超时 ─────────────────────────────────────────┐
│                                                     │
│  软超时 (soft_timeout)                              │
│  ├─ 触发: 接近时间预算时                             │
│  ├─ 动作: 向 agent 发送提醒 "请尽快完成当前步骤"       │
│  └─ 目的: 让 LLM 优雅收尾，产出可用的中间结果         │
│                                                     │
│  空闲检测 (idle_timeout)                            │
│  ├─ 触发: 子进程 5 分钟无任何输出                     │
│  ├─ 动作: 判定为卡死，kill 子进程                     │
│  └─ 恢复: 合成恢复简报，重试同一任务 (最多 3 次)       │
│                                                     │
│  硬超时 (hard_timeout)                              │
│  ├─ 触发: 绝对时间上限 (如单次迭代 30 分钟)           │
│  ├─ 动作: 强制 kill，暂停当前任务                     │
│  └─ 恢复: 记录失败，跳到下一个任务                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 10.2 滑动窗口卡死检测

不只检测"有没有输出"，还检测**重复模式**：

```
最近 N 次迭代的工具调用模式:
├─ 如果连续 3 次执行相同的修复 → 同一个 fix 反复失败
├─ 触发深度诊断: 分析根因，换方案
└─ 诊断后仍失败 → 断路器跳过
```

### 10.3 崩溃恢复

所有状态持久化到磁盘，进程随时可以安全重启：

```
正常迭代:
  读状态 → 执行 → 写状态 → 下一个
                 ↑
                 └─ 每次迭代后立即 flush 到磁盘

进程崩溃 (kill -9 / OOM / 机器重启):
  → 丢失: 仅当前正在执行的未完成迭代
  → 保留: 所有已完成迭代的状态
  → 恢复: crossgate resume → 读 progress.json → 从断点继续

Provider 错误 (API 超时 / Rate Limit / 500):
  ├─ 瞬态错误 (429/500/503): 指数退避重试 (最多 3 次)
  ├─ 永久错误 (401/403): 暂停，等人工介入
  └─ 网络中断: 重试，多次失败则暂停
```

### 10.4 恢复简报合成

崩溃后重启时，不是"从头开始"，而是合成一份恢复简报：

```python
def synthesize_recovery_brief():
    """从磁盘状态合成恢复上下文，让新 agent 快速接上"""
    return f"""
    ## 恢复简报 (自动生成)

    ### 已完成 ({len(completed_tasks)} 个任务)
    {format_tasks(completed_tasks)}

    ### 当前任务
    {current_task.description}
    上次尝试失败原因: {failure_log.last_failure_reason}

    ### 经验教训 (从历史中提取)
    {learnings.recent_insights}

    ### 禁止重试的模式
    {anti_patterns.failed_approaches}
    """
```

### 10.5 隔离机制

| 机制 | 说明 |
|------|------|
| 分支隔离 | 每个 session 在独立 feature 分支上工作，不影响用户工作区 |
| 分支策略 | 所有工作在 feature 分支，PR 是唯一合入路径 |
| 自动快照 | 每次迭代 commit + tag，任何状态都可回滚 |
| Hook 门禁 | 现有 stop hook 保证 session 结束前质量检查 |

### 10.6 防护总结

| 风险 | 防护 |
|------|------|
| AI 死循环 | 10 次断路器 + 迭代预算上限 |
| LLM 卡死 | 三级超时 + 空闲检测 + kill + 重试 |
| LLM 崩溃 | 自动重试 (3 次) + 指数退避 |
| 编排器崩溃 | 磁盘状态机 + resume 恢复 |
| Provider 故障 | 瞬态重试 + 永久暂停 |
| 质量滑坡 | 四层评估 + before/after 对比 |
| 方向跑偏 | 进度文件可随时人工检查 + redirect 命令 |
| 重复失败 | 滑动窗口检测 + 深度诊断 + 换方案 |
| Token 浪费 | 预算控制 (迭代次数 / 时间上限) |
| 大范围破坏 | 分支隔离 + 每步 commit 可回滚 |

---

## 11. 实施路线

### Phase 1: MVP — 最小可用循环

- [ ] Python CLI 骨架 (`pixi run crossgate start|status|resume|abort`)
- [ ] 单次迭代循环 (读状态 → 选任务 → 执行 → 验证 → 提交)
- [ ] 状态文件管理 (progress.json, learnings.json, metrics.json)
- [ ] Git 分支隔离 + 自动 commit/tag
- [ ] 硬门禁集成 (`pixi run check`)
- [ ] 三级超时监控 (软超时 / 空闲检测 / 硬超时)
- [ ] 崩溃恢复 (磁盘状态机 + resume + 恢复简报合成)

### Phase 2: 评估体系

- [ ] L1 客观度量自动采集
- [ ] L2 Before/After 对比评审
- [ ] L3 Rubric 标准 (初始版本，基于现有 `.claude/rules/`)
- [ ] L4 交叉评审 (复用 `/ditto-review` 六维模式)
- [ ] 修复循环 + 10 次断路器

### Phase 3: 知识进化

- [ ] 经验沉淀自动化 (每次迭代写 learnings)
- [ ] 定期反思合成 (每 5 次迭代)
- [ ] Rubric 自进化 (基于积累经验提议更新)
- [ ] Patterns/Anti-patterns 自动提炼

### Phase 4: 模式完善

- [ ] Goal-Driven 模式 (Phase 1-4 自动执行)
- [ ] Karpathy Loop 模式 (度量驱动开放探索)
- [ ] 模式串联 (Goal-Driven → Karpathy)
- [ ] 定时调度 (cron/systemd 集成)
- [ ] `/crossgate` 斜杠命令

### Phase 5: 增强体验

- [ ] Web Dashboard (实时进度可视化)
- [ ] 失败趋势分析与预警
- [ ] 跨 session 知识迁移
- [ ] 多项目并行支持

---

## 12. 参考来源

| 来源 | 借鉴内容 |
|------|---------|
| [Karpathy autoresearch](https://github.com/karpathy/autoresearch) | 度量驱动循环、单一文件/指标约束、agent 编辑代码→实验→保留的范式 |
| [Addy Osmani: Self-Improving Agents](https://addyosmani.com/blog/self-improving-agents/) | 无状态循环、AGENTS.md 持久化、状态机设计 |
| [Ralph Loop](https://www.alibabacloud.com/blog/from-react-to-ralph-loop-a-continuous-iteration-paradigm-for-ai-agents_602799) | 原子任务分解、fresh agent per iteration、CI 作为质量门 |
| [Continuous Claude](https://github.com/AnandChowdhary/continuous-claude) | Claude Code 长程自动化编排 |
| [OpenAI Self-Evolving Agents](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining) | 元提示 + 评估循环 |

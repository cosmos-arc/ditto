# 材料迁移记录

这些清单是已执行路径变更的恢复证据，不维护任务进度；规格、验收结果和后续事项在
[Issue 111](https://github.com/cosmos-arc/ditto/issues/111)。

[2026-09-08 第二批清单](2026-09-08-batch-2.csv)逐项记录源路径、owner 归属、用途、
消费者、迁移理由、前后 SHA-256 与恢复提交。字节变化只来自路径引用同步；旧的原型
冻结记录按原始字节保留，当前记录由已提交源码重新捕获。

- SQL 与 R3 API 基线进入相应 owner 的 `tests/fixtures`，既有消费者验证 DDL 字节、
  canonical API hash 以及迁移/路由行为；没有执行真实数据迁移。
- Web 页面合同进入 `apps/web/contracts`，规格进入 `apps/web/design/specs`，
  原型进入 `apps/web/prototype`。使用现有 generator 与原型套件验收；archive 中仍有
  活跃测试的两份 AI 原型保留，CSS/HTML 资源引用随目录深度调整。
- Data、Features 和 Backend 专用指南靠近 owner；跨项目运维、架构、ADR、发布/安全
  规则仍在根 docs，统一入口链接 owner 的资料。
- 既有 `artifacts`、证据和二进制设计源不在本批删除范围；保留原内容身份。
  普通 archive/研究/计划材料仍待逐项退役核查，不能把本清单解释为批量清理授权。

从 `restore_commit` 使用 `git show <commit>:<source>` 可读取迁移前字节。
CSV 记录目标文件身份；它不是新的运行时配置或生成器输入。

## 第三批退役

[2026-09-08 退役清单](2026-09-08-batch-3-retirements.csv)记录 112 份普通历史实施计划和
一个旧验证脚本的用途、依赖核查、替代入口、SHA-256 与恢复提交。先按正文标题保留设计、
报告和未知材料，再对全体 tracked 文本查找路径/文件名，递归保留被其他保留材料引用的计划；
另核查源码、测试、生成器和 Task/CI 对目录的消费。没有以日期、目录名或体积直接删除整棵 archive。

旧脚本仍被两份历史说明提及；其引用保留历史语境并加退役提示，恢复链接固定到退役前提交。
该脚本依赖已退出的 Pixi/ditto_port，包含数据库/Parquet 删除和真实摄入，未运行。
当前验证与显式真实数据验收分别使用根 Task 和对应验收入口。

其余设计、被引用计划、评审、证据、发布材料及机器基线保留。清单是历史身份记录，后续对
仍活跃文档的正常引用修复不会回写第二批的旧 hash。敏感本地处置清单只保存在本机，不提交仓库。

## 保留材料快照

[2026-09-08 保留清单](2026-09-08-retained-materials.csv)记录 `fd8cd17a` 中根 docs、
Web docs/design/prototype/contracts、Backend/Data/Features owner 文档、根 artifacts
及知识政策声明的机器输入。每行包含路径、用途分类、SHA-256、同字节文件数量、
字面引用候选、Git 保存基线与保留决定。不包含工作区未提交文件或个人运行状态。

分类用于分流核查，不以目录名证明过时。`literal_reference_candidates` 是 tracked
文本中的完整路径或长文件名命中，不是已证明的调用关系；空值也不证明无消费者，
因为目录枚举、相对路径和动态生成可能不出现文件名。同 hash 只证明快照中字节相同，
不证明上下文可互换。所有条目继续保留，未假定存在外部长期副本。

| 材料族 | 实际用途与消费者 | 本次处置 |
| --- | --- | --- |
| 根 artifacts/acceptance 与 docs/evidence | R2/R3 验收读取前置报告、manifest 和内容身份；后端 scripts 下的验收测试覆盖消费者 | 保留现有 tracked 输入；新普通输出由忽略规则隔离 |
| Web contracts、prototype 与冻结记录 | 页面合同生成器、原型测试、capture-prototype-baseline 实际读取 | 保留；不以截图替代可编辑源 |
| 根/Web 验收 JSON、图片及发布证明索引 | 固定提交的人工/机器验收记录；部分只供历史复核 | 保留；未上传或删除唯一材料 |
| DOCX、设计 Markdown、ADR | 编辑源及取舍语境，未证明跨格式等价 | 分别保留 |
| 其余历史、owner 材料与引用不明项 | 当前入口/历史解释或待进一步核查，逐文件候选见 CSV | 保留；不作为失效入口执行 |

`.github/workflows/release.yml` 已将完整 cohort 和关联证明发布为 Release 附件，
普通 Actions artifact 的配置留存期为 90 天。这里记录实现的保存机制，不声称本次
已发布 Release、验证所有历史远端副本或获得永久可用保证。

## Web 失效工具退役

[2026-09-08 Web 退役清单](2026-09-08-web-retirements.csv)只包含
`apps/web/scripts/audit-tokens.mjs`。该历史提取脚本读取不存在的原型和 token 目录，
输出旧计划目录下的原始报告。tracked 调用方核查仅发现其自身用法注释；现行
`audit:tokens` 使用独立的 WCAG 和 token dead-link 工具，保留不变。
此处不是将历史原始报告生成能力移交给现行审计，也没有删除其他视觉工具或材料。
按 CSV 中固定提交与源路径可恢复原字节。

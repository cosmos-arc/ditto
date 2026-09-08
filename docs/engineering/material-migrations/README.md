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

# 任务交付与通用技能适配

从[文档入口](../README.md)找到当前 owner；[根 AGENTS](../../AGENTS.md)路由局部约束、
架构、契约与测试。小任务直接实现并按风险验证；复杂任务只补齐影响结果的规格、依赖
与决定，复用 Issue 中已确认的测试边界和授权。GitHub 操作见[任务记录约定](../agents/issue-tracker.md)。

## 技能来源与宿主

通用方法来自 [mattpocock/skills](https://github.com/mattpocock/skills/tree/3cca18b368ae95cdbdebbff572ccafa662551015)，
固定核查版本为 `3cca18b368ae95cdbdebbff572ccafa662551015`（Issue 111 的 2026-09-08 核查基线）。
该版本是可复现来源，并非自动升级通道。项目 skill 的唯一编辑源及镜像规则见
[Harness](agent-harness.md#skills)。通用 skills 不复制到项目中。

需要安装或核查通用技能时，在独立临时目录检出固定来源，选择用户要求的 skill：

```bash
git clone https://github.com/mattpocock/skills.git /tmp/ditto-matt-skills
git -C /tmp/ditto-matt-skills checkout --detach 3cca18b368ae95cdbdebbff572ccafa662551015
git -C /tmp/ditto-matt-skills rev-parse HEAD
# 以实际安装目录替换最后一个参数；比较整个 skill，不只比较 SKILL.md。
diff -r /tmp/ditto-matt-skills/skills/engineering/implement /path/to/installed/implement
```

安装由宿主支持的 installer 将选定目录放入其发现位置；只有用户要求安装/更新时才写入。
记录来源 SHA、skill 名称、安装位置、完整目录比较结果与宿主发现结果。升级先比较内容及
以下兼容表，再在典型任务验证；不修改用户全局副本来修正 Ditto 专属行为。

| 宿主 | 项目技能与调用 |
|---|---|
| Claude Code | 发现 `.claude/skills` 生成镜像；使用宿主支持的技能调用入口 |
| Codex | 发现 `.agents/skills`；有技能工具则调用，否则按已解析路径读取 `SKILL.md` 与引用并执行 |
| ZCode | 直接发现 `.agents/skills`；按实际可用调用能力执行，hooks 使用 `hooks.events` |

静态 validator 成功只证明配置与内容结构。宿主是否实际发现、信任并触发必须分别记录；
不可用或需要用户信任的入口标记未执行，保留原信任设置。

## 项目适配

| 通用步骤 | Ditto 执行约定 |
|---|---|
| 自动探测包管理器/测试命令 | 使用根 Task DAG、uv/Python 与 Bun/Web；版本及准备见[工具链](toolchain.md) |
| 安装 Husky、lint-staged 等 hooks | 先核对现有 pre-commit 和三个宿主 hooks；当前任务未要求更换时继续使用现有入口 |
| tdd 选择测试 seam | 复用已确认的 Issue 测试边界；新增边界才需要澄清，纯移动和文档通过真实消费者验收 |
| implement → code-review → commit | 先形成已提交实现范围再审查，遵循下文提交与交付流程 |
| 宿主不存在的 Skill/子代理命令 | 读取实际可用技能内容；使用可用能力，未执行的独立审查明确报告 |

## 提交、审查与交付

1. 记录 Issue、本批范围与起始 SHA。大型迭代使用独立 worktree 和 `codex/` 分支；
   main 上有用户成果时保留原件，只迁入任务明确要求的材料。
2. 按[测试指南](testing.md)实现并验证。`check-changed` 观察 pending/staged/untracked；
   pre-push 使用实际提交范围。只读检查无需为已有脏文件启动全库验证。
3. 将本批实现提交在实施分支。固定比较基线和当前 HEAD，检查
   `git diff <base>...HEAD` 非空、`git log <base>..HEAD --oneline` 包含待交付实现；
   确认无遗漏的未提交实现后，执行需求与规范两轴审查。空差异不能证明未提交实现已被审查。
4. 处理有效发现，提交修复并检查新增差异。验证记录绑定 SHA、路径范围、命令、结果和
   关键工具版本；本地 receipt 仅复用完全相同证据，CI/发布证明仍需当前提交身份。
5. 创建关联 Issue 的 PR，核对 PR HEAD 与成功 CI 的 SHA 一致，适用检查全部通过后
   标记待维护者合并。有效门失败则修复或记录精确阻断；不以跳过门禁取得绿灯。
6. 维护者决定合并。分批任务等待前置 PR 合并再开始依赖批，全部验收成立后才关闭任务。
   本批待合并、整个任务完成是不同状态。

## 同一 Issue 的交接记录

在 Issue 追加简短交接，保持规格正文和确认决定可追溯，不另建持续更新的仓库进度文件：

- 本批目标与已确认决定（引用原决定，写明新增决定）。
- 分支、worktree、比较基线、当前 SHA、PR 链接；未提交改动及归属。
- 已完成内容与验证：对应 SHA/范围、命令、成功/失败/适用性跳过/未执行、证据位置。
- 尚未解决的发现、外部限制、后续批依赖与下一步；待合并明确标记。

本地绝对路径仅在不含敏感信息且有交接必要时分享；密钥、真实配置、数据库与个人运行
内容留在本地。典型小任务与真实跨会话接手的结果另作实际工作流证据，不能用预填 policy
测试结果声称模型能力已经验收。

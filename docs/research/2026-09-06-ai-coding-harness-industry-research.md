# AI Coding Harness：减负的一手证据

调研日期：2026-09-06。以下原文均已打开核实；持续更新的产品文档没有可靠发布日期，按访问日记录。厂商经验、独立实验、平台行为分别列出，不能互相替代。本文只提供外部证据，Ditto 的具体删除项须结合本库调用链、失败记录和 CI 耗时判断。

**建议方向：缩短通用流程指令，保留项目特有知识和可执行验收；让模型决定实现路径，让工具提供事实反馈。** 当前证据支持试删冗余指导，不支持因模型升级而取消正确性检查。

## 近期厂商实践

- **OpenAI 当前模型指南（访问日：2026-09-06）**：GPT-6 Astra 更容易受 Skills、AGENTS.md 中的指令影响，官方要求审计冲突和隐含阻塞；测试应匹配变更影响，完成必要检查后，只有新改动、失败或未决疑点才扩大或重复验证。这支持删除重复全量检查和低价值测试要求，但仍要求完成必要门禁。[OpenAI Docs：Model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- **OpenAI GPT-5.5 指南（访问日同上）**：迁移先建立新基线，从保留产品约束的最小提示开始；描述目标、成功标准和约束，让模型选择路径；绝对规则留给真正不变量，判断性事务使用决策规则。这直接支持将固定的「先读若干文档、必须走完整阶段」改为按需选择。[GPT-5.5 guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5)
- **Anthropic（2026-07-24）**：作者报告对新一代 Claude 删除超过 80% 的 Claude Code 系统提示，在内部 coding eval 中未测得损失；将 review、verification 移入按需加载的 Skills，建议只留下团队独有知识和易踩坑事项。**这是厂商内部结果，未公开足以独立复现的完整实验，80% 不能作为 Ditto 的删除指标。**[Context engineering for Claude 5](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
- **Claude Code 文档（访问日同上）**：持续删去模型无需提示也能正确执行的内容，同时给出可运行检查、截图等验收证据。模型自报完成不足以形成反馈闭环；流程可以轻，验收仍须明确。[Best practices](https://code.claude.com/docs/en/best-practices)

## 独立实验：不能把「少指令」当成普适定律

| 原始研究与日期 | 观察 | 适用限制 |
| --- | --- | --- |
| [Evaluating AGENTS.md，v2，2026-06-23](https://arxiv.org/html/2602.11988v2) | 在 SWE-bench Lite 与 138 个 CTXbench 任务上，上下文文件没有显著提升解决率，增加推理成本；自动生成文件的成本平均增加 20% / 23%。 | Python 任务；模型包括 Sonnet 4.5、GPT-5.2 等。开发者文件比自动生成文件更好，但相对无文件的提升不显著。不能沿用 v1 的表述，将结果说成已证明文件降低正确率。 |
| [Probe-and-Refine，v2，2026-06-19](https://arxiv.org/html/2606.20512v2) | 依据失败探针迭代指导，Qwen3.5-35B-A3B 在 SWE-bench Verified 的平均解决率从无指导 25.5% 提到 33.0%。 | 单一主要有效模型和 benchmark；收益主要来自产出可评估补丁的覆盖度，补丁精度未显著变化，跨模型迁移会恶化。它支持按失败修订知识，不能证明通用长流程有益。 |
| [Two-Agent Ablation，v1，2026-07-28](https://arxiv.org/html/2607.27250v1) | 3 个 Python 仓库、17 个任务、288 次可评估运行；Sonnet 4.6 / GPT-5.5 在无上下文、常驻与按需加载间未测得正确率收益。 | 样本很小，作者承认检测能力不足；注入渠道与资料体量存在混杂，不能推出严格等效或「所有 AGENTS.md 无用」。 |

这些是预印本研究结果，并非 Ditto 的验证结果。共同启示是评估**具体内容是否改变结果**，而非根据文件数量、长度或模型排名决定去留。

## CI：减少重复，维持明确的合并条件

GitHub 明确区分 strict 与 loose required checks：前者要求分支跟上目标分支，因此构建更多；后者减少重复构建，但可能在合并后暴露组合不兼容。选择依据应是并发合并频率与失败成本，而非模型能力。[Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

按路径选择任务时，要保留清晰的完成状态：工作流被路径过滤跳过会使 required check 留在 Pending；条件跳过的 job 则可报告成功；依赖失败后被跳过的下游 job 还可能不阻止合并。GitHub 建议对依赖其他 job 的必需检查使用 `always()` 与 `needs`，并实际检查上游结果。[Required checks troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)

对 Ditto 的可执行推论：迭代时运行目标检查，PR 运行必要汇总检查；删除重复入口，保留同一事实源。高成本全栈检查是否按影响范围触发，需要先确认路径分类不会漏掉间接消费者。不能把一个笼统绿色状态当作所有任务都已成功。

## 最小验证方式

先选近期真实任务做小规模对照：原指导与精简指导使用同一模型、同一提交、同一验收，比较解决率、返工、人工干预、token、等待时间及重复测试次数。小样本用于发现明显退化，不宣称统计等效。通用流程先删，项目特有约束暂留；出现可复现失败时，只恢复能解释该失败的最小指导。

PIT 可见性、账户记账、API 契约和依赖方向的机器检查各自有可证伪对象；「必须读完某套流程」「必须产出指定章节」若没有对应失败记录，可优先降为建议。外部研究不能单独证明需要替换 Pixi、Bun、React 或 FastAPI；技术栈调整仍应由本库安装成本、兼容问题和实际维护负担驱动。

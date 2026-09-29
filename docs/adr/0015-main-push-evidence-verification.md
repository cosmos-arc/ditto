# ADR 0015：main push 收窄选择的机器证据核验

日期：2026-09-29　状态：已实施（#351）　关联：ADR0011、#310/#317/#324/#351

## 背景

push 到 main 的 CI 选择自 #310 起收窄为"常驻安全检查 + 跨平台 smoke"，
依据是"PR 已验证等价内容"。但这一信任此前是隐式的：没有机器核验合并
提交确实对应一个已通过 CI 的 PR、其被测内容与最终 main 内容一致。
票据 #324 明确：不能把无机器核验的信任称为已完成移交。

## 决策

push 到 main 时，repository-policy 先执行
`tooling.agent_harness.main_evidence`（三腿身份链核验）：

1. **合并关联**：该提交存在 state=merged 且 `merge_commit_sha` 等于
   本次 push SHA 的 PR（squash 合并语义下成立）；
2. **head 验证成功**：PR head SHA 上存在 GitHub Actions 的
   "CI gate" check-run 且 conclusion=success——被测 SHA 即验证 SHA；
3. **树同一**：head 提交与 main 提交的 tree OID 相同——tested tree
   即最终 tree 时，workflow/selector/toolchain 等一切规则文件不可能
   与被测版本漂移（树同一性是比"敏感文件逐个比对"更强的证据）。

三腿全部通过 → 维持收窄选择；任一缺失、不匹配或 API 查询失败 →
**退回 REQUIRED_JOBS 全量**（全量始终可执行，优于让 run 失败）。

## 边界与不变量

- 时效性输入（安全数据库、OSV 等）不能由树同一证明——这些检查本就
  每次照跑（`_ALWAYS` 含 security-supply-chain），不在信任范围内。
- squash 时 base 已移动 → 树不同 → 全量，属预期保守行为。
- 周度 schedule 与未知范围仍走全量路径，不受影响。
- 精确 main push 身份与发布前置合同不变；本核验只影响选择集。
- 恢复路径：核验退全量后无需任何手动动作；不允许以绕过核验换回收窄。

## 后果

- main 每次收窄运行都有可追溯的核验日志（reasons 进 step 输出）。
- #324/#352 的影子观察期在此基础上累计（≥7 天/10 SHA）。

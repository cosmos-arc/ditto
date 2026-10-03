# 远端 CI 临时暂停记录

2026-10-03，维护者明确授权暂停 `cosmos-arc/ditto` 的远端 CI，整改期间仅做本地
review 和适用验证，完成后统一重构 CI。未修改业务代码或 workflow 文件。

- 仓库 Actions：`enabled: true` → `false`，已通过 API 回读确认。
- `ditto-main` ruleset（11363741）：仅移除 required status check `CI gate`；
  其余规则、作用分支、enforcement 和 bypass 配置与变更前一致，已回读比较。
- 查询 `in_progress`、`queued`、`requested`、`waiting`、`pending` 状态的运行均为空，
  无需取消既有运行。
- 未提交 Actions 允许列表或 SHA 固定策略变更。关闭后允许列表 API 返回 HTTP 409
  （GitHub Actions is disabled on this repository），因此仅保留变更前快照，
  不宣称已回读确认其关闭后的值。
- 未调整独立 Dependabot 更新或 Secret Protection。Dependabot 更新可能绕过 Actions
  禁用，参见 [GitHub 官方说明](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-on-actions)。

本目录保存 Actions 权限、允许列表、workflow、CodeQL default setup 和 ruleset 的
变更前快照；`main-ruleset-request.json` 是实际更新内容，两个 `*-after.json`
是变更后回读结果。快照用于追溯，不是自动恢复指令。

本地交付遵循[临时交付策略](../../../engineering/development-workflow.md#整改期间的临时交付策略2026-10-03)。
整改结束后先重构 CI，由维护者确认重新启用 Actions 及新的合并检查要求，不自动恢复旧门禁。

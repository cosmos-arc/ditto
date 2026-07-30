import type { ReactElement } from "react";
import { useState } from "react";
import type { StrategyLifecycleState, StrategyVersion } from "@/types/strategy";
import { useStrategyGovernance } from "../hooks/use-strategy-governance";
import { DecisionDialog, ReactivateDialog } from "./governance-dialogs";

type DecisionKind = "submit" | "approve" | "reject" | "deprecate";
type DialogKind = DecisionKind | "reactivate" | null;

interface GovernanceActionsProps {
	readonly strategyId: string;
	readonly version: StrategyVersion;
	/** 当前 active pointer revision（reactivate 乐观 CAS 基线；null 时隐藏 reactivate）。 */
	readonly expectedPointerRevision: number | null;
}

interface ActionDef {
	readonly kind: DecisionKind;
	readonly label: string;
	readonly title: string;
	readonly confirmLabel: string;
}

const ACTIONS_BY_STATE: Partial<Record<StrategyLifecycleState, readonly ActionDef[]>> = {
	draft: [{ kind: "submit", label: "提交审查", title: "提交审查", confirmLabel: "确认提交" }],
	review: [
		{ kind: "approve", label: "批准", title: "批准审查", confirmLabel: "确认批准" },
		{ kind: "reject", label: "驳回", title: "驳回审查", confirmLabel: "确认驳回" },
	],
	approved: [{ kind: "deprecate", label: "弃用", title: "弃用版本", confirmLabel: "确认弃用" }],
	published: [{ kind: "deprecate", label: "弃用", title: "弃用版本", confirmLabel: "确认弃用" }],
};

const DECISION_TITLES: Record<DecisionKind, { readonly title: string; readonly confirmLabel: string }> = {
	submit: { title: "提交审查", confirmLabel: "确认提交" },
	approve: { title: "批准审查", confirmLabel: "确认批准" },
	reject: { title: "驳回审查", confirmLabel: "确认驳回" },
	deprecate: { title: "弃用版本", confirmLabel: "确认弃用" },
};

type Governance = ReturnType<typeof useStrategyGovernance>;

function isDecisionPending(governance: Governance, kind: DecisionKind): boolean {
	switch (kind) {
		case "submit":
			return governance.submitReview.isPending;
		case "approve":
			return governance.approve.isPending;
		case "reject":
			return governance.reject.isPending;
		case "deprecate":
			return governance.deprecate.isPending;
	}
}

/**
 * 版本治理动作面板（接入 StrategyVersionsView 每行）。
 *
 * 按 `version.lifecycleState` 渲染可用决策动作 + reactivate（published 且持有 active pointer
 * revision 时）。publish 不在此面板——它是 evidence-gated（需 review packet 的 bundle_hash），
 * 由 review-detail 页的 `ReviewDecisionPanel` 在 approved 结论下执行。决策动作经
 * DecisionDialog（actor+reason），reactivate 经 ReactivateDialog（type-to-confirm + CAS）。
 */
export function GovernanceActions({
	strategyId,
	version,
	expectedPointerRevision,
}: GovernanceActionsProps): ReactElement {
	const governance = useStrategyGovernance(strategyId);
	const [dialog, setDialog] = useState<DialogKind>(null);

	const actions = ACTIONS_BY_STATE[version.lifecycleState] ?? [];
	const canReactivate = version.lifecycleState === "published" && expectedPointerRevision !== null;
	const activeDecision = dialog !== null && dialog !== "reactivate" ? dialog : null;
	const decisionMeta = activeDecision ? DECISION_TITLES[activeDecision] : null;

	function dispatchDecision(kind: DecisionKind, actor: string, reason: string): void {
		const variables = { version: version.version, actor, reason };
		switch (kind) {
			case "submit":
				governance.submitReview.mutate(variables);
				break;
			case "approve":
				governance.approve.mutate(variables);
				break;
			case "reject":
				governance.reject.mutate(variables);
				break;
			case "deprecate":
				governance.deprecate.mutate(variables);
				break;
		}
		setDialog(null);
	}

	return (
		<>
			<div className="flex items-center gap-1">
				{actions.map((action) => (
					<button
						key={action.kind}
						type="button"
						onClick={() => setDialog(action.kind)}
						className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						{action.label}
					</button>
				))}
				{canReactivate && (
					<button
						type="button"
						onClick={() => setDialog("reactivate")}
						className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						重新激活
					</button>
				)}
			</div>

			{activeDecision && decisionMeta && (
				<DecisionDialog
					open
					onOpenChange={(open) => {
						if (!open) setDialog(null);
					}}
					title={decisionMeta.title}
					confirmLabel={decisionMeta.confirmLabel}
					isPending={isDecisionPending(governance, activeDecision)}
					onConfirm={(actor, reason) => dispatchDecision(activeDecision, actor, reason)}
				/>
			)}

			{dialog === "reactivate" && canReactivate && expectedPointerRevision !== null && (
				<ReactivateDialog
					open
					onOpenChange={(open) => {
						if (!open) setDialog(null);
					}}
					strategyId={strategyId}
					targetVersion={version.version}
					expectedPointerRevision={expectedPointerRevision}
					isPending={governance.reactivate.isPending}
					onConfirm={(variables) => {
						governance.reactivate.mutate(variables, {
							onSuccess: () => setDialog(null),
						});
					}}
				/>
			)}
		</>
	);
}

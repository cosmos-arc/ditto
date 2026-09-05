/**
 * Review-detail 决策面板（审查者在 review-detail 页执行的动作）。
 *
 * 按 review_outcome 渲染：pending → 批准/驳回；approved → 发布（evidence-gated，
 * 需 packet 的 bundle_hash 且 !hard_review_blocked）+ 弃用。publish 的证据身份
 * （bundle_hash）由 review-detail 页从 packet 注入。HARD GATE 阻断时 publish 禁用
 * （服务端 StrategyPromotionProcess 强制，UI 反射 hard_review_blocked）。
 */
import type { ReactElement } from "react";
import { useState } from "react";
import { ContextSection } from "@/components/domain/context-section";
import { Button } from "@/components/ui/button";
import { useStrategyGovernance } from "../hooks/use-strategy-governance";
import { DecisionDialog, PublishDialog } from "./governance-dialogs";

type DialogKind = "approve" | "reject" | "publish" | "deprecate" | null;

interface ReviewDecisionPanelProps {
	readonly strategyId: string;
	readonly version: number;
	readonly reviewOutcome: string;
	readonly hardReviewBlocked: boolean;
	readonly bundleHash: string;
	readonly experimentId?: string | undefined;
}

export function ReviewDecisionPanel({
	strategyId,
	version,
	reviewOutcome,
	hardReviewBlocked,
	bundleHash,
	experimentId,
}: ReviewDecisionPanelProps): ReactElement {
	const governance = useStrategyGovernance(strategyId);
	const [dialog, setDialog] = useState<DialogKind>(null);

	const isPending = reviewOutcome === "pending";
	const canPublish = reviewOutcome === "approved" && !hardReviewBlocked;

	function dispatchDecision(kind: "approve" | "reject" | "deprecate", actor: string, reason: string): void {
		const variables = { version, actor, reason, experimentId };
		if (kind === "approve") governance.approve.mutate(variables);
		else if (kind === "reject") governance.reject.mutate(variables);
		else governance.deprecate.mutate(variables);
		setDialog(null);
	}

	return (
		<ContextSection title="Decision Form">
			<div className="flex flex-wrap items-center gap-2 p-3">
				{isPending && (
					<>
						<Button
							size="sm"
							disabled={hardReviewBlocked}
							title={hardReviewBlocked ? "hard-gate 阻断，不可批准" : "批准审查"}
							onClick={() => !hardReviewBlocked && setDialog("approve")}
						>
							批准
						</Button>
						<Button size="sm" variant="outline" onClick={() => setDialog("reject")}>
							驳回
						</Button>
					</>
				)}
				{reviewOutcome === "approved" && (
					<>
						<Button
							size="sm"
							disabled={!canPublish}
							title={canPublish ? "使用 review packet 的 bundle_hash 发布" : "hard-gate 阻断，不可发布"}
							onClick={() => canPublish && setDialog("publish")}
						>
							发布
						</Button>
						<Button size="sm" variant="destructive" onClick={() => setDialog("deprecate")}>
							弃用
						</Button>
					</>
				)}
				{reviewOutcome === "rejected" && (
					<Button asChild size="sm" variant="outline">
						<a href={`/research/strategies/${encodeURIComponent(strategyId)}/studio`}>克隆为新草稿</a>
					</Button>
				)}
				{!isPending && reviewOutcome !== "approved" && reviewOutcome !== "rejected" && (
					<span className="text-xs text-(--color-foreground-tertiary)">当前结论 {reviewOutcome}，无可执行动作。</span>
				)}
			</div>

			{(dialog === "approve" || dialog === "reject" || dialog === "deprecate") && (
				<DecisionDialog
					open
					onOpenChange={(open) => {
						if (!open) setDialog(null);
					}}
					title={dialog === "approve" ? "批准审查" : dialog === "reject" ? "驳回审查" : "弃用版本"}
					confirmLabel={dialog === "approve" ? "确认批准" : dialog === "reject" ? "确认驳回" : "确认弃用"}
					isPending={
						dialog === "approve"
							? governance.approve.isPending
							: dialog === "reject"
								? governance.reject.isPending
								: governance.deprecate.isPending
					}
					onConfirm={(actor, reason) => dispatchDecision(dialog, actor, reason)}
				/>
			)}
			{dialog === "publish" && canPublish && (
				<PublishDialog
					open
					onOpenChange={(open) => {
						if (!open) setDialog(null);
					}}
					targetVersion={version}
					bundleHash={bundleHash}
					isPending={governance.publish.isPending}
					onConfirm={(variables) => {
						governance.publish.mutate({ ...variables, experimentId });
						setDialog(null);
					}}
				/>
			)}
		</ContextSection>
	);
}

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
	useDecideRemediationApproval,
	useDraftFallbackPolicy,
	useExecuteRemediationApproval,
	useRequestRemediationApproval,
	useRevokePromotion,
	useTransitionFallbackPolicy,
} from "../hooks/use-data-product-operations";
import type {
	FallbackPolicyView,
	FallbackPreviewView,
	PromotionReadinessView,
	RemediationApprovalView,
	RemediationItemDetailView,
} from "../types/operations";

type GovernanceSheet = "fallback" | "promotion" | "remediation-decision" | "remediation-request" | null;

interface DataProductGovernanceActionsProps {
	readonly approvals: readonly RemediationApprovalView[];
	readonly datasetId: string;
	readonly fallbackPolicies: readonly FallbackPolicyView[];
	readonly fallbackPreview: FallbackPreviewView | undefined;
	readonly promotion: PromotionReadinessView | null | undefined;
	readonly remediationDetail: RemediationItemDetailView | undefined;
	readonly tradeDate: string;
}

const INPUT_CLASS =
	"h-8 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 font-data text-xs text-(--color-foreground) outline-none focus-visible:border-(--color-focus-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)";

function JsonPreview({ value, label }: { readonly label: string; readonly value: Readonly<Record<string, unknown>> }) {
	return (
		<div>
			<p className="mb-1 text-xs text-(--color-foreground-tertiary)">{label}</p>
			<pre className="max-h-52 overflow-auto rounded-(--radius-sm) bg-(--color-surface-strip) p-3 font-data text-xs whitespace-pre-wrap text-(--color-foreground-secondary)">
				{JSON.stringify(value, null, 2)}
			</pre>
		</div>
	);
}

function Field({
	label,
	value,
	mono = false,
}: {
	readonly label: string;
	readonly mono?: boolean;
	readonly value: string;
}) {
	return (
		<div className="grid grid-cols-[7rem_1fr] gap-2 text-xs">
			<span className="text-(--color-foreground-tertiary)">{label}</span>
			<span className={mono ? "break-all font-data" : "break-words"}>{value}</span>
		</div>
	);
}

function latestApproval(approvals: readonly RemediationApprovalView[]): RemediationApprovalView | undefined {
	return [...approvals].sort((left, right) => right.requestedAt.localeCompare(left.requestedAt))[0];
}

function currentPolicy(policies: readonly FallbackPolicyView[]): FallbackPolicyView | undefined {
	return [...policies]
		.sort((left, right) => right.createdAt.localeCompare(left.createdAt))
		.find((policy) => policy.status !== "retired");
}

function isExpired(expiresAt: string): boolean {
	const timestamp = Date.parse(expiresAt);
	return Number.isFinite(timestamp) && timestamp <= Date.now();
}

function mutationError(...errors: readonly (Error | null)[]): string | null {
	return errors.find((error) => error !== null)?.message ?? null;
}

export function DataProductGovernanceActions({
	approvals,
	datasetId,
	fallbackPolicies,
	fallbackPreview,
	promotion,
	remediationDetail,
	tradeDate,
}: DataProductGovernanceActionsProps) {
	const [sheet, setSheet] = useState<GovernanceSheet>(null);
	const [actor, setActor] = useState("operator");
	const [confirmation, setConfirmation] = useState("");
	const [revocationReason, setRevocationReason] = useState<
		"evidence_invalidated" | "failed_revalidation" | "manual_override" | "policy_regression"
	>("failed_revalidation");
	const [lastResult, setLastResult] = useState<string | null>(null);
	const approval = useMemo(() => latestApproval(approvals), [approvals]);
	const policy = useMemo(() => currentPolicy(fallbackPolicies), [fallbackPolicies]);
	const intent = remediationDetail?.approvalIntents[0];
	const requestApproval = useRequestRemediationApproval(datasetId);
	const decideApproval = useDecideRemediationApproval(datasetId);
	const executeApproval = useExecuteRemediationApproval(datasetId, tradeDate);
	const draftFallback = useDraftFallbackPolicy(datasetId);
	const transitionFallback = useTransitionFallbackPolicy(datasetId, tradeDate);
	const revokePromotion = useRevokePromotion(datasetId, tradeDate);
	const isPending =
		requestApproval.isPending ||
		decideApproval.isPending ||
		executeApproval.isPending ||
		draftFallback.isPending ||
		transitionFallback.isPending ||
		revokePromotion.isPending;
	const error = mutationError(
		requestApproval.error,
		decideApproval.error,
		executeApproval.error,
		draftFallback.error,
		transitionFallback.error,
		revokePromotion.error,
	);

	function open(nextSheet: Exclude<GovernanceSheet, null>): void {
		setConfirmation("");
		setLastResult(null);
		setSheet(nextSheet);
	}

	function closeWithResult(message: string): void {
		setLastResult(message);
		setConfirmation("");
		setSheet(null);
	}

	const exactApprovalLoaded =
		approval !== undefined &&
		approval.authorityHash.length === 64 &&
		approval.expiresAt.length > 0 &&
		Object.keys(approval.requestPayload).length > 0;
	const approvalExpired = approval ? isExpired(approval.expiresAt) : true;
	const remediationPhrase = approval
		? `remediation:${approval.status === "approved" ? "execute" : "approve"}:${approval.authorityHash}`
		: "";
	const fallbackAction = policy?.authorityPayload.action;
	const fallbackPhrase = policy ? `fallback:${String(fallbackAction)}:${policy.authorityHash}` : "";
	const draftPhrase = fallbackPreview
		? `fallback:draft:${datasetId}:${tradeDate}:${fallbackPreview.selectedSource}`
		: "";
	const promotionPhrase = `promotion:revoke:${datasetId}:${tradeDate}:confirm`;

	return (
		<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3" aria-label="受治理写动作">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div>
					<h3 className="text-sm font-medium">Governed actions</h3>
					<p className="text-xs text-(--color-foreground-tertiary)">
						所有写入先展示精确作用域，再由后端校验 authority。
					</p>
				</div>
				<div className="flex flex-wrap gap-2">
					{intent && (
						<Button type="button" size="xs" variant="outline" onClick={() => open("remediation-request")}>
							预览 remediation request
						</Button>
					)}
					{approval && (
						<Button type="button" size="xs" variant="outline" onClick={() => open("remediation-decision")}>
							检查 remediation approval
						</Button>
					)}
					{policy ? (
						<Button type="button" size="xs" variant="outline" onClick={() => open("fallback")}>
							检查 fallback {String(fallbackAction)}
						</Button>
					) : (
						fallbackPreview && (
							<Button type="button" size="xs" variant="outline" onClick={() => open("fallback")}>
								预览 fallback draft
							</Button>
						)
					)}
					{promotion?.active && (
						<Button type="button" size="xs" variant="destructive" onClick={() => open("promotion")}>
							撤销晋级
						</Button>
					)}
				</div>
			</div>
			{lastResult && (
				<p role="status" className="mt-3 text-xs text-(--color-led-success)">
					{lastResult}
				</p>
			)}

			<Sheet
				open={sheet !== null}
				onOpenChange={(nextOpen) => {
					if (!nextOpen && !isPending) setSheet(null);
				}}
			>
				<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-xl">
					<SheetHeader>
						<SheetTitle>精确治理动作</SheetTitle>
						<SheetDescription>
							{datasetId} · provider {fallbackPreview?.selectedSource ?? remediationDetail?.item.source ?? "—"} ·{" "}
							{tradeDate}
						</SheetDescription>
					</SheetHeader>

					<div className="flex flex-col gap-4">
						{sheet === "remediation-request" && intent && remediationDetail && (
							<>
								<Field label="item" value={remediationDetail.item.itemId} mono />
								<Field label="action" value={intent.action} mono />
								<JsonPreview label="Exact request payload" value={intent.requestTemplate} />
								<p className="text-xs text-(--color-foreground-secondary)">
									提交后由后端冻结 payload，并返回 authority hash 与有效期；此步骤不会执行修复。
								</p>
							</>
						)}

						{sheet === "remediation-decision" && approval && (
							<>
								<Field label="approval" value={approval.approvalId} mono />
								<Field label="status" value={approval.status} />
								<JsonPreview label="Exact action payload" value={approval.requestPayload} />
								<Field label="authority hash" value={approval.authorityHash || "missing"} mono />
								<Field label="expires at" value={approval.expiresAt || "missing"} mono />
								{approvalExpired && (
									<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
										approval expired；审批与执行均已禁用。
									</p>
								)}
							</>
						)}

						{sheet === "fallback" &&
							(policy || fallbackPreview) &&
							(policy ? (
								<>
									<JsonPreview label="Exact fallback authority payload" value={policy.authorityPayload} />
									<Field label="authority hash" value={policy.authorityHash || "missing"} mono />
								</>
							) : (
								<>
									<Field label="default source" value={fallbackPreview?.defaultSource ?? "—"} mono />
									<Field label="selected source" value={fallbackPreview?.selectedSource ?? "—"} mono />
									<Field label="time range" value={tradeDate} mono />
								</>
							))}

						{sheet === "promotion" && promotion && (
							<>
								<Field label="dataset" value={datasetId} mono />
								<Field label="maturity" value={promotion.currentMaturity ?? "unknown"} />
								<Field label="time range" value={tradeDate} mono />
								<label className="text-xs text-(--color-foreground-secondary)">
									<span className="mb-1 block">撤销原因</span>
									<select
										aria-label="撤销原因"
										className={INPUT_CLASS}
										value={revocationReason}
										onChange={(event) => setRevocationReason(event.currentTarget.value as typeof revocationReason)}
									>
										<option value="failed_revalidation">failed_revalidation</option>
										<option value="policy_regression">policy_regression</option>
										<option value="evidence_invalidated">evidence_invalidated</option>
										<option value="manual_override">manual_override</option>
									</select>
								</label>
							</>
						)}

						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">执行者</span>
							<input
								aria-label="治理执行者"
								className={INPUT_CLASS}
								value={actor}
								onChange={(event) => setActor(event.currentTarget.value)}
							/>
						</label>
						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">
								确认短语（输入「
								{sheet === "remediation-request"
									? `remediation:request:${remediationDetail?.item.itemId ?? ""}`
									: sheet === "remediation-decision"
										? remediationPhrase
										: sheet === "fallback"
											? policy
												? fallbackPhrase
												: draftPhrase
											: promotionPhrase}
								」）
							</span>
							<input
								aria-label="治理确认短语"
								className={INPUT_CLASS}
								value={confirmation}
								onChange={(event) => setConfirmation(event.currentTarget.value)}
							/>
						</label>
						{error && (
							<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
								{error}
							</p>
						)}
					</div>

					<SheetFooter className="mt-auto flex-wrap">
						<Button type="button" variant="outline" disabled={isPending} onClick={() => setSheet(null)}>
							取消
						</Button>
						{sheet === "remediation-request" && intent && remediationDetail && (
							<Button
								type="button"
								disabled={
									isPending ||
									actor.trim().length === 0 ||
									confirmation !== `remediation:request:${remediationDetail.item.itemId}`
								}
								onClick={() =>
									requestApproval.mutate(
										{
											action: intent.action,
											intentType: intent.intentType,
											itemId: remediationDetail.item.itemId,
											method: intent.method,
											path: intent.path,
											requestPayload: intent.requestTemplate,
											requestedBy: actor.trim(),
										},
										{ onSuccess: (result) => closeWithResult(`approval requested · ${result.approvalId}`) },
									)
								}
							>
								请求审批
							</Button>
						)}
						{sheet === "remediation-decision" && approval?.status === "requested" && (
							<>
								<Button
									type="button"
									variant="outline"
									disabled={isPending || !exactApprovalLoaded || approvalExpired || actor.trim().length === 0}
									onClick={() =>
										decideApproval.mutate(
											{
												approvalId: approval.approvalId,
												authorityHash: approval.authorityHash,
												decidedBy: actor.trim(),
												decision: "rejected",
											},
											{ onSuccess: () => closeWithResult("approval rejected") },
										)
									}
								>
									拒绝
								</Button>
								<Button
									type="button"
									disabled={
										isPending ||
										!exactApprovalLoaded ||
										approvalExpired ||
										actor.trim().length === 0 ||
										confirmation !== remediationPhrase
									}
									onClick={() =>
										decideApproval.mutate(
											{
												approvalId: approval.approvalId,
												authorityHash: approval.authorityHash,
												decidedBy: actor.trim(),
												decision: "approved",
											},
											{ onSuccess: () => closeWithResult("approval approved") },
										)
									}
								>
									批准精确动作
								</Button>
							</>
						)}
						{sheet === "remediation-decision" && approval?.status === "approved" && (
							<Button
								type="button"
								variant="destructive"
								disabled={
									isPending ||
									!exactApprovalLoaded ||
									approvalExpired ||
									actor.trim().length === 0 ||
									confirmation !== remediationPhrase
								}
								onClick={() =>
									executeApproval.mutate(
										{
											approvalId: approval.approvalId,
											authorityHash: approval.authorityHash,
											executedBy: actor.trim(),
										},
										{
											onSuccess: (result) => closeWithResult(`remediation ${result.execution.status}`),
										},
									)
								}
							>
								执行已批准动作
							</Button>
						)}
						{sheet === "fallback" && !policy && fallbackPreview && (
							<Button
								type="button"
								disabled={isPending || actor.trim().length === 0 || confirmation !== draftPhrase}
								onClick={() =>
									draftFallback.mutate(
										{ preview: fallbackPreview, createdBy: actor.trim() },
										{ onSuccess: (result) => closeWithResult(`fallback draft · ${result.policy_id}`) },
									)
								}
							>
								创建 fallback draft
							</Button>
						)}
						{sheet === "fallback" && policy && policy.status !== "retired" && (
							<Button
								type="button"
								variant={fallbackAction === "retirement" ? "destructive" : "default"}
								disabled={
									isPending ||
									policy.authorityHash.length !== 64 ||
									actor.trim().length === 0 ||
									confirmation !== fallbackPhrase
								}
								onClick={() => {
									if (
										fallbackAction !== "approval" &&
										fallbackAction !== "activation" &&
										fallbackAction !== "retirement"
									)
										return;
									transitionFallback.mutate(
										{
											action: fallbackAction,
											actor: actor.trim(),
											authorityHash: policy.authorityHash,
											datasetId,
											policyId: policy.policyId,
										},
										{ onSuccess: (result) => closeWithResult(`fallback ${result.status}`) },
									);
								}}
							>
								确认 fallback {String(fallbackAction)}
							</Button>
						)}
						{sheet === "promotion" && promotion?.active && (
							<Button
								type="button"
								variant="destructive"
								disabled={isPending || actor.trim().length === 0 || confirmation !== promotionPhrase}
								onClick={() =>
									revokePromotion.mutate(
										{ datasetId, reason: revocationReason, revokedBy: actor.trim() },
										{ onSuccess: () => closeWithResult("promotion revoked") },
									)
								}
							>
								确认撤销晋级
							</Button>
						)}
					</SheetFooter>
				</SheetContent>
			</Sheet>
		</section>
	);
}

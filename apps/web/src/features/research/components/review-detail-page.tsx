/**
 * Review-detail 页面（`/research/reviews/$experimentId`）。
 *
 * 数据：review-packet（gates/evidence/lineage/rationale）+ 版本 state 投影 +
 * spec diff（vs parent）。版本身份由路由注入（experimentId + strategyId/version）。
 * 11 hard-gate 真实状态来自 packet，绝不伪造；packet/versions/diff 失败均显示 typed retry，
 * 不回退 prototype empty。决策动作面板（approve/reject/publish）由 `ReviewDecisionPanel` 提供。
 */
import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import { ReviewDecisionPanel } from "@/features/strategy";
import { StrategyGovernanceAudit } from "@/features/strategy/components/strategy-governance-audit";
import { useStrategyVersions } from "@/features/strategy/hooks/use-strategy-versions";
import { useVersionDiff } from "@/features/strategy/hooks/use-version-diff";
import { ApiError } from "@/lib/api-client";
import { useReviewPacket } from "../hooks/use-review-packet";
import {
	CandidateRationale,
	EvidenceHashes,
	HardGateList,
	LineagePanel,
	R1ImpactEvidence,
	ReviewDecisionBanner,
	SelectionExposureEvidence,
	SpecDiffView,
} from "./review-packet-sections";

interface ReviewDetailPageProps {
	readonly experimentId: string;
	readonly strategyId: string;
	readonly version: number;
}

function typedError(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "REVIEW_RESOURCE_ERROR"}: ${error.message}`
		: error.message;
}

export function ReviewDetailPage({ experimentId, strategyId, version }: ReviewDetailPageProps): ReactElement {
	const packetQuery = useReviewPacket(experimentId);
	const versionsQuery = useStrategyVersions(strategyId);
	const diffQuery = useVersionDiff(strategyId, version, packetQuery.isSuccess);

	const versionInfo = versionsQuery.data?.find((entry) => entry.version === version);
	const state = versionInfo?.state ?? "unknown";
	const reviewOutcome = versionInfo?.reviewOutcome ?? "unknown";

	if (packetQuery.isLoading) {
		return <div className="p-6 text-sm text-(--color-foreground-tertiary)">加载审查包…</div>;
	}
	if (packetQuery.isError || packetQuery.data === undefined) {
		const error = packetQuery.error;
		const message =
			error instanceof ApiError
				? `${error.status} ${error.errorCode ?? "REVIEW_PACKET_ERROR"}: ${error.message}`
				: (error?.message ?? "Review packet unavailable");
		return (
			<div className="flex flex-col gap-2 p-(--density-panel-padding) text-sm text-(--color-led-danger)">
				<p role="alert">{message}</p>
				<button type="button" className="self-start underline" onClick={() => void packetQuery.refetch()}>
					重试审查包
				</button>
			</div>
		);
	}

	const packet = packetQuery.data;

	return (
		<div data-contract-slot="review-evidence" className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
			<div data-contract-slot="review-decision-banner">
				<ReviewDecisionBanner
					strategyId={strategyId}
					version={version}
					experimentId={experimentId}
					state={state}
					reviewOutcome={reviewOutcome}
					hardReviewBlocked={packet.hardReviewBlocked}
				/>
			</div>
			{versionsQuery.error && (
				<p role="alert" className="text-xs text-(--color-led-danger)">
					{typedError(versionsQuery.error)}
				</p>
			)}
			<HardGateList packet={packet} />
			<EvidenceHashes packet={packet} />
			{diffQuery.error ? (
				<ContextSection title="Spec Diff">
					<div className="flex flex-col gap-1 p-(--density-panel-padding) text-xs text-(--color-led-danger)">
						<p role="alert">{typedError(diffQuery.error)}</p>
						<button type="button" className="self-start underline" onClick={() => void diffQuery.refetch()}>
							重试 Spec Diff
						</button>
					</div>
				</ContextSection>
			) : (
				<SpecDiffView changes={diffQuery.data?.changes ?? []} />
			)}
			<CandidateRationale rationale={packet.candidateRationale} />
			<SelectionExposureEvidence packet={packet} />
			<LineagePanel packet={packet} />
			<R1ImpactEvidence packet={packet} />
			<div data-contract-slot="review-actions">
				<ReviewDecisionPanel
					strategyId={strategyId}
					version={version}
					reviewOutcome={reviewOutcome}
					hardReviewBlocked={packet.hardReviewBlocked}
					bundleHash={packet.bundleHash}
					experimentId={experimentId}
				/>
			</div>
			<StrategyGovernanceAudit strategyId={strategyId} currentPacketBundleHash={packet.bundleHash} />
		</div>
	);
}

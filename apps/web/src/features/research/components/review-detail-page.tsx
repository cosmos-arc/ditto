/**
 * Review-detail 页面（`/research/reviews/$experimentId`）。
 *
 * 数据：review-packet（gates/evidence/lineage/rationale）+ 版本 state 投影 +
 * spec diff（vs parent）。版本身份由路由注入（experimentId + strategyId/version）。
 * 11 hard-gate 真实状态来自 packet，绝不伪造；packet 缺失（experimentId=null 或 404）
 * 降级为结构化空态。决策动作面板（approve/reject/publish）由 `ReviewDecisionPanel` 提供。
 */
import type { ReactElement } from "react";
import { PrototypeOnlyEmpty } from "@/components/domain/prototype-only-empty";
import { ReviewDecisionPanel } from "@/features/strategy";
import { useStrategyVersions } from "@/features/strategy/hooks/use-strategy-versions";
import { useVersionDiff } from "@/features/strategy/hooks/use-version-diff";
import { useReviewPacket } from "../hooks/use-review-packet";
import {
	CandidateRationale,
	EvidenceHashes,
	HardGateList,
	LineagePanel,
	ReviewDecisionBanner,
	SpecDiffView,
} from "./review-packet-sections";

interface ReviewDetailPageProps {
	readonly experimentId: string;
	readonly strategyId: string;
	readonly version: number;
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
		return <PrototypeOnlyEmpty domain="review-packet" />;
	}

	const packet = packetQuery.data;

	return (
		<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
			<ReviewDecisionBanner
				strategyId={strategyId}
				version={version}
				experimentId={experimentId}
				state={state}
				reviewOutcome={reviewOutcome}
				hardReviewBlocked={packet.hardReviewBlocked}
			/>
			<HardGateList packet={packet} />
			<EvidenceHashes packet={packet} />
			{diffQuery.data && <SpecDiffView changes={diffQuery.data.changes} />}
			<LineagePanel packet={packet} />
			<CandidateRationale rationale={packet.candidateRationale} />
			<ReviewDecisionPanel
				strategyId={strategyId}
				version={version}
				reviewOutcome={reviewOutcome}
				hardReviewBlocked={packet.hardReviewBlocked}
				bundleHash={packet.bundleHash}
			/>
		</div>
	);
}

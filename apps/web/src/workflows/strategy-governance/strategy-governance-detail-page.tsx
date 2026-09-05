import type { ReactElement } from "react";
import { ApiError } from "@/api";
import { useReviewPacket } from "@/features/research";
import {
	GovernanceActions,
	StrategyDetailPage,
	type StrategyGovernanceActionsSlotProps,
	type StrategyReviewEvidence,
	type StrategyReviewEvidenceIssue,
} from "@/features/strategy";

function packetErrorIssue(error: Error): StrategyReviewEvidenceIssue {
	if (error instanceof ApiError) {
		return {
			code: error.errorCode ?? "REVIEW_PACKET_ERROR",
			message: error.message,
			status: error.status,
		};
	}
	return { code: "REVIEW_PACKET_ERROR", message: error.message };
}

function unavailableEvidence(code: string, message: string): StrategyReviewEvidence {
	return {
		bundleHash: null,
		hardReviewBlocked: true,
		issue: { code, message },
	};
}

/** Compose Research review evidence with Strategy-owned governance controls. */
export function StrategyReviewGovernanceActions(props: StrategyGovernanceActionsSlotProps): ReactElement {
	const experimentId = props.version.experimentId;
	const packet = useReviewPacket(experimentId);
	let reviewEvidence: StrategyReviewEvidence;

	if (!experimentId) {
		reviewEvidence = unavailableEvidence("REVIEW_PACKET_MISSING", "当前策略版本没有绑定 review packet");
	} else if (packet.isError) {
		reviewEvidence = {
			bundleHash: null,
			hardReviewBlocked: true,
			issue: packetErrorIssue(packet.error),
		};
	} else if (packet.isPending) {
		reviewEvidence = { bundleHash: null, hardReviewBlocked: true, issue: null };
	} else if (!packet.data) {
		reviewEvidence = unavailableEvidence("REVIEW_PACKET_MISSING", "review packet 响应没有数据");
	} else if (!/^[0-9a-f]{64}$/u.test(packet.data.bundleHash)) {
		reviewEvidence = unavailableEvidence("REVIEW_PACKET_INVALID", "review packet bundle hash 无效");
	} else if (packet.data.hardReviewBlocked) {
		reviewEvidence = {
			bundleHash: packet.data.bundleHash,
			hardReviewBlocked: true,
			issue: {
				code: "REVIEW_HARD_GATE_BLOCKED",
				message: "review packet hard gates 未通过",
			},
		};
	} else {
		reviewEvidence = {
			bundleHash: packet.data.bundleHash,
			hardReviewBlocked: false,
			issue: null,
		};
	}

	return <GovernanceActions {...props} reviewEvidence={reviewEvidence} />;
}

function renderGovernanceActions(props: StrategyGovernanceActionsSlotProps): ReactElement {
	return <StrategyReviewGovernanceActions {...props} />;
}

/** Route-ready Strategy page whose cross-feature dependencies stay in the workflow layer. */
export function StrategyGovernanceDetailPage(): ReactElement {
	return <StrategyDetailPage renderGovernanceActions={renderGovernanceActions} />;
}

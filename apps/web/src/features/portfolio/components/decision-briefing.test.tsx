import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createDailyDecisionV3ViewModel } from "./daily-decision-v3.fixture";
import { buildDecisionOpinionIdentity, DecisionBriefing } from "./decision-briefing";

const mocks = vi.hoisted(() => ({ useDecisionOpinion: vi.fn() }));

vi.mock("@/features/agent", async () => {
	const actual = await vi.importActual<typeof import("@/features/agent")>("@/features/agent");
	return { ...actual, useDecisionOpinion: mocks.useDecisionOpinion };
});

describe("DecisionBriefing", () => {
	it("builds the exact V3/PIT identity and renders a shadow-only opinion", () => {
		const decision = createDailyDecisionV3ViewModel();
		const identity = buildDecisionOpinionIdentity(decision);
		expect(identity).toEqual({
			accountId: "paper-r4",
			decisionTime: "2026-08-18T07:00:00Z",
			knowledgeCutoff: "2026-08-18T06:55:00Z",
			publicationCutoff: "2026-08-18T06:50:00Z",
			sleeveId: "sleeve-r4",
			sourceSnapshotId: "snapshot-bars-r4",
			strategyId: "strategy-r4",
			strategyVersion: "7",
			tradeDate: "2026-08-19",
			v3ArtifactId: "daily-decision-v3:strategy-r4:2026-08-19:paper-r4:sleeve-r4",
		});
		mocks.useDecisionOpinion.mockReturnValue({
			data: {
				evidenceRefs: ["evidence-v3"],
				disagreements: ["factor concentration exceeds preference"],
				generatedAt: "2026-08-18T07:02:00Z",
				identity,
				modelProfile: "quality",
				provenanceMatch: true,
				shadowOutcomeIdentity: "shadow-outcome-1",
				status: "completed",
				summary: "尾部风险可控，但需关注因子集中。",
				uncertainties: ["opening gap"],
				unavailableReason: null,
			},
			isLoading: false,
			isError: false,
			error: null,
			refetch: vi.fn(),
		});

		render(<DecisionBriefing decision={decision} />);

		expect(screen.getByText("SHADOW ONLY")).toBeInTheDocument();
		expect(screen.getByText("尾部风险可控，但需关注因子集中。")).toBeInTheDocument();
		expect(screen.getByText(/factor concentration exceeds preference/)).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /采纳|交易/ })).not.toBeInTheDocument();
	});

	it("normalizes offset PIT timestamps to the UTC boundary required by the opinion API", () => {
		const decision = createDailyDecisionV3ViewModel({
			provenance: {
				...createDailyDecisionV3ViewModel().provenance,
				decisionTime: "2026-08-18T15:00:00+08:00",
				knowledgeCutoff: "2026-08-18T14:55:00+08:00",
				publicationCutoff: "2026-08-18T14:50:00+08:00",
			},
		});

		expect(buildDecisionOpinionIdentity(decision)).toMatchObject({
			decisionTime: "2026-08-18T07:00:00.000Z",
			knowledgeCutoff: "2026-08-18T06:55:00.000Z",
			publicationCutoff: "2026-08-18T06:50:00.000Z",
		});
	});

	it("fails closed when exact identity has missing or ambiguous provenance", () => {
		const decision = createDailyDecisionV3ViewModel({
			identity: {
				...createDailyDecisionV3ViewModel().identity,
				sleeveId: null,
			},
			provenance: {
				...createDailyDecisionV3ViewModel().provenance,
				sourceSnapshotIds: ["snapshot-a", "snapshot-b"],
			},
		});
		mocks.useDecisionOpinion.mockReturnValue({
			data: undefined,
			isLoading: false,
			isError: false,
			error: null,
			refetch: vi.fn(),
		});

		render(<DecisionBriefing decision={decision} />);

		expect(mocks.useDecisionOpinion).toHaveBeenCalledWith(null);
		expect(screen.getByText(/exact identity 不完整/)).toBeInTheDocument();
		expect(screen.getByText(/sleeve_id/)).toBeInTheDocument();
		expect(screen.getByText(/source_snapshot_id/)).toBeInTheDocument();
	});
});

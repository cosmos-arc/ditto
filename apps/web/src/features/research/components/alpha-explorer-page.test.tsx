import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgentCampaignView } from "@/features/agent";
import { AlphaExplorerPageView } from "./alpha-explorer-page";

const campaign: AgentCampaignView = {
	campaignId: "campaign-7",
	status: "draft",
	canonicalManifest: { campaign_id: "campaign-7" },
	manifestHash: "c".repeat(64),
	authorizationHash: null,
	authorizedBy: null,
	authorizationExpiresAt: null,
	searchAxis: "parameters",
	sourceSnapshotId: "snapshot-11",
	allowedTools: ["factor_evidence"],
	budget: {
		candidateLimit: 12,
		foldRunLimit: 24,
		generationLimit: 4,
		concurrentSandboxLimit: 2,
		wallTimeLimitSeconds: 2700,
		temporaryStorageLimitBytes: 1_000_000,
		modelSpendLimitUsdMicros: 5_000_000,
		sandboxResourceLimits: {
			cpuCount: 2,
			memoryBytes: 1_000_000_000,
			processLimit: 16,
			temporaryStorageBytes: 1_000_000,
			wallTimeSeconds: 300,
			outputBytes: 100_000,
		},
	},
	bestPrimaryMetricValue: 0.036,
	noImprovementGenerations: 1,
	statisticalTrialCount: 7,
	operationalAttemptCount: 9,
	revision: 2,
	objective: "发现低相关反转因子",
	outputSummary: "低相关性候选需要样本外复核。",
	toolRecords: [
		{
			callId: "call-1",
			toolName: "factor_evidence",
			argumentsHash: "args-hash",
			resultHash: "result-hash",
			evidenceRefs: ["evidence-7"],
			artifactRefs: ["artifact-2"],
		},
	],
	evidenceRefs: ["evidence-7"],
	artifactRefs: ["artifact-2"],
	guardrail: { status: "blocked", reasonCode: "sensitive_field_forbidden" },
	usage: {
		statisticalTrialCount: 7,
		operationalAttemptCount: 9,
		noImprovementGenerations: 1,
		modelSpendUsdMicros: 1_200_000,
		exhaustedReason: null,
	},
	eventCursor: 17,
	projectionState: "partial",
	projectionReason: "candidate_score_vector_unavailable",
	projectionVersion: 3,
	projectionUpdatedAt: "2026-08-25T01:03:00Z",
};

describe("AlphaExplorerPageView", () => {
	it("renders the Studio contract slots and preserves exact snapshot evidence without inventing candidate fields", () => {
		const { container } = render(
			<AlphaExplorerPageView
				campaigns={[campaign]}
				selectedCampaign={campaign}
				state="ready"
				onSelectCampaign={vi.fn()}
				onOpenApproval={vi.fn()}
			/>,
		);

		for (const slot of ["source", "main", "inspector", "adoption", "graph"]) {
			expect(container.querySelector(`[data-slot='${slot}']`), slot).not.toBeNull();
		}
		expect(screen.getAllByText("snapshot-11").length).toBeGreaterThan(0);
		expect(screen.getByText("候选公式未由 Campaign projection 提供")).toBeInTheDocument();
		expect(screen.getByText(/knowledge cutoff 未提供/u)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "审查并批准 Campaign" })).toBeInTheDocument();
	});

	it("opens concrete evidence, artifact, guardrail, and Copilot context overlays", () => {
		render(
			<AlphaExplorerPageView
				campaigns={[campaign]}
				selectedCampaign={campaign}
				state="ready"
				onSelectCampaign={vi.fn()}
				onOpenApproval={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: "深入 campaign-7" }));
		expect(screen.getByRole("dialog", { name: "候选深入 · campaign-7" })).toHaveTextContent("evidence-7");
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getAllByRole("button", { name: "预览 artifact-2" })[0]);
		expect(screen.getByRole("dialog", { name: "产物预览 · artifact-2" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getByRole("button", { name: "查看阻断原因" }));
		expect(screen.getByRole("dialog", { name: "Guardrail 阻断详情" })).toHaveTextContent("sensitive_field_forbidden");
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getByRole("button", { name: "打开 Copilot 上下文" }));
		expect(screen.getByRole("dialog", { name: "Copilot · Alpha 上下文" })).toHaveTextContent("snapshot-11");
	});
});

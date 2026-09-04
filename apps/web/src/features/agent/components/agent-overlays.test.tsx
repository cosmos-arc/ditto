import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
	AgentApprovalView,
	AgentCampaignValidationInput,
	AgentCampaignView,
	AgentCapabilityView,
	AgentRunView,
} from "../types";
import {
	AgentApprovalExactActionDialog,
	AgentArtifactPreviewDrawer,
	AgentCampaignApprovalDialog,
	AgentCampaignCancelDialog,
	AgentCampaignDraftSheet,
	AgentEvidenceDetailDrawer,
	AgentGuardrailDetailDrawer,
	AgentRunCancelDialog,
	AgentRunCreateSheet,
} from "./agent-overlays";

const mocks = vi.hoisted(() => ({
	approveCampaign: vi.fn(),
	cancelCampaign: vi.fn(),
	cancelRun: vi.fn(),
	createCampaign: vi.fn(),
	createRun: vi.fn(),
	decideApproval: vi.fn(),
	resetValidation: vi.fn(),
	validate: vi.fn(),
}));

vi.mock("../hooks", () => ({
	useApproveAgentCampaign: () => ({ isPending: false, error: null, mutate: mocks.approveCampaign }),
	useCancelAgentCampaign: () => ({ isPending: false, error: null, mutate: mocks.cancelCampaign }),
	useCancelAgentRun: () => ({ isPending: false, error: null, mutate: mocks.cancelRun }),
	useCreateAgentCampaign: () => ({ isPending: false, error: null, mutate: mocks.createCampaign }),
	useCreateAgentRun: () => ({ isPending: false, error: null, mutate: mocks.createRun }),
	useDecideAgentApproval: () => ({ isPending: false, error: null, mutate: mocks.decideApproval }),
	useValidateAgentCampaign: () => ({
		isPending: false,
		error: null,
		mutateAsync: mocks.validate,
		reset: mocks.resetValidation,
	}),
}));

const capability: AgentCapabilityView = {
	enabled: true,
	runtimeState: "available",
	provider: "configured",
	availableProfiles: ["balanced"],
	defaultProfile: "balanced",
	degradationReason: null,
	checkedAt: "2026-08-25T08:00:00Z",
};

const draftCampaign: AgentCampaignView = {
	campaignId: "campaign-7",
	status: "draft",
	canonicalManifest: { campaign_id: "campaign-7" },
	manifestHash: "c".repeat(64),
	authorizationHash: null,
	authorizedBy: null,
	authorizationExpiresAt: null,
	searchAxis: "factor_code",
	sourceSnapshotId: "snapshot-11",
	allowedTools: ["campaign_propose_candidate"],
	budget: {
		candidateLimit: 12,
		foldRunLimit: 48,
		generationLimit: 4,
		concurrentSandboxLimit: 2,
		wallTimeLimitSeconds: 3600,
		temporaryStorageLimitBytes: 1_073_741_824,
		modelSpendLimitUsdMicros: 5_000_000,
		sandboxResourceLimits: {
			cpuCount: 2,
			memoryBytes: 2_147_483_648,
			processLimit: 32,
			temporaryStorageBytes: 536_870_912,
			wallTimeSeconds: 900,
			outputBytes: 10_485_760,
		},
	},
	bestPrimaryMetricValue: null,
	noImprovementGenerations: 0,
	statisticalTrialCount: 0,
	operationalAttemptCount: 0,
	revision: 1,
	objective: "Verify campaign approval.",
	outputSummary: null,
	toolRecords: [],
	evidenceRefs: [],
	artifactRefs: [],
	guardrail: null,
	usage: null,
	eventCursor: 1,
	projectionState: "partial",
	projectionReason: "campaign_result_projection_unavailable",
	projectionVersion: 1,
	projectionUpdatedAt: "2026-08-25T01:00:00Z",
};

const run: AgentRunView = {
	runId: "run-104",
	sessionId: "session-9",
	status: "running",
	objectiveHash: "objective-hash",
	authorityHash: "a".repeat(64),
	maxModelTokens: 12_000,
	maxModelSpendUsd: "3.00",
	modelProfile: "balanced",
	manifestHash: "manifest-hash",
	createdAt: "2026-08-25T01:00:00Z",
	startedAt: "2026-08-25T01:01:00Z",
	finishedAt: null,
	revision: 3,
	objective: "Inspect exact evidence.",
	context: { contextType: "strategy", contextId: "strategy-12@4" },
	outputSummary: null,
	toolRecords: [],
	evidenceRefs: [],
	artifactRefs: [],
	guardrail: null,
	usage: null,
	failureCode: null,
	executionPlan: null,
	eventCursor: 17,
	projectionState: "complete",
	projectionReason: null,
	projectionVersion: 4,
	projectionUpdatedAt: "2026-08-25T01:03:00Z",
};

const approval: AgentApprovalView = {
	approvalId: "approval-4",
	runId: run.runId,
	actionType: "strategy_patch",
	targetIdentity: "strategy-12@4",
	actionPayload: { patch: [{ path: "/name", value: "Momentum v5" }] },
	actionHash: "b".repeat(64),
	status: "pending",
	requestedAt: "2026-08-25T01:00:00Z",
	expiresAt: "2099-08-25T01:30:00Z",
	operatorId: null,
	reason: null,
	decidedAt: null,
};

function fillHypothesisStep(): void {
	const values: ReadonlyArray<readonly [string, string]> = [
		["Campaign identity", "campaign-1"],
		["Objective", "Test one falsifiable signal."],
		["Primary metric", "sharpe_ratio"],
		["Hypothesis statement", "Signal persists after costs."],
		["Mechanism", "Liquidity provision."],
		["Expected signal", "Sharpe improves."],
		["Failure condition", "Sharpe does not improve."],
		["Universe hash", "a".repeat(64)],
	];
	fillFields(values);
}

function fillFields(values: ReadonlyArray<readonly [string, string]>): void {
	for (const [label, value] of values) {
		fireEvent.change(screen.getByRole("textbox", { name: label }), { target: { value } });
	}
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.validate.mockImplementation(async (input: AgentCampaignValidationInput) => {
		const canonicalManifest = input.step === "manifest" ? input.manifest : null;
		return {
			step: input.step,
			valid: true,
			canonicalManifest,
			manifestHash: canonicalManifest ? "d".repeat(64) : null,
		};
	});
});

describe("Agent governed overlays", () => {
	it("prefills a governed run from stable URL context and explicit objective", () => {
		render(
			<AgentRunCreateSheet
				open
				onOpenChange={vi.fn()}
				onCreated={vi.fn()}
				capability={capability}
				contextType="experiment"
				contextId="experiment-22@revision-4"
				initialObjective="Review the exact experiment evidence."
			/>,
		);

		expect(screen.getByRole("textbox", { name: "Run objective" })).toHaveValue("Review the exact experiment evidence.");
		expect(screen.getByRole("textbox", { name: "Context type" })).toHaveValue("experiment");
		expect(screen.getByRole("textbox", { name: "Context identity" })).toHaveValue("experiment-22@revision-4");
	});

	it("submits the exact PIT scope and executes the new governed run", async () => {
		const user = userEvent.setup();
		const onCreated = vi.fn();
		const onOpenChange = vi.fn();
		render(
			<AgentRunCreateSheet
				open
				onOpenChange={onOpenChange}
				onCreated={onCreated}
				capability={{ ...capability, availableProfiles: ["balanced", "quality"] }}
				contextType=" strategy "
				contextId=" strategy-12@4 "
				initialObjective=" Inspect exact evidence. "
			/>,
		);

		await user.selectOptions(screen.getByRole("combobox", { name: "Retention class" }), "audit");
		await user.selectOptions(screen.getByRole("combobox", { name: "Model profile" }), "quality");
		await user.click(screen.getByText("覆盖硬预算"));
		fireEvent.change(screen.getByRole("spinbutton", { name: "Max model tokens" }), { target: { value: "16000" } });
		fireEvent.change(screen.getByRole("textbox", { name: "Max model spend USD" }), { target: { value: "4.25" } });
		fireEvent.change(screen.getByRole("textbox", { name: "Decision time" }), {
			target: { value: "2026-08-25T08:00:00Z" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Knowledge cutoff" }), {
			target: { value: "2026-08-25T07:55:00Z" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Publication cutoff" }), {
			target: { value: "2026-08-25T07:50:00Z" },
		});
		await user.type(screen.getByRole("textbox", { name: "Source snapshot" }), "snapshot-certified-2026-08-25");
		await user.type(screen.getByRole("textbox", { name: "Allowed universe" }), "510300.SH, 510500.SH");
		fireEvent.change(screen.getByRole("spinbutton", { name: "Max output tokens" }), { target: { value: "2048" } });
		await user.click(screen.getByRole("button", { name: "取消" }));
		await user.click(screen.getByRole("button", { name: "创建并执行" }));

		expect(mocks.createRun).toHaveBeenCalledWith(
			expect.objectContaining({
				context: { contextType: "strategy", contextId: "strategy-12@4" },
				maxModelSpendUsd: "4.25",
				maxModelTokens: 16_000,
				modelProfile: "quality",
				objective: "Inspect exact evidence.",
				executeImmediately: true,
				executionScope: {
					allowedUniverse: ["510300.SH", "510500.SH"],
					decisionTime: "2026-08-25T08:00:00Z",
					knowledgeCutoff: "2026-08-25T07:55:00Z",
					maxOutputTokens: 2048,
					publicationCutoff: "2026-08-25T07:50:00Z",
					sourceSnapshotId: "snapshot-certified-2026-08-25",
				},
				retentionClass: "audit",
				sessionId: "",
				idempotencyKey: expect.stringMatching(/^agent-run:/),
			}),
			expect.any(Object),
		);
		const [, options] = mocks.createRun.mock.calls[0] as [unknown, { onSuccess: (value: AgentRunView) => void }];
		options.onSuccess(run);
		expect(onCreated).toHaveBeenCalledWith(run);
		expect(onOpenChange).toHaveBeenLastCalledWith(false);
	});

	it("allows queueing but blocks immediate execution while the model lane is degraded", () => {
		render(
			<AgentRunCreateSheet
				open
				onOpenChange={vi.fn()}
				onCreated={vi.fn()}
				capability={{
					...capability,
					runtimeState: "degraded",
					provider: null,
					degradationReason: "agent_model_execution_unconfigured",
				}}
				initialObjective="Queue an exact evidence review."
			/>,
		);

		fireEvent.change(screen.getByRole("textbox", { name: "Decision time" }), {
			target: { value: "2026-08-25T08:00:00Z" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Knowledge cutoff" }), {
			target: { value: "2026-08-25T07:55:00Z" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Publication cutoff" }), {
			target: { value: "2026-08-25T07:50:00Z" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Source snapshot" }), {
			target: { value: "snapshot-certified-2026-08-25" },
		});
		fireEvent.change(screen.getByRole("textbox", { name: "Allowed universe" }), {
			target: { value: "510300.SH" },
		});

		expect(screen.getByRole("alert")).toHaveTextContent("模型执行不可用");
		expect(screen.getByRole("button", { name: "仅创建" })).toBeEnabled();
		expect(screen.getByRole("button", { name: "创建并执行" })).toBeDisabled();
		fireEvent.click(screen.getByRole("button", { name: "仅创建" }));
		expect(mocks.createRun).toHaveBeenCalledWith(
			expect.objectContaining({ executeImmediately: false }),
			expect.any(Object),
		);
	});

	it("requires the exact run revision phrase before cancelling", async () => {
		const user = userEvent.setup();
		const onSuccess = vi.fn();
		const onOpenChange = vi.fn();
		render(<AgentRunCancelDialog run={run} open onOpenChange={onOpenChange} onSuccess={onSuccess} />);

		const submit = screen.getByRole("button", { name: "确认取消" });
		expect(submit).toBeDisabled();
		await user.type(screen.getByRole("textbox", { name: "Run cancel confirmation" }), "run:cancel:run-104:revision:3");
		expect(submit).toBeEnabled();
		await user.click(submit);
		expect(mocks.cancelRun).toHaveBeenCalledWith(run, expect.any(Object));
		const [, options] = mocks.cancelRun.mock.calls[0] as [unknown, { onSuccess: (value: AgentRunView) => void }];
		options.onSuccess({ ...run, status: "cancelled" });
		expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }));
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});

	it("binds approval and rejection to the loaded action hash", async () => {
		const user = userEvent.setup();
		const onOpenChange = vi.fn();
		render(<AgentApprovalExactActionDialog approval={approval} open onOpenChange={onOpenChange} />);

		await user.clear(screen.getByRole("textbox", { name: "Approval operator" }));
		await user.type(screen.getByRole("textbox", { name: "Approval operator" }), "operator-7");
		await user.type(screen.getByRole("textbox", { name: "Approval reason" }), "Reviewed exact patch.");
		await user.type(
			screen.getByRole("textbox", { name: "Exact approval confirmation" }),
			`approval:${approval.actionHash}`,
		);
		await user.click(screen.getByRole("button", { name: "批准当前 hash" }));
		await user.click(screen.getByRole("button", { name: "拒绝" }));

		expect(mocks.decideApproval).toHaveBeenNthCalledWith(
			1,
			{
				actionHash: approval.actionHash,
				approvalId: approval.approvalId,
				decision: "approve",
				operatorId: "operator-7",
				reason: "Reviewed exact patch.",
			},
			expect.any(Object),
		);
		expect(mocks.decideApproval).toHaveBeenNthCalledWith(
			2,
			expect.objectContaining({ decision: "reject" }),
			expect.any(Object),
		);
		const [, options] = mocks.decideApproval.mock.calls[0] as [unknown, { onSuccess: () => void }];
		options.onSuccess();
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});

	it("fails closed when an approval projection is expired or incomplete", () => {
		const { rerender } = render(
			<AgentApprovalExactActionDialog
				approval={{ ...approval, expiresAt: "invalid-date" }}
				open
				onOpenChange={vi.fn()}
			/>,
		);
		expect(screen.getByRole("alert")).toHaveTextContent("approval 已过期");
		expect(screen.getByRole("button", { name: "批准当前 hash" })).toBeDisabled();

		rerender(
			<AgentApprovalExactActionDialog
				approval={{ ...approval, actionPayload: {}, actionHash: "", expiresAt: "" }}
				open
				onOpenChange={vi.fn()}
			/>,
		);
		expect(screen.getAllByRole("alert").map((item) => item.textContent)).toEqual(
			expect.arrayContaining([expect.stringContaining("fail closed")]),
		);
	});

	it("opens all governed reference drawers without inventing missing content", async () => {
		const user = userEvent.setup();
		const onOpenChange = vi.fn();
		const evidenceView = render(
			<AgentEvidenceDetailDrawer evidenceRef="evidence-7" open onOpenChange={onOpenChange} />,
		);
		expect(screen.getByText("evidence-7")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "Close" }));
		expect(onOpenChange).toHaveBeenCalledWith(false);
		evidenceView.unmount();

		const artifactView = render(<AgentArtifactPreviewDrawer artifactRef="artifact-2" open onOpenChange={vi.fn()} />);
		expect(screen.getByText("内容未在展示契约中提供。")).toBeInTheDocument();
		artifactView.unmount();

		render(<AgentGuardrailDetailDrawer status="blocked" reasonCode={null} open onOpenChange={vi.fn()} />);
		expect(screen.getByText("not provided")).toBeInTheDocument();
	});

	it("does not advance a Campaign step until backend validation succeeds", async () => {
		render(<AgentCampaignDraftSheet open onOpenChange={vi.fn()} onCreated={vi.fn()} />);
		fillHypothesisStep();
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));

		await waitFor(() => expect(mocks.validate).toHaveBeenCalledTimes(1));
		expect(mocks.validate).toHaveBeenCalledWith(
			expect.objectContaining({ step: "hypothesis", primary_metric_id: "sharpe_ratio" }),
		);
		expect(await screen.findByText("hypothesis 后端校验通过")).toBeInTheDocument();
		expect(screen.getByText("步骤 2/4", { exact: false })).toBeInTheDocument();
	});

	it("keeps a Campaign step open and shows a fail-closed backend validation error", async () => {
		mocks.validate.mockRejectedValueOnce("invalid governed input");
		render(<AgentCampaignDraftSheet open onOpenChange={vi.fn()} onCreated={vi.fn()} />);
		fillHypothesisStep();
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("Campaign 后端校验失败");
		expect(screen.getByText("步骤 1/4", { exact: false })).toBeInTheDocument();
	});

	it("validates all four Campaign stages and creates only the canonical draft", async () => {
		const onCreated = vi.fn();
		const onOpenChange = vi.fn();
		render(<AgentCampaignDraftSheet open onOpenChange={onOpenChange} onCreated={onCreated} />);
		fillHypothesisStep();
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));
		await screen.findByText("步骤 2/4", { exact: false });

		fireEvent.change(screen.getByRole("combobox", { name: "Campaign search axis" }), {
			target: { value: "factor_code" },
		});
		fillFields([
			["Baseline candidate", "candidate-1"],
			["Data requirement hash", "b".repeat(64)],
			["Baseline code hash", "c".repeat(64)],
			["Snapshot identity", "snapshot-11"],
			["Fold protocol", "walk-forward"],
			["Fold protocol hash", "d".repeat(64)],
			["Validation objective hash", "e".repeat(64)],
			["Cost model hash", "f".repeat(64)],
		]);
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));
		await screen.findByText("步骤 3/4", { exact: false });

		fillFields([
			["Search-space hash", "1".repeat(64)],
			["Lineage root", "lineage-root-1"],
		]);
		fireEvent.click(screen.getByRole("button", { name: "上一步" }));
		expect(screen.getByText("步骤 2/4", { exact: false })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));
		await screen.findByText("步骤 3/4", { exact: false });
		fireEvent.click(screen.getByRole("button", { name: "下一步" }));
		await screen.findByText("步骤 4/4", { exact: false });
		expect(screen.getByText("输入完整；创建前仍需完整 manifest 后端校验。")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "校验完整 Manifest" }));
		await screen.findByText("Backend canonical manifest");
		fireEvent.click(screen.getByRole("button", { name: "创建 Draft" }));

		expect(mocks.validate.mock.calls.map(([input]) => input.step)).toEqual([
			"hypothesis",
			"experiment_plan",
			"experiment_plan",
			"governance",
			"manifest",
		]);
		expect(mocks.createCampaign).toHaveBeenCalledWith(
			expect.objectContaining({
				idempotencyKey: expect.stringMatching(/^agent-campaign:/),
				manifest: expect.objectContaining({
					search_axis: "factor_code",
					allowed_tools: ["factor_evidence", "experiment_runner"],
					prohibited_actions: ["trade", "deploy", "write_production"],
					baseline_candidate: expect.objectContaining({
						factor_code_hash: "c".repeat(64),
						model_code_hash: null,
					}),
				}),
			}),
			expect.any(Object),
		);
		const [, options] = mocks.createCampaign.mock.calls[0] as [
			unknown,
			{ onSuccess: (value: AgentCampaignView) => void },
		];
		options.onSuccess(draftCampaign);
		expect(onCreated).toHaveBeenCalledWith(draftCampaign);
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});

	it("prefills a visible finite Campaign authorization expiry", () => {
		render(<AgentCampaignApprovalDialog campaign={draftCampaign} open onOpenChange={vi.fn()} />);

		const expiry = screen.getByLabelText("Campaign authorization expiry");
		expect(expiry).not.toHaveValue("");
		expect(Date.parse((expiry as HTMLInputElement).value)).toBeGreaterThan(Date.now());
	});

	it("approves the exact Campaign manifest with finite authorization", async () => {
		const user = userEvent.setup();
		const onOpenChange = vi.fn();
		render(<AgentCampaignApprovalDialog campaign={draftCampaign} open onOpenChange={onOpenChange} />);
		await user.clear(screen.getByRole("textbox", { name: "Campaign approval operator" }));
		await user.type(screen.getByRole("textbox", { name: "Campaign approval operator" }), "operator-7");
		fireEvent.change(screen.getByLabelText("Campaign authorization expiry"), {
			target: { value: "2099-08-26T12:00" },
		});
		await user.type(
			screen.getByRole("textbox", { name: "Campaign approval confirmation" }),
			`campaign:approve:${draftCampaign.manifestHash}`,
		);
		await user.click(screen.getByRole("button", { name: "批准当前 manifest" }));

		expect(mocks.approveCampaign).toHaveBeenCalledWith(
			expect.objectContaining({
				campaignId: draftCampaign.campaignId,
				manifestHash: draftCampaign.manifestHash,
				operatorId: "operator-7",
				expiresAt: new Date("2099-08-26T12:00").toISOString(),
				idempotencyKey: expect.stringMatching(/^campaign-approve:/),
			}),
			expect.any(Object),
		);
		const [, options] = mocks.approveCampaign.mock.calls[0] as [unknown, { onSuccess: () => void }];
		options.onSuccess();
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});

	it("cancels only the exact authorized Campaign projection", async () => {
		const user = userEvent.setup();
		const onOpenChange = vi.fn();
		const authorized = {
			...draftCampaign,
			status: "authorized" as const,
			authorizationHash: "e".repeat(64),
		};
		render(<AgentCampaignCancelDialog campaign={authorized} open onOpenChange={onOpenChange} />);
		const submit = screen.getByRole("button", { name: "确认取消" });
		expect(submit).toBeDisabled();
		await user.type(
			screen.getByRole("textbox", { name: "Campaign cancel confirmation" }),
			`campaign:cancel:${authorized.authorizationHash}`,
		);
		await user.click(submit);

		expect(mocks.cancelCampaign).toHaveBeenCalledWith(
			{
				campaignId: authorized.campaignId,
				authorizationHash: authorized.authorizationHash,
				idempotencyKey: expect.stringMatching(/^campaign-cancel:/),
			},
			expect.any(Object),
		);
		const [, options] = mocks.cancelCampaign.mock.calls[0] as [unknown, { onSuccess: () => void }];
		options.onSuccess();
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});
});

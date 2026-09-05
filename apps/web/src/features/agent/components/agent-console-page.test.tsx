import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentApprovalView, AgentCampaignView, AgentRunView, AgentSessionView } from "../types";
import { AgentConsolePage } from "./agent-console-page";

const mocks = vi.hoisted(() => ({
	useAgentApproval: vi.fn(),
	useAgentApprovals: vi.fn(),
	useAgentCampaign: vi.fn(),
	useAgentCampaigns: vi.fn(),
	useAgentCapability: vi.fn(),
	useAgentEventNotifications: vi.fn(),
	useAgentRun: vi.fn(),
	useAgentRuns: vi.fn(),
	useAgentSessions: vi.fn(),
	executeRun: vi.fn(),
}));

vi.mock("../hooks", () => ({
	...mocks,
	useApproveAgentCampaign: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useCancelAgentCampaign: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useCancelAgentRun: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useCreateAgentCampaign: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useCreateAgentRun: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useExecuteAgentRun: () => ({ isPending: false, error: null, mutate: mocks.executeRun }),
	useDecideAgentApproval: () => ({ isPending: false, error: null, mutate: vi.fn() }),
	useValidateAgentCampaign: () => ({ isPending: false, error: null, mutateAsync: vi.fn(), reset: vi.fn() }),
}));

const run: AgentRunView = {
	runId: "run-104",
	sessionId: "session-9",
	status: "waiting_approval",
	objectiveHash: "objective-hash",
	authorityHash: "a".repeat(64),
	maxModelTokens: 12_000,
	maxModelSpendUsd: "3.00",
	modelProfile: "balanced",
	manifestHash: "manifest-hash",
	createdAt: "2026-08-18T01:00:00Z",
	startedAt: "2026-08-18T01:01:00Z",
	finishedAt: null,
	revision: 3,
	objective: "核对候选因子的证据链",
	context: { contextType: "strategy", contextId: "strategy-12@4" },
	outputSummary: null,
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
	guardrail: { status: "passed", reasonCode: null },
	usage: {
		modelAttempts: 1,
		modelTurns: 2,
		toolCalls: 1,
		retries: 0,
		totalTokens: 1400,
		modelSpendUsd: "0.18",
		exhaustedReason: null,
	},
	failureCode: null,
	executionPlan: {
		allowedTools: ["research_factor_evidence"],
		allowedUniverse: ["510300.SH"],
		authorityHash: "a".repeat(64),
		decisionTime: "2026-08-18T01:00:00Z",
		egressClass: "cloud_allowed",
		executionEligibleAt: "not_applicable",
		knowledgeCutoff: "2026-08-18T00:55:00Z",
		licenseClass: "approved-research",
		maxOutputTokens: 1024,
		publicationCutoff: "2026-08-18T00:50:00Z",
		sourceSnapshotId: "snapshot-certified-2026-08-18",
	},
	eventCursor: 17,
	projectionState: "partial",
	projectionReason: "output_summary_pending",
	projectionVersion: 4,
	projectionUpdatedAt: "2026-08-18T01:03:00Z",
};

const approval: AgentApprovalView = {
	approvalId: "approval-4",
	runId: "run-104",
	actionType: "strategy_patch",
	targetIdentity: "strategy-12@4",
	actionPayload: { patch: [{ path: "/name", value: "Momentum v5" }] },
	actionHash: "b".repeat(64),
	status: "pending",
	requestedAt: "2026-08-17T01:00:00Z",
	expiresAt: "2026-08-17T01:30:00Z",
	operatorId: null,
	reason: null,
	decidedAt: null,
};

const session: AgentSessionView = {
	sessionId: "session-9",
	createdAt: "2026-08-18T00:58:00Z",
	retentionClass: "audit",
};

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
	bestPrimaryMetricValue: null,
	noImprovementGenerations: 0,
	statisticalTrialCount: 0,
	operationalAttemptCount: 0,
	revision: 1,
	objective: "复核参数搜索空间",
	outputSummary: null,
	toolRecords: [],
	evidenceRefs: [],
	artifactRefs: [],
	guardrail: null,
	usage: null,
	eventCursor: 0,
	projectionState: "complete",
	projectionReason: null,
	projectionVersion: 1,
	projectionUpdatedAt: "2026-08-25T01:00:00Z",
};

function query<T>(data: T | undefined, options: { loading?: boolean; error?: Error } = {}) {
	return {
		data,
		error: options.error ?? null,
		isError: Boolean(options.error),
		isFetching: false,
		isLoading: options.loading ?? false,
		refetch: vi.fn(),
	};
}

function wrapper({ children }: { children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.useAgentCapability.mockReturnValue(
		query({
			enabled: false,
			runtimeState: "disabled",
			provider: null,
			availableProfiles: [],
			defaultProfile: null,
			degradationReason: "provider_not_configured",
			checkedAt: "2026-08-18T01:00:00Z",
		}),
	);
	mocks.useAgentRuns.mockReturnValue(
		query({ items: [run], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
	);
	mocks.useAgentSessions.mockReturnValue(
		query({ items: [session], pagination: { total: 21, limit: 20, offset: 20, hasMore: false } }),
	);
	mocks.useAgentRun.mockImplementation((id: string) => query(id ? run : undefined));
	mocks.useAgentApprovals.mockReturnValue(
		query({ items: [approval], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
	);
	mocks.useAgentApproval.mockImplementation((id: string) => query(id ? approval : undefined));
	mocks.useAgentCampaigns.mockReturnValue(
		query({
			items: [] as readonly AgentCampaignView[],
			pagination: { total: 0, limit: 20, offset: 0, hasMore: false },
		}),
	);
	mocks.useAgentCampaign.mockReturnValue(query(undefined));
	mocks.useAgentEventNotifications.mockReturnValue("stopped");
});

describe("AgentConsolePage", () => {
	it("separates Research Agent Lab, System Agent Ops, and the Approval Inbox", () => {
		const lab = render(<AgentConsolePage surface="research-lab" initialSearch={{ tab: "runs" }} />, { wrapper });
		expect(screen.getByRole("region", { name: "Research Agent Lab" })).toBeInTheDocument();
		expect(screen.getByText("Research Agent Lab · Strategy Author")).toBeInTheDocument();
		expect(screen.queryByRole("tab", { name: "Approvals" })).not.toBeInTheDocument();
		lab.unmount();

		const ops = render(<AgentConsolePage surface="system-ops" initialSearch={{ tab: "runs" }} />, { wrapper });
		expect(screen.getByRole("region", { name: "System Agent Ops" })).toBeInTheDocument();
		expect(screen.getByText("System Agent Ops · Runtime supervision")).toBeInTheDocument();
		expect(screen.queryByRole("tab", { name: "Approvals" })).not.toBeInTheDocument();
		ops.unmount();

		render(<AgentConsolePage surface="approval-inbox" initialSearch={{ tab: "approvals" }} />, { wrapper });
		expect(screen.getByRole("region", { name: "Agent Approval Inbox" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Approvals" })).toBeInTheDocument();
		expect(screen.queryByRole("tab", { name: "Runs" })).not.toBeInTheDocument();
	});

	it("exposes every required visual-audit contract slot", () => {
		const { container } = render(<AgentConsolePage initialSearch={{ tab: "runs" }} />, { wrapper });
		for (const tab of screen.getAllByRole("tab")) {
			const controlledId = tab.getAttribute("aria-controls");
			expect(controlledId, `${tab.textContent} aria-controls`).toBeTruthy();
			expect(document.getElementById(controlledId!), `${tab.textContent} tabpanel`).not.toBeNull();
		}

		for (const [name, slot] of Object.entries({
			shell: "shell",
			tabs: "tabs",
			source: "source",
			main: "main",
			inspector: "inspector",
			status: "status-bar",
		})) {
			expect(container.querySelector(`[data-slot='${slot}']`), name).not.toBeNull();
		}
		const toolbar = container.querySelector("[data-slot='task-toolbar']");
		expect(toolbar).toHaveClass("h-[42px]", "flex-row");
		expect(container.querySelector("[data-slot='agent-header']")).not.toBeInTheDocument();
		const shell = container.querySelector("[data-slot='shell']");
		expect(shell).toHaveClass("h-full", "min-h-0", "overflow-hidden");
		const workspace = container.querySelector("[data-slot='workspace']");
		expect(workspace).toHaveClass("flex-1", "xl:grid-cols-[18rem_minmax(0,1fr)_23.25rem]");
		expect(screen.getByRole("main")).toContainElement(screen.getByRole("link", { name: "返回 Agent 任务列表" }));
		expect(screen.getByRole("link", { name: "返回 Agent 任务列表" })).toHaveAttribute(
			"href",
			"#agent-unified-task-list",
		);
	});

	it("keeps historical projections readable when runtime is disabled and blocks creation", async () => {
		const { container } = render(<AgentConsolePage initialSearch={{ tab: "runs", selected: "run-104" }} />, {
			wrapper,
		});

		expect(screen.getByRole("status", { name: "Agent runtime" })).toHaveTextContent("provider_not_configured");
		expect(
			container.querySelector("[data-slot='shell-header-extension']")?.textContent?.match(/provider not configured/g),
		).toHaveLength(1);
		expect(screen.getByRole("button", { name: "新建 Run" })).toBeDisabled();
		expect(screen.getByRole("heading", { name: "核对候选因子的证据链" })).toBeInTheDocument();
		expect(screen.getByRole("main")).toHaveTextContent("Evidence Spine");
	});

	it("keeps the selected Run, Campaign, and Approval actions in a compact bottom action bar", () => {
		const runView = render(<AgentConsolePage initialSearch={{ tab: "runs", selected: run.runId }} />, { wrapper });
		const runActions = runView.container.querySelector("[data-slot='mobile-actions']");
		expect(runView.container.querySelector("[data-slot='mobile-controls']")).toHaveClass("sticky", "bottom-0");
		expect(runActions).toHaveClass("xl:hidden");
		expect(runActions).toHaveTextContent("取消 Run");
		runView.unmount();

		mocks.useAgentCampaigns.mockReturnValue(
			query({ items: [campaign], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentCampaign.mockReturnValue(query(campaign));
		const campaignView = render(
			<AgentConsolePage initialSearch={{ tab: "campaigns", selected: campaign.campaignId }} />,
			{ wrapper },
		);
		expect(campaignView.container.querySelector("[data-slot='mobile-actions']")).toHaveTextContent("审查并批准");
		campaignView.unmount();

		mocks.useAgentCampaign.mockReturnValue(query(undefined));
		const approvalView = render(
			<AgentConsolePage initialSearch={{ tab: "approvals", selected: approval.approvalId }} />,
			{ wrapper },
		);
		const approvalAction = approvalView.container.querySelector<HTMLButtonElement>(
			"[data-slot='mobile-actions'] button",
		);
		expect(approvalAction).toHaveTextContent("审查精确动作");
		expect(approvalAction).toBeDisabled();
	});

	it("marks a partial projection and does not invent omitted output content", () => {
		render(<AgentConsolePage initialSearch={{ tab: "runs", selected: "run-104" }} />, { wrapper });

		expect(screen.getByRole("region", { name: "Current page summary" })).toHaveTextContent("1 / 1 loaded");
		expect(screen.getByRole("region", { name: "Current page summary" })).toHaveTextContent("waiting approval 1");
		expect(screen.getByRole("region", { name: "Current page summary" })).toHaveTextContent("time window");
		expect(screen.getByRole("main")).toHaveTextContent("output_summary_pending");
		expect(screen.getByRole("main")).toHaveTextContent("内容未在展示契约中提供");
		expect(screen.getAllByText("evidence-7")).not.toHaveLength(0);
		expect(screen.getByText("cursor 17")).toBeInTheDocument();
		expect(screen.getByRole("main")).toHaveTextContent("10,600 tokens remaining");
		expect(screen.getByRole("main")).toHaveTextContent("$2.82 remaining");
		expect(screen.getByRole("main")).toHaveTextContent("stop reasonnone");
	});

	it("shows the exact PIT authority and lets a queued run execute by revision", () => {
		const queued = { ...run, status: "queued" as const, revision: 0 };
		mocks.useAgentCapability.mockReturnValue(
			query({
				enabled: true,
				runtimeState: "available",
				provider: "glm",
				availableProfiles: ["balanced"],
				defaultProfile: "balanced",
				degradationReason: null,
				checkedAt: "2026-08-18T01:00:00Z",
			}),
		);
		mocks.useAgentRuns.mockReturnValue(
			query({ items: [queued], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentRun.mockImplementation((id: string) => query(id ? queued : undefined));

		render(<AgentConsolePage initialSearch={{ tab: "runs", selected: queued.runId }} />, { wrapper });

		expect(screen.getByRole("main")).toHaveTextContent("snapshot-certified-2026-08-18");
		expect(screen.getByRole("main")).toHaveTextContent("2026-08-18T00:50:00Z");
		fireEvent.click(screen.getAllByRole("button", { name: "执行 Run" })[0] as HTMLButtonElement);
		expect(mocks.executeRun).toHaveBeenCalledWith({ runId: queued.runId, revision: 0 });
	});

	it("keeps a queued run readable but blocks execution while the model lane is degraded", () => {
		const queued = { ...run, status: "queued" as const, revision: 0 };
		mocks.useAgentCapability.mockReturnValue(
			query({
				enabled: true,
				runtimeState: "degraded",
				provider: null,
				availableProfiles: ["balanced"],
				defaultProfile: "balanced",
				degradationReason: "agent_model_execution_unconfigured",
				checkedAt: "2026-08-18T01:00:00Z",
			}),
		);
		mocks.useAgentRuns.mockReturnValue(
			query({ items: [queued], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentRun.mockImplementation((id: string) => query(id ? queued : undefined));

		render(<AgentConsolePage initialSearch={{ tab: "runs", selected: queued.runId }} />, { wrapper });

		expect(screen.getByRole("status", { name: "Agent runtime" })).toHaveTextContent("模型执行已禁用");
		expect(screen.queryByRole("button", { name: "执行 Run" })).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "新建 Run" })).toBeEnabled();
	});

	it("forwards an exact URL context pair to the durable run list", () => {
		render(
			<AgentConsolePage
				initialSearch={{
					tab: "runs",
					contextType: "strategy",
					contextId: "strategy-12@4",
				}}
			/>,
			{ wrapper },
		);

		expect(mocks.useAgentRuns).toHaveBeenCalledWith(
			expect.objectContaining({ contextType: "strategy", contextId: "strategy-12@4" }),
		);
	});

	it("restores recent session pagination and exposes exact context search inputs", () => {
		render(
			<AgentConsolePage
				initialSearch={{
					tab: "runs",
					contextType: "strategy",
					contextId: "strategy-12@4",
					sessionOffset: 20,
				}}
			/>,
			{ wrapper },
		);

		expect(mocks.useAgentSessions).toHaveBeenCalledWith(20);
		expect(screen.getByRole("button", { name: /session-9/u })).toHaveTextContent("audit");
		expect(screen.getByLabelText("Context type")).toHaveValue("strategy");
		expect(screen.getByLabelText("Context identity")).toHaveValue("strategy-12@4");
	});

	it("fails closed for an expired exact approval", () => {
		render(<AgentConsolePage initialSearch={{ tab: "approvals", selected: "approval-4" }} />, { wrapper });

		expect(screen.getByText("Exact action payload")).toBeInTheDocument();
		expect(screen.getByText("approval 已过期，不能提交决定。")).toBeInTheDocument();
		for (const button of screen.getAllByRole("button", { name: "审查精确动作" })) {
			expect(button).toBeDisabled();
		}
	});

	it("drives durable filters, projection selection, pagination, and governed creation controls", async () => {
		const user = userEvent.setup();
		const secondRun: AgentRunView = {
			...run,
			runId: "run-105",
			status: "completed",
			createdAt: "2026-08-18T02:00:00Z",
			finishedAt: "2026-08-18T02:10:00Z",
		};
		const validApproval: AgentApprovalView = { ...approval, expiresAt: "2099-08-25T01:30:00Z" };
		mocks.useAgentCapability.mockReturnValue(
			query({
				enabled: true,
				runtimeState: "available",
				provider: "configured",
				availableProfiles: ["balanced", "quality"],
				defaultProfile: "balanced",
				degradationReason: null,
				checkedAt: "2026-08-18T01:00:00Z",
			}),
		);
		mocks.useAgentRuns.mockReturnValue(
			query({ items: [run, secondRun], pagination: { total: 45, limit: 20, offset: 20, hasMore: true } }),
		);
		mocks.useAgentSessions.mockReturnValue(
			query({ items: [session], pagination: { total: 45, limit: 20, offset: 20, hasMore: true } }),
		);
		mocks.useAgentCampaigns.mockReturnValue(
			query({ items: [campaign], pagination: { total: 21, limit: 20, offset: 0, hasMore: true } }),
		);
		mocks.useAgentCampaign.mockImplementation((id: string) => query(id ? campaign : undefined));
		mocks.useAgentApprovals.mockReturnValue(
			query({ items: [validApproval], pagination: { total: 21, limit: 20, offset: 0, hasMore: true } }),
		);
		mocks.useAgentApproval.mockImplementation((id: string) => query(id ? validApproval : undefined));
		const onSearchChange = vi.fn();
		render(
			<AgentConsolePage
				initialSearch={{ tab: "runs", offset: 20, sessionOffset: 20 }}
				onSearchChange={onSearchChange}
			/>,
			{ wrapper },
		);

		expect(screen.getByRole("region", { name: "Current page summary" })).toHaveTextContent(
			"completed 1 · waiting approval 1",
		);
		for (const button of screen.getAllByRole("button", { name: "上一页" })) fireEvent.click(button);
		for (const button of screen.getAllByRole("button", { name: "下一页" })) fireEvent.click(button);
		fireEvent.click(screen.getByRole("button", { name: /Session session-9/u }));
		fireEvent.click(screen.getByRole("button", { name: /run-105/u }));
		fireEvent.change(screen.getByLabelText("Context type"), { target: { value: "strategy" } });
		fireEvent.change(screen.getByLabelText("Context identity"), { target: { value: "strategy-12@4" } });
		fireEvent.click(screen.getByRole("button", { name: "清除上下文" }));
		fireEvent.change(screen.getByRole("combobox", { name: "Status filter" }), { target: { value: "running" } });
		fireEvent.click(screen.getByRole("button", { name: "新建 Run" }));
		expect(screen.getByRole("heading", { name: "创建 governed run" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		await user.click(screen.getByRole("tab", { name: "Campaigns" }));
		await screen.findByRole("button", { name: /campaign-7/u });
		fireEvent.click(screen.getByRole("button", { name: /campaign-7/u }));
		fireEvent.click(screen.getByRole("button", { name: "新建 Campaign" }));
		expect(screen.getByRole("heading", { name: "Campaign Draft Wizard" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		await user.click(screen.getByRole("tab", { name: "Approvals" }));
		await screen.findByRole("button", { name: /approval-4/u });
		fireEvent.click(screen.getByRole("button", { name: /approval-4/u }));
		await waitFor(() => expect(onSearchChange).toHaveBeenCalled());
	});

	it("opens exact Run evidence, artifact, guardrail, and cancellation controls", () => {
		mocks.useAgentCapability.mockReturnValue(
			query({
				enabled: true,
				runtimeState: "available",
				provider: "configured",
				availableProfiles: ["balanced"],
				defaultProfile: "balanced",
				degradationReason: null,
				checkedAt: "2026-08-18T01:00:00Z",
			}),
		);
		const { container } = render(<AgentConsolePage initialSearch={{ tab: "runs", selected: run.runId }} />, {
			wrapper,
		});

		for (const button of screen.getAllByRole("button", { name: "evidence-7" })) fireEvent.click(button);
		fireEvent.click(screen.getByRole("button", { name: "reason not provided" }));
		fireEvent.click(screen.getByRole("button", { name: "artifact-2" }));
		expect(container.querySelector("[data-slot='inspector']")).toHaveTextContent("Selected artifact");
		fireEvent.click(screen.getByRole("button", { name: "打开详情" }));
		expect(screen.getByRole("heading", { name: "Artifact preview" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getAllByRole("button", { name: "取消 Run" })[0] as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "取消 Run" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));
		fireEvent.click(screen.getAllByRole("button", { name: "取消 Run" }).at(-1) as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "取消 Run" })).toBeInTheDocument();
	});

	it("opens exact Campaign references, approval, cancellation, and Approval review controls", () => {
		const governedCampaign: AgentCampaignView = {
			...campaign,
			evidenceRefs: ["campaign-evidence"],
			artifactRefs: ["campaign-artifact"],
			guardrail: { status: "blocked", reasonCode: "budget_exhausted" },
		};
		mocks.useAgentCapability.mockReturnValue(
			query({
				enabled: true,
				runtimeState: "available",
				provider: "configured",
				availableProfiles: ["balanced"],
				defaultProfile: "balanced",
				degradationReason: null,
				checkedAt: "2026-08-18T01:00:00Z",
			}),
		);
		mocks.useAgentCampaigns.mockReturnValue(
			query({ items: [governedCampaign], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentCampaign.mockImplementation((id: string) => query(id ? governedCampaign : undefined));
		const draftView = render(<AgentConsolePage initialSearch={{ tab: "campaigns", selected: campaign.campaignId }} />, {
			wrapper,
		});

		fireEvent.click(screen.getByRole("button", { name: "Evidence · campaign-evidence" }));
		fireEvent.click(screen.getByRole("button", { name: "Artifact · campaign-artifact" }));
		fireEvent.click(screen.getByRole("button", { name: "Guardrail · blocked" }));
		expect(draftView.container.querySelector("[data-slot='inspector']")).toHaveTextContent("Selected guardrail");
		fireEvent.click(screen.getAllByRole("button", { name: "审查并批准" })[0] as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "Campaign 精确审批" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));
		fireEvent.click(screen.getAllByRole("button", { name: "审查并批准" }).at(-1) as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "Campaign 精确审批" })).toBeInTheDocument();
		draftView.unmount();

		const authorizedCampaign: AgentCampaignView = {
			...governedCampaign,
			status: "authorized",
			authorizationHash: "e".repeat(64),
		};
		mocks.useAgentCampaigns.mockReturnValue(
			query({ items: [authorizedCampaign], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentCampaign.mockImplementation((id: string) => query(id ? authorizedCampaign : undefined));
		const authorizedView = render(
			<AgentConsolePage initialSearch={{ tab: "campaigns", selected: campaign.campaignId }} />,
			{ wrapper },
		);
		fireEvent.click(screen.getAllByRole("button", { name: "取消 Campaign" })[0] as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "取消 Campaign" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));
		fireEvent.click(screen.getAllByRole("button", { name: "取消 Campaign" }).at(-1) as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "取消 Campaign" })).toBeInTheDocument();
		authorizedView.unmount();

		const validApproval: AgentApprovalView = { ...approval, expiresAt: "2099-08-25T01:30:00Z" };
		mocks.useAgentApprovals.mockReturnValue(
			query({ items: [validApproval], pagination: { total: 1, limit: 20, offset: 0, hasMore: false } }),
		);
		mocks.useAgentApproval.mockImplementation((id: string) => query(id ? validApproval : undefined));
		render(<AgentConsolePage initialSearch={{ tab: "approvals", selected: approval.approvalId }} />, { wrapper });
		fireEvent.click(screen.getAllByRole("button", { name: "审查精确动作" })[0] as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "审查精确动作" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));
		fireEvent.click(screen.getAllByRole("button", { name: "审查精确动作" }).at(-1) as HTMLButtonElement);
		expect(screen.getByRole("heading", { name: "审查精确动作" })).toBeInTheDocument();
	});
});

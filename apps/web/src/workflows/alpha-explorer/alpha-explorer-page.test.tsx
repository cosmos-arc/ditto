import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentCampaignView } from "@/features/agent";
import { AlphaExplorerPage, AlphaExplorerPageView } from "./alpha-explorer-page";

const mocks = vi.hoisted(() => ({
	useAgentCampaign: vi.fn(),
	useAgentCampaigns: vi.fn(),
	useAgentCapability: vi.fn(),
	useAgentEventNotifications: vi.fn(),
}));

vi.mock("@/features/agent", () => ({
	AgentCampaignApprovalDialog: ({
		campaign,
		open,
		onOpenChange,
	}: {
		readonly campaign: { readonly campaignId: string };
		readonly open: boolean;
		readonly onOpenChange: (open: boolean) => void;
	}) =>
		open ? (
			<div role="dialog" aria-label={`批准 ${campaign.campaignId}`}>
				<button type="button" onClick={() => onOpenChange(false)}>
					关闭批准
				</button>
			</div>
		) : null,
	AgentCampaignDraftSheet: ({
		open,
		onOpenChange,
		onCreated,
	}: {
		readonly open: boolean;
		readonly onOpenChange: (open: boolean) => void;
		readonly onCreated: (campaign: { readonly campaignId: string }) => void;
	}) =>
		open ? (
			<div role="dialog" aria-label="创建 Campaign">
				<button type="button" onClick={() => onCreated({ campaignId: "campaign-created" })}>
					完成创建
				</button>
				<button type="button" onClick={() => onOpenChange(false)}>
					取消创建
				</button>
			</div>
		) : null,
	useAgentCampaign: mocks.useAgentCampaign,
	useAgentCampaigns: mocks.useAgentCampaigns,
	useAgentCapability: mocks.useAgentCapability,
	useAgentEventNotifications: mocks.useAgentEventNotifications,
}));

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

function campaignWith(campaignId: string, overrides: Partial<AgentCampaignView> = {}): AgentCampaignView {
	return {
		...campaign,
		campaignId,
		canonicalManifest: { campaign_id: campaignId },
		...overrides,
	};
}

function query<T>(
	data: T | undefined,
	options: { readonly error?: unknown; readonly loading?: boolean; readonly stale?: boolean } = {},
) {
	return {
		data,
		error: options.error ?? null,
		isLoading: options.loading ?? false,
		isStale: options.stale ?? false,
	};
}

const capability = {
	enabled: true,
	runtimeState: "ready",
};

beforeEach(() => {
	vi.clearAllMocks();
	mocks.useAgentCapability.mockReturnValue(query(capability));
	mocks.useAgentCampaigns.mockReturnValue(
		query({
			items: [campaign],
			pagination: { total: 1, limit: 50, offset: 0, hasMore: false },
		}),
	);
	mocks.useAgentCampaign.mockImplementation((campaignId: string) => query(campaignId ? campaign : undefined));
	mocks.useAgentEventNotifications.mockReturnValue("stopped");
});

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

		const artifactButton = screen.getAllByRole("button", { name: "预览 artifact-2" })[0];
		if (!artifactButton) throw new Error("expected artifact preview button");
		fireEvent.click(artifactButton);
		expect(screen.getByRole("dialog", { name: "产物预览 · artifact-2" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getByRole("button", { name: "查看阻断原因" }));
		expect(screen.getByRole("dialog", { name: "Guardrail 阻断详情" })).toHaveTextContent("sensitive_field_forbidden");
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getByRole("button", { name: "打开 Copilot 上下文" }));
		expect(screen.getByRole("dialog", { name: "Copilot · Alpha 上下文" })).toHaveTextContent("snapshot-11");
	});

	it("renders every campaign lifecycle without treating partial or terminal work as running", () => {
		const waiting = campaignWith("waiting", {
			guardrail: null,
			projectionState: "complete",
		});
		const partial = campaignWith("partial", {
			status: "completed",
			guardrail: null,
			projectionState: "partial",
		});
		const blocked = campaignWith("blocked", {
			status: "failed",
			guardrail: null,
			projectionState: "complete",
		});
		const running = campaignWith("running", {
			status: "running",
			guardrail: null,
			projectionState: "complete",
		});
		const ready = campaignWith("ready", {
			status: "completed_with_failures",
			guardrail: null,
			projectionState: "complete",
		});

		render(
			<AlphaExplorerPageView
				campaigns={[waiting, partial, blocked, running, ready]}
				selectedCampaign={waiting}
				state="ready"
				onSelectCampaign={vi.fn()}
				onOpenApproval={vi.fn()}
			/>,
		);

		for (const label of ["等待审批", "部分可用", "已阻断", "探索中", "可复核"]) {
			expect(screen.getAllByText(label).length, label).toBeGreaterThan(0);
		}
		expect(screen.getAllByRole("button", { name: "审查并批准 Campaign" })).toHaveLength(1);
	});

	it("renders explicit loading, error, empty, and missing-projection states", () => {
		const props = {
			campaigns: [] as readonly AgentCampaignView[],
			selectedCampaign: undefined,
			onSelectCampaign: vi.fn(),
			onOpenApproval: vi.fn(),
		};
		const view = render(<AlphaExplorerPageView {...props} state="loading" />);
		expect(screen.getByText("正在读取 Campaign projection…")).toBeInTheDocument();
		expect(screen.getByText("暂无待处理项")).toBeInTheDocument();
		expect(screen.getByText("选择一个 Campaign 查看完整证据。")).toBeInTheDocument();
		expect(screen.getByText("Artifact 待生成")).toBeInTheDocument();
		expect(screen.getByText("未提供工具授权")).toBeInTheDocument();

		view.rerender(<AlphaExplorerPageView {...props} state="error" errorMessage="projection unavailable" />);
		expect(screen.getByText("projection unavailable")).toBeInTheDocument();

		view.rerender(<AlphaExplorerPageView {...props} state="empty" />);
		expect(screen.getByText(/暂无探索记录/u)).toBeInTheDocument();
	});

	it("shows fail-closed fallbacks when a ready projection omits optional evidence", () => {
		const incomplete = campaignWith("incomplete", {
			status: "completed",
			guardrail: null,
			objective: null,
			outputSummary: null,
			projectionReason: null,
			bestPrimaryMetricValue: null,
			allowedTools: [],
			evidenceRefs: [],
			artifactRefs: [],
			toolRecords: [],
		});

		render(
			<AlphaExplorerPageView
				campaigns={[incomplete]}
				selectedCampaign={incomplete}
				state="ready"
				onSelectCampaign={vi.fn()}
				onOpenApproval={vi.fn()}
			/>,
		);

		expect(screen.getByText(/等待可验证产物/u)).toBeInTheDocument();
		expect(screen.getByText("输出摘要未由 projection 提供")).toBeInTheDocument();
		expect(screen.getAllByText("未提供").length).toBeGreaterThan(0);
		expect(screen.getByText("无 evidence refs")).toBeInTheDocument();
		expect(screen.getByText("尚无可验证产物")).toBeInTheDocument();
	});

	it("opens the deep dive for the campaign whose action was invoked", () => {
		const selected = campaignWith("selected", { guardrail: null });
		const target = campaignWith("target", { guardrail: null, evidenceRefs: ["target-evidence"] });
		render(
			<AlphaExplorerPageView
				campaigns={[selected, target]}
				selectedCampaign={selected}
				state="ready"
				onSelectCampaign={vi.fn()}
				onOpenApproval={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: "深入 target" }));
		expect(screen.getByRole("dialog", { name: "候选深入 · target" })).toHaveTextContent("target-evidence");
	});
});

describe("AlphaExplorerPage", () => {
	it("synchronizes selection and preserves mode while creating and approving campaigns", async () => {
		const onSearchChange = vi.fn();
		mocks.useAgentCapability.mockReturnValue(query(capability, { stale: true }));
		mocks.useAgentEventNotifications.mockReturnValue("connected");
		render(<AlphaExplorerPage search={{}} onSearchChange={onSearchChange} />);

		await waitFor(() => expect(onSearchChange).toHaveBeenCalledWith({ mode: undefined, selected: "campaign-7" }));
		expect(screen.getByText("SSE connected")).toBeInTheDocument();
		expect(screen.getByText("数据 stale")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "Factor Lab" }));
		expect(onSearchChange).toHaveBeenCalledWith({ mode: "factor-lab", selected: "campaign-7" });

		fireEvent.click(screen.getByRole("button", { name: "启动探索" }));
		expect(screen.getByRole("dialog", { name: "创建 Campaign" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "完成创建" }));
		expect(onSearchChange).toHaveBeenCalledWith({ mode: "copilot", selected: "campaign-created" });

		fireEvent.click(screen.getAllByRole("button", { name: "审查并批准 Campaign" })[0]!);
		expect(screen.getByRole("dialog", { name: "批准 campaign-7" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "关闭批准" }));
		expect(screen.queryByRole("dialog", { name: "批准 campaign-7" })).not.toBeInTheDocument();
	});

	it("derives loading, error, empty, and disabled states from every query boundary", () => {
		mocks.useAgentCapability.mockReturnValue(query(undefined, { loading: true }));
		const loading = render(<AlphaExplorerPage />);
		expect(screen.getByText("正在读取 Campaign projection…")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "启动探索" })).toBeDisabled();
		loading.unmount();

		mocks.useAgentCapability.mockReturnValue(query({ enabled: false, runtimeState: "disabled" }));
		mocks.useAgentCampaigns.mockReturnValue(query(undefined, { error: new Error("campaign service down") }));
		const failed = render(<AlphaExplorerPage />);
		expect(screen.getByText("campaign service down")).toBeInTheDocument();
		failed.unmount();

		mocks.useAgentCampaigns.mockReturnValue(query(undefined, { error: new Error("   ") }));
		const fallback = render(<AlphaExplorerPage />);
		expect(screen.getByText("Alpha 数据暂时不可用，请重试。")).toBeInTheDocument();
		fallback.unmount();

		mocks.useAgentCampaigns.mockReturnValue(
			query({ items: [], pagination: { total: 0, limit: 50, offset: 0, hasMore: false } }),
		);
		mocks.useAgentCampaign.mockReturnValue(query(undefined));
		render(<AlphaExplorerPage />);
		expect(screen.getByText(/暂无探索记录/u)).toBeInTheDocument();
		expect(screen.getByText("未选择 Campaign")).toBeInTheDocument();
	});

	it("uses the selected detail projection and forwards card selection", () => {
		const listProjection = campaignWith("campaign-list", { objective: "列表投影" });
		const detailProjection = campaignWith("campaign-list", { objective: "详情投影" });
		mocks.useAgentCampaigns.mockReturnValue(
			query({
				items: [listProjection],
				pagination: { total: 1, limit: 50, offset: 0, hasMore: false },
			}),
		);
		mocks.useAgentCampaign.mockReturnValue(query(detailProjection));
		const onSearchChange = vi.fn();
		render(
			<AlphaExplorerPage
				search={{ mode: "autoresearch", selected: "campaign-list" }}
				onSearchChange={onSearchChange}
			/>,
		);

		expect(screen.getAllByText("详情投影").length).toBeGreaterThan(0);
		fireEvent.click(screen.getByRole("button", { name: /列表投影/u }));
		expect(onSearchChange).toHaveBeenCalledWith({
			mode: "autoresearch",
			selected: "campaign-list",
		});
	});
});

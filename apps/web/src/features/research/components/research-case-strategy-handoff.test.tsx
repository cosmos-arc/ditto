import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchCaseFixture } from "@/mocks/fixtures/selection";
import { server } from "@/mocks/server";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			children,
			to,
			params,
		}: {
			readonly children: ReactNode;
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
		}) => <a href={params?.["id"] ? to.replace("$id", params["id"]) : to}>{children}</a>,
	};
});

import {
	ResearchCaseStrategyHandoff,
	type StrategyHandoffCreateTarget,
	type StrategyHandoffTemplateOption,
} from "./research-case-strategy-handoff";

const TEMPLATES: readonly StrategyHandoffTemplateOption[] = [
	{
		templateId: "stock_selection",
		displayName: "股票多因子选股",
		description: "按因子权重合成分数选股并定期调仓。",
	},
];

const PROPOSAL = {
	template_id: "stock_selection",
	spec_json: {
		strategy_id: "stock-selection-draft",
		name: "研究: 验证动量因子持续性",
		template: "stock_selection",
		universe: "csi_a_share",
		asset_class: "stock",
		benchmark: "000300.SH",
		tags: ["handoff", "selection-spec:stock-core"],
		signal_expressions: ["momentum_1m", "value_pe"],
		signal_weights: [0.6, 0.4],
		selector: { method: "top_k", params: { k: 5 } },
	},
	converted: [
		{ source: "factor_weights", detail: "因子与权重转入信号表达式: momentum_1mx0.6, value_pex0.4" },
		{ source: "top_k", detail: "入选数量转入选取器 top_k=5" },
	],
	unconverted: [
		{
			source: "filter_groups",
			reason_code: "selection_filter_group_not_convertible",
			explanation:
				"筛选条件是决策日截面分数秩阈值, 回测模板没有对应的硬性过滤阶段; 条件保留在来源运行证据中, 不自动套用。",
			detail: "(momentum_1m >= 0.5)",
		},
	],
	lineage: {
		selection_run_id: researchCaseFixture.selection_run_id,
		selection_spec_hash: "c".repeat(64),
		asset_kind: "stock",
		as_of: "2026-08-31T07:00:00Z",
		knowledge_cutoff: "2026-08-31T07:00:00Z",
		universe_snapshot_id: "universe:sha256:stock-core",
		candidate_count: 2,
		research_case_id: researchCaseFixture.case_id,
	},
};

function renderPanel(
	createStrategy: (
		target: StrategyHandoffCreateTarget,
		key: string,
	) => Promise<{
		strategyId: string;
		version: number;
	}>,
) {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return render(
		<ResearchCaseStrategyHandoff
			caseDetail={researchCaseFixture}
			templates={TEMPLATES}
			createStrategy={createStrategy}
		/>,
		{
			wrapper: ({ children }: { children: ReactNode }) => (
				<QueryClientProvider client={client}>{children}</QueryClientProvider>
			),
		},
	);
}

beforeEach(() => {
	server.use(
		http.post("/api/v1/selections/runs/:runId/strategy-template-drafts", () => HttpResponse.json({ data: PROPOSAL })),
	);
});

describe("ResearchCaseStrategyHandoff", () => {
	it("selects a template, shows converted weights and unconverted condition explanations", async () => {
		renderPanel(async () => ({ strategyId: "created-1", version: 1 }));
		const user = userEvent.setup();

		await user.click(screen.getByRole("radio", { name: /股票多因子选股/ }));

		expect(await screen.findByText(/momentum_1mx0\.6/)).toBeInTheDocument();
		// 不可转换条件可见且带解释，不静默丢弃。
		expect(screen.getByText(/不能直接转换/)).toBeInTheDocument();
		expect(screen.getByText(/截面分数秩阈值/)).toBeInTheDocument();
		expect(screen.getByText(/csi_a_share/)).toBeInTheDocument();
		// 表单以提案默认值初始化。
		expect(screen.getByLabelText("新策略 ID")).toHaveValue("stock-selection-draft");
		expect(screen.getByLabelText("策略名称")).toHaveValue("研究: 验证动量因子持续性");
	});

	it("submits the proposal spec with edited identity and blocks duplicate creation", async () => {
		const createStrategy = vi.fn(async (_target: StrategyHandoffCreateTarget, _key: string) => ({
			strategyId: "handoff-momentum",
			version: 1,
		}));
		renderPanel(createStrategy);
		const user = userEvent.setup();

		await user.click(screen.getByRole("radio", { name: /股票多因子选股/ }));
		await screen.findByText(/momentum_1mx0\.6/);
		await user.clear(screen.getByLabelText("新策略 ID"));
		await user.type(screen.getByLabelText("新策略 ID"), "handoff-momentum");
		await user.click(screen.getByRole("button", { name: "创建策略草稿" }));

		const status = await screen.findByText(/已创建策略草稿 handoff-momentum · v1/);
		expect(status).toBeInTheDocument();
		expect(createStrategy).toHaveBeenCalledTimes(1);
		const firstCall = createStrategy.mock.calls[0];
		if (!firstCall) throw new Error("createStrategy was not called");
		const [target, idempotencyKey] = firstCall;
		expect(target.strategyId).toBe("handoff-momentum");
		// 服务端提案 spec 原样提交，仅身份字段跟表单。
		expect(target.specJson["signal_expressions"]).toEqual(["momentum_1m", "value_pe"]);
		expect(target.specJson["strategy_id"]).toBe("handoff-momentum");
		expect(target.tags).toEqual(["handoff", "selection-spec:stock-core"]);
		expect(idempotencyKey).toMatch(/^strategy-handoff:[0-9a-f-]{36}$/);
		// 成功后提供真实导航入口（版本治理与 Studio）。
		expect(screen.getByRole("link", { name: "查看策略版本" })).toHaveAttribute(
			"href",
			"/research/strategies/handoff-momentum",
		);
		expect(screen.getByRole("link", { name: "打开 Strategy Studio" })).toHaveAttribute(
			"href",
			"/research/strategies/handoff-momentum/studio",
		);
	});

	it("keeps inputs and shows the reason when creation fails", async () => {
		const createStrategy = vi.fn(async (_target: StrategyHandoffCreateTarget, _key: string) => {
			throw new Error("strategy id already exists");
		});
		renderPanel(createStrategy);
		const user = userEvent.setup();

		await user.click(screen.getByRole("radio", { name: /股票多因子选股/ }));
		await screen.findByText(/momentum_1mx0\.6/);
		await user.click(screen.getByRole("button", { name: "创建策略草稿" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("strategy id already exists");
		// 失败保留输入，可改 ID 后重试。
		expect(screen.getByLabelText("新策略 ID")).toHaveValue("stock-selection-draft");
		expect(screen.getByRole("button", { name: "创建策略草稿" })).toBeEnabled();
	});

	it("explains a missing policy snapshot and links back to the exact run", async () => {
		server.use(
			http.post("/api/v1/selections/runs/:runId/strategy-template-drafts", () =>
				HttpResponse.json(
					{
						success: false,
						error_code: "selection_policy_snapshot_missing",
						detail: "the exact selection policy snapshot was never persisted",
					},
					{ status: 422 },
				),
			),
		);
		renderPanel(async () => ({ strategyId: "created-1", version: 1 }));
		const user = userEvent.setup();

		await user.click(screen.getByRole("radio", { name: /股票多因子选股/ }));

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("selection_policy_snapshot_missing");
		expect(alert).toHaveTextContent("条件快照未保存");
		expect(screen.getByRole("link", { name: "回到该运行的筛选工作面" })).toHaveAttribute(
			"href",
			`/markets/screener?run=${encodeURIComponent(researchCaseFixture.selection_run_id)}`,
		);
	});
});

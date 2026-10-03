import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchCaseFixture, selectionReceiptFixture } from "@/mocks/fixtures/selection";
import {
	ASSEMBLED_UNIVERSE_SNAPSHOT_ID,
	assembledSelectionRunResponse,
	selectionHandlers,
} from "@/mocks/handlers/selection";
import { server } from "@/mocks/server";
import { ContextActionsProvider, type ContextActionsRequest } from "@/providers";
import type { AssembleSelectionRunBody } from "../api";
import { SelectionWorkspacePage } from "./selection-workspace-page";

const renderContextActions = vi.fn((request: ContextActionsRequest) => (
	<a href="#context-action" data-context-id={request.contextId} data-context-type={request.contextType}>
		{request.evidenceLabel ?? "请求证据分析"}
	</a>
));

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<ContextActionsProvider renderActions={renderContextActions}>
			<QueryClientProvider client={client}>{children}</QueryClientProvider>
		</ContextActionsProvider>
	);
}

beforeEach(() => {
	localStorage.clear();
	renderContextActions.mockClear();
	server.use(...selectionHandlers);
});

describe("SelectionWorkspacePage", () => {
	it("starts from the production A-share stock discovery spec", async () => {
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		expect(screen.getByRole("textbox", { name: "SelectionSpec ID" })).toHaveValue("a-share-stock-discovery");
	});

	it("renders saved SelectionRuns with exact candidates, factors, exclusions, and Agent context", async () => {
		const user = userEvent.setup();
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		expect(screen.getAllByText("momentum").length).toBeGreaterThan(0);
		expect(screen.getByText("0.5400")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "贵州茅台" })).toHaveAttribute(
			"href",
			"/instruments/600519?tab=technical&selectionRunId=selection-run%3Asha256%3A1111111111111111111111111111111111111111111111111111111111111111",
		);
		await user.click(screen.getByRole("tab", { name: "排除 1" }));
		expect(screen.getByText("insufficient_liquidity")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "邯郸钢铁" })).toHaveAttribute(
			"href",
			"/instruments/600001?tab=technical&selectionRunId=selection-run%3Asha256%3A1111111111111111111111111111111111111111111111111111111111111111",
		);

		const memo = screen.getByRole("link", { name: "生成 SelectionMemo" });
		expect(memo).toHaveAttribute("data-context-type", "selection");
		expect(memo).toHaveAttribute("data-context-id", `selection-run:sha256:${"1".repeat(64)}`);
	});

	it("compares two exact saved runs and labels the source of drift", async () => {
		const user = userEvent.setup();
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		const selectors = await screen.findAllByRole("checkbox", { name: /加入运行对比/ });
		await user.click(selectors[0] as HTMLElement);
		await user.click(selectors[1] as HTMLElement);
		await user.click(screen.getByRole("button", { name: "比较 2 个运行" }));

		await expect(screen.findByText("数据快照已变化")).resolves.toBeInTheDocument();
		expect(screen.getByText("行业轮动已变化")).toBeInTheDocument();
		expect(screen.getByText("300750 · 1 → 2")).toBeInTheDocument();
	});

	it("saves a SelectionRun directly from the policy form without requiring a preview", async () => {
		const user = userEvent.setup();
		let createdBody: unknown;
		server.use(
			http.post("/api/v1/selections/runs", async ({ request }) => {
				createdBody = await request.json();
				return HttpResponse.json({ data: selectionReceiptFixture }, { status: 201 });
			}),
		);
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		const createButton = await screen.findByRole("button", { name: "创建运行" });
		await waitFor(() => expect(createButton).toBeEnabled());
		await user.click(createButton);

		await expect(screen.findByText("已保存 SelectionRun 111111111111")).resolves.toBeInTheDocument();
		const created = createdBody as AssembleSelectionRunBody;
		expect(created.spec_id).toBe("stock-momentum-manual");
		expect(created.factor_weights).toEqual([{ name: "momentum_1m", weight: 1 }]);
		expect(createdBody).not.toHaveProperty("instruments");
	});

	it("creates a ResearchCase from the exact run with selected candidates and a required objective", async () => {
		const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
		const user = userEvent.setup();
		Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
		let received: { objective: string; candidate_instrument_ids: number[] } | undefined;
		server.use(
			http.post("/api/v1/selections/runs/:runId/research-cases", async ({ request }) => {
				received = (await request.json()) as { objective: string; candidate_instrument_ids: number[] };
				return HttpResponse.json({ data: { ...researchCaseFixture, ...received } }, { status: 201 });
			}),
		);
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		expect(await screen.findByRole("button", { name: "创建研究用例" })).toBeDisabled();
		await user.type(screen.getByRole("textbox", { name: "研究假设 objective" }), "验证动量因子在食品饮料的持续性");
		await user.click(screen.getByRole("checkbox", { name: "纳入 600519 贵州茅台" }));
		await user.click(screen.getByRole("checkbox", { name: "纳入 300750 宁德时代" }));
		await expect(screen.findByRole("button", { name: "创建研究用例" })).resolves.toBeDisabled();
		await user.click(screen.getByRole("checkbox", { name: "纳入 600519 贵州茅台" }));
		await user.click(screen.getByRole("button", { name: "创建研究用例" }));

		await expect(screen.findByText(researchCaseFixture.case_id)).resolves.toBeInTheDocument();
		expect(received?.candidate_instrument_ids).toEqual([600519]);
		expect(received?.objective).toBe("验证动量因子在食品饮料的持续性");

		await user.click(screen.getByRole("button", { name: "复制用例 ID" }));
		expect(writeText).toHaveBeenCalledWith(researchCaseFixture.case_id);
		expect(screen.getByText("已复制")).toBeInTheDocument();
	});

	it("assembles server facts from the structured form and creates the run with the policy-only body", async () => {
		const user = userEvent.setup();
		let assembledBody: AssembleSelectionRunBody | undefined;
		let createdBody: unknown;
		server.use(
			http.post("/api/v1/selections/runs:assembled", async ({ request }) => {
				assembledBody = (await request.json()) as AssembleSelectionRunBody;
				return HttpResponse.json({ data: assembledSelectionRunResponse(assembledBody) });
			}),
			http.post("/api/v1/selections/runs", async ({ request }) => {
				createdBody = await request.json();
				return HttpResponse.json({ data: selectionReceiptFixture }, { status: 201 });
			}),
		);
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await user.click(screen.getByRole("button", { name: "组装并预览" }));

		const summary = await screen.findByRole("region", { name: "组装摘要" });
		expect(summary).toHaveTextContent(ASSEMBLED_UNIVERSE_SNAPSHOT_ID);
		expect(summary).toHaveTextContent("输入证券：2 只");
		expect(summary).toHaveTextContent("无缺失输入");

		await user.click(screen.getByRole("button", { name: "创建运行" }));

		await expect(screen.findByText("已保存 SelectionRun 111111111111")).resolves.toBeInTheDocument();
		const created = createdBody as AssembleSelectionRunBody;
		expect(created).toEqual(assembledBody);
		expect(created).toMatchObject({
			seed: 0,
			universe_id: "a-share-custom-202609",
			lookback_days: 400,
		});
		// policy-only：客户端事实包字段不再上送，由服务端在创建时组装。
		expect(createdBody).not.toHaveProperty("instruments");
		expect(createdBody).not.toHaveProperty("universe_snapshot_id");
	});

	it("surfaces declared missing inputs from the assembled request echo", async () => {
		const user = userEvent.setup();
		server.use(
			http.post("/api/v1/selections/runs:assembled", async ({ request }) => {
				const body = (await request.json()) as AssembleSelectionRunBody;
				const response = assembledSelectionRunResponse(body);
				response.request.rotation_missing_inputs = ["industry_inputs"];
				const first = response.request.instruments[0];
				if (first) {
					first.declared_missing_inputs = ["momentum_1m"];
					// 全市场池下缺失输入证券可能远超预览上限：第 21 只之后只汇总计数。
					for (const instrument_id of Array.from({ length: 25 }, (_, index) => index + 1)) {
						response.request.instruments.push({
							...first,
							instrument_id,
							instrument_name: `合成证券${instrument_id}`,
							declared_missing_inputs: ["bars"],
						});
					}
				}
				return HttpResponse.json({ data: response });
			}),
		);
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await user.click(screen.getByRole("button", { name: "组装并预览" }));

		const summary = await screen.findByRole("region", { name: "组装摘要" });
		expect(summary).toHaveTextContent("行业轮动缺失输入：industry_inputs");
		expect(summary).toHaveTextContent("贵州茅台（600519）缺失输入：momentum_1m");
		expect(summary).toHaveTextContent("另有 6 只证券存在缺失输入");
		expect(summary).not.toHaveTextContent("合成证券25");
		expect(summary).not.toHaveTextContent("无缺失输入");
	});

	it("blocks assembly on client-side strategy validation with in-place messages", async () => {
		const user = userEvent.setup();
		const assembleError = vi.fn(() => HttpResponse.json({ detail: "unreachable" }, { status: 200 }));
		server.use(http.post("/api/v1/selections/runs:assembled", () => assembleError()));
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await user.click(screen.getByRole("button", { name: "添加因子" }));
		await user.type(screen.getByLabelText("因子 2 名称"), "momentum_1m");
		expect(screen.getByRole("button", { name: "组装并预览" })).toBeDisabled();
		expect(screen.getByText("因子名称重复：momentum_1m")).toBeInTheDocument();

		await user.clear(screen.getByLabelText("因子 2 名称"));
		await user.type(screen.getByLabelText("因子 2 名称"), "reversal_1w");
		await user.clear(screen.getByLabelText("因子 1 权重"));
		await user.type(screen.getByLabelText("因子 1 权重"), "0.4");
		await user.clear(screen.getByLabelText("因子 2 权重"));
		await user.type(screen.getByLabelText("因子 2 权重"), "0.4");
		expect(screen.getByRole("button", { name: "组装并预览" })).toBeDisabled();
		expect(screen.getByText("因子权重之和需为 1")).toBeInTheDocument();

		await user.clear(screen.getByLabelText("因子 2 权重"));
		await user.type(screen.getByLabelText("因子 2 权重"), "0.6");
		expect(screen.getByRole("button", { name: "组装并预览" })).toBeEnabled();
		expect(assembleError).not.toHaveBeenCalled();

		fireEvent.change(screen.getByLabelText("决策时点 as_of"), { target: { value: "" } });
		expect(screen.getByRole("button", { name: "组装并预览" })).toBeDisabled();
		expect(screen.getByText("请填写决策时点 as_of")).toBeInTheDocument();
	});

	it("shows the server 422 validation error without crashing", async () => {
		const user = userEvent.setup();
		server.use(
			http.post("/api/v1/selections/runs:assembled", () =>
				HttpResponse.json({ detail: "因子权重不得重复且权重之和必须为 1" }, { status: 422 }),
			),
		);
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await user.click(screen.getByRole("button", { name: "组装并预览" }));

		await expect(screen.findByText("因子权重不得重复且权重之和必须为 1")).resolves.toBeInTheDocument();
		// policy-only：预览失败不阻塞创建，数据完整性由服务端在创建时把关。
		expect(screen.getByRole("button", { name: "创建运行" })).toBeEnabled();
	});
});

it("loads universe options from the authoritative list and requires an explicit pick", async () => {
	const user = userEvent.setup();
	server.use(
		http.get("/api/v1/universes", () =>
			HttpResponse.json({
				data: [
					{
						universe_id: "a-share-custom-202609",
						name: "A 股全市场池",
						universe_type: "custom",
						description: null,
						source_ref: null,
					},
				],
			}),
		),
	);
	render(<SelectionWorkspacePage />, { wrapper: wrapper() });

	const select = await screen.findByLabelText("universe 证券池");
	const option = await screen.findByRole("option", { name: /A 股全市场池/ });
	await user.selectOptions(select, option);
	expect((select as HTMLSelectElement).value).toBe("a-share-custom-202609");
	expect(screen.getByRole("button", { name: "组装并预览" })).toBeEnabled();
});

it("rejects an assembled response whose policy echo drifts from the submitted window", async () => {
	const user = userEvent.setup();
	server.use(
		http.post("/api/v1/selections/runs:assembled", async ({ request }) => {
			const body = (await request.json()) as AssembleSelectionRunBody;
			const response = assembledSelectionRunResponse(body);
			// 模拟错配/过期响应：把区间终点挪到决策时点之后。
			response.request.data_to = "2026-12-31";
			return HttpResponse.json({ data: response });
		}),
	);
	render(<SelectionWorkspacePage />, { wrapper: wrapper() });
	await waitFor(() => expect((screen.getByLabelText("universe 证券池") as HTMLSelectElement).value).not.toBe(""));

	await user.click(screen.getByRole("button", { name: "组装并预览" }));

	await waitFor(() =>
		expect(screen.getByRole("alert")).toHaveTextContent(/组装响应的策略回显或服务端事实与提交不一致/),
	);
	expect(screen.queryByRole("region", { name: "组装摘要" })).not.toBeInTheDocument();
});

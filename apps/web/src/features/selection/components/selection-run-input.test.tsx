import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { selectionHandlers } from "@/mocks/handlers/selection";
import { server } from "@/mocks/server";
import type { AssembleSelectionRunBody } from "../api";
import { SelectionRunInput } from "./selection-run-input";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => {
	server.use(...selectionHandlers);
});

describe("SelectionRunInput factor conditions (#740)", () => {
	it("builds filter groups from the factor catalog and submits the exact policy body", async () => {
		const user = userEvent.setup();
		let createdBody: AssembleSelectionRunBody | undefined;
		server.use(
			http.post("/api/v1/selections/runs", async ({ request }) => {
				createdBody = (await request.json()) as AssembleSelectionRunBody;
				return HttpResponse.json({}, { status: 201 });
			}),
		);
		const onRun = (input: AssembleSelectionRunBody) => {
			createdBody = input;
		};
		render(<SelectionRunInput busy={false} onRun={onRun} />, { wrapper: wrapper() });

		// 目录加载后才能构建条件与权重。
		await user.click(await screen.findByRole("button", { name: "添加条件组" }));
		await user.selectOptions(screen.getByLabelText("条件组 1 因子 1"), "momentum_1m");
		await user.selectOptions(screen.getByLabelText("条件组 1 算子 1"), "lte");
		await user.clear(screen.getByLabelText("条件组 1 阈值 1"));
		await user.type(screen.getByLabelText("条件组 1 阈值 1"), "0.4");

		const createButton = await screen.findByRole("button", { name: "创建运行" });
		await waitFor(() => expect(createButton).toBeEnabled());
		await user.click(createButton);

		await waitFor(() => expect(createdBody).toBeDefined());
		expect(createdBody?.factor_filter_groups).toEqual([
			{ conditions: [{ factor_name: "momentum_1m", operator: "lte", value: 0.4 }] },
		]);
		// 未添加条件时默认提交空条件组（与策略权重共存）。
		expect(createdBody?.factor_weights).toEqual([{ name: "momentum_1m", weight: 1 }]);
	});

	it("supports OR rows within a group and multiple AND groups", async () => {
		const user = userEvent.setup();
		let submitted: AssembleSelectionRunBody | undefined;
		const onRun = (input: AssembleSelectionRunBody) => {
			submitted = input;
		};
		render(<SelectionRunInput busy={false} onRun={onRun} />, { wrapper: wrapper() });

		await user.click(await screen.findByRole("button", { name: "添加条件组" }));
		await user.selectOptions(screen.getByLabelText("条件组 1 因子 1"), "momentum_1m");
		await user.click(screen.getByRole("button", { name: "添加条件" }));
		await user.selectOptions(screen.getByLabelText("条件组 1 因子 2"), "reversal_1w");
		await user.click(screen.getByRole("button", { name: "添加条件组" }));
		await user.selectOptions(screen.getByLabelText("条件组 2 因子 1"), "volatility_factor");
		await user.selectOptions(screen.getByLabelText("条件组 2 算子 1"), "lte");
		await user.clear(screen.getByLabelText("条件组 2 阈值 1"));
		await user.type(screen.getByLabelText("条件组 2 阈值 1"), "0.5");

		const createButton = screen.getByRole("button", { name: "创建运行" });
		await waitFor(() => expect(createButton).toBeEnabled());
		await user.click(createButton);

		await waitFor(() => expect(submitted).toBeDefined());
		expect(submitted?.factor_filter_groups).toEqual([
			{
				conditions: [
					{ factor_name: "momentum_1m", operator: "gte", value: 0.8 },
					{ factor_name: "reversal_1w", operator: "gte", value: 0.8 },
				],
			},
			{ conditions: [{ factor_name: "volatility_factor", operator: "lte", value: 0.5 }] },
		]);
	});

	it("rejects thresholds outside the unit-rank scale with an in-place message", async () => {
		const user = userEvent.setup();
		render(<SelectionRunInput busy={false} onRun={() => {}} />, { wrapper: wrapper() });

		await user.click(await screen.findByRole("button", { name: "添加条件组" }));
		await user.clear(screen.getByLabelText("条件组 1 阈值 1"));
		await user.type(screen.getByLabelText("条件组 1 阈值 1"), "1.5");

		expect(await screen.findByText("条件组 1 行 1 阈值需在 0 到 1 之间（截面分数秩）")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "创建运行" })).toBeDisabled();
	});

	it("shows catalog metadata (unit, lookback, dependencies) beside each pick", async () => {
		const user = userEvent.setup();
		render(<SelectionRunInput busy={false} onRun={() => {}} />, { wrapper: wrapper() });

		await user.click(await screen.findByRole("button", { name: "添加条件组" }));
		await user.selectOptions(screen.getByLabelText("条件组 1 因子 1"), "momentum_3m");

		expect(screen.getByText(/3-month price momentum \(60-day return\) · 回看 60 个交易日/)).toBeInTheDocument();
		expect(screen.getByText(/截面分数秩 \(0,1\]/)).toBeInTheDocument();
	});

	it("surfaces catalog failure and keeps creation disabled until it recovers", async () => {
		const user = userEvent.setup();
		server.use(
			http.get("/api/v1/selections/factor-catalog", () =>
				HttpResponse.json({ detail: "catalog unavailable" }, { status: 500 }),
			),
		);
		render(<SelectionRunInput busy={false} onRun={() => {}} />, { wrapper: wrapper() });

		expect(await screen.findByText("因子目录加载失败")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "创建运行" })).toBeDisabled();

		server.use(...selectionHandlers);
		await user.click(screen.getByRole("button", { name: "重试" }));
		expect(await screen.findByRole("button", { name: "添加条件组" })).toBeInTheDocument();
	});
});

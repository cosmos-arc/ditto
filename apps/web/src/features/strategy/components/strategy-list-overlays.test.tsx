import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { useCreateStrategy } from "../hooks";
import { StrategyListOverlays } from "./strategy-list-overlays";

function mockMutationState() {
	return {
		mutate: vi.fn(),
		reset: vi.fn(),
		data: undefined,
		error: null,
		isPending: false,
		variables: undefined,
		isError: false,
		isIdle: true,
		isSuccess: false,
		isPaused: false,
		status: "idle",
		submit: undefined,
		context: undefined,
		failureCount: 0,
		failureReason: null,
		mutateAsync: vi.fn(),
		onMutate: undefined,
		onError: undefined,
		onSettled: undefined,
		onSuccess: undefined,
	};
}

vi.mock("../hooks", async () => {
	const actual = await vi.importActual<typeof import("../hooks")>("../hooks");
	return {
		...actual,
		useCreateStrategy: vi.fn(() => ({
			mutate: vi.fn(),
			reset: vi.fn(),
			data: undefined,
			error: null,
			isPending: false,
		})),
	};
});

const CATALOG = [
	{
		template_id: "stock_selection",
		display_name: "股票多因子选股",
		asset_class: "stock",
		description: "",
		universe: "csi_a_share",
		benchmark: "000300.SH",
		default_frequency: "M",
		required_datasets: [],
		param_constraints: [],
	},
	{
		template_id: "etf_rotation",
		display_name: "ETF 轮动",
		asset_class: "etf",
		description: "",
		universe: "csi_etf_broad",
		benchmark: "000300.SH",
		default_frequency: "M",
		required_datasets: [],
		param_constraints: [],
	},
];

function renderOverlays() {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return render(
		<StrategyListOverlays open="create" onClose={() => {}} selected={null} detail={undefined} detailLoading={false} />,
		{
			wrapper: ({ children }: { children: ReactNode }) => (
				<QueryClientProvider client={client}>{children}</QueryClientProvider>
			),
		},
	);
}

beforeEach(() => {
	server.use(http.get("/api/v1/strategies/templates", () => HttpResponse.json({ data: CATALOG })));
	vi.mocked(useCreateStrategy).mockReturnValue(mockMutationState() as unknown as ReturnType<typeof useCreateStrategy>);
});

describe("StrategyDraftSheet template selection", () => {
	it("offers the three committed research templates with readable labels", async () => {
		renderOverlays();

		await screen.findByText("股票多因子选股 · stock_selection");
		const select = screen.getByTestId("strategy-template-select");
		const options = Array.from(select.querySelectorAll("option")).map((option) => option.textContent);
		expect(options).toContain("股票多因子选股 · stock_selection");
		expect(options).toContain("ETF 轮动 · etf_rotation");
		// 无自由文本模板：占位项要求显式选择。
		expect(select).toHaveValue("");
		expect(select).toBeRequired();
	});

	it("syncs asset class and universe defaults from the chosen template", async () => {
		renderOverlays();
		const user = userEvent.setup();

		await screen.findByText("股票多因子选股 · stock_selection");
		const select = screen.getByTestId("strategy-template-select");
		await user.selectOptions(select, "stock_selection");

		expect(screen.getByLabelText("资产类型")).toHaveValue("stock");
		expect(screen.getByLabelText("Universe")).toHaveValue("");
		// 用户仍可显式覆盖资产类别与池。
		expect(screen.getByLabelText("资产类型")).toBeEnabled();
	});
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";
import { FactorListPage } from "./factor-list-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			children,
			to,
			params,
			className,
		}: {
			readonly children: ReactNode;
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
			readonly className?: string;
		}) => (
			<a href={params?.id ? to.replace("$id", params.id) : to} className={className}>
				{children}
			</a>
		),
	};
});

const FACTORS = [
	{
		factor_id: "momentum_1m",
		resolved_payload: {
			lanes: ["stock", "etf"],
			lookback: { value: 20, unit: "trading_days" },
			pit_requirement: "known_at",
		},
	},
	{
		factor_id: "quality_roe",
		resolved_payload: {
			lanes: ["stock"],
			lookback: { value: 1, unit: "quarters" },
			pit_requirement: "announcement_known_at",
		},
	},
	{
		factor_id: "etf_liquidity",
		resolved_payload: {
			lanes: ["etf"],
			lookback: { value: 5, unit: "trading_days" },
			pit_requirement: "known_at",
		},
	},
] as const;

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("FactorListPage live catalog", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(...researchHandlers);
		server.use(http.get("/api/v1/research/factors", () => HttpResponse.json({ data: FACTORS })));
	});

	it("renders the governed factor catalog and fails closed when diagnostics are not scoped", async () => {
		render(<FactorListPage />, { wrapper: createWrapper() });

		await expect(screen.findAllByText("momentum_1m")).resolves.not.toHaveLength(0);
		expect(screen.getByText("quality_roe")).toBeInTheDocument();
		expect(screen.queryByText("北向资金因子")).not.toBeInTheDocument();
		expect(screen.getAllByText("未评估").length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("未绑定 snapshot、时间窗口与 registry hash")).toBeInTheDocument();
		expect(screen.queryByText("0.000")).not.toBeInTheDocument();
	});

	it("filters the live catalog by search and lane", async () => {
		const user = userEvent.setup();
		render(<FactorListPage />, { wrapper: createWrapper() });
		await screen.findAllByText("momentum_1m");

		await user.type(screen.getByRole("searchbox", { name: "搜索因子" }), "quality");
		expect(screen.getAllByText("quality_roe").length).toBeGreaterThanOrEqual(1);
		expect(screen.queryByText("momentum_1m")).not.toBeInTheDocument();

		await user.clear(screen.getByRole("searchbox", { name: "搜索因子" }));
		await user.click(screen.getByRole("button", { name: "仅 ETF" }));
		expect(screen.getByText("etf_liquidity")).toBeInTheDocument();
		expect(screen.queryByText("quality_roe")).not.toBeInTheDocument();
	});

	it("selects a factor and opens a catalog-level comparison without inventing correlation evidence", async () => {
		const user = userEvent.setup();
		render(<FactorListPage />, { wrapper: createWrapper() });
		await screen.findAllByText("momentum_1m");

		await user.click(screen.getByRole("button", { name: "查看 quality_roe" }));
		const detail = screen.getByRole("complementary", { name: "因子详情" });
		expect(within(detail).getByText("quality_roe")).toBeInTheDocument();

		await user.click(screen.getByRole("checkbox", { name: "将 momentum_1m 加入对比" }));
		await user.click(screen.getByRole("checkbox", { name: "将 quality_roe 加入对比" }));
		await user.click(screen.getByRole("button", { name: "因子对比 2" }));

		const dialog = screen.getByRole("dialog", { name: "因子对比" });
		expect(within(dialog).getByText("momentum_1m")).toBeInTheDocument();
		expect(within(dialog).getByText("quality_roe")).toBeInTheDocument();
		expect(within(dialog).getByText("相关性未计算")).toBeInTheDocument();
	});
});

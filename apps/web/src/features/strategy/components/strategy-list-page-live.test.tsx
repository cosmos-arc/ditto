import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { StrategyListPage } from "./strategy-list-page";

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

const SPEC = {
	strategy_id: "alpha_etf",
	name: "ETF Alpha",
	template: "etf_rotation",
	universe: "csi_etf_broad",
	asset_class: "etf",
	benchmark: "000300.SH",
	scorer: { method: "rank", params: {} },
	selector: { method: "top_k", params: { k: 5 } },
	execution: { frequency: "M", method: "calendar", default_order_type: "market" },
	constraints: [],
	params: {},
	signal_expressions: ["momentum_1m"],
	signal_weights: [1],
	param_constraints: [],
};

const STRATEGIES = [
	{
		strategy_id: "alpha_etf",
		name: "ETF Alpha",
		spec_json: SPEC,
		version: 3,
		status: "published",
		created_at: "2026-08-01T09:00:00Z",
		tags: ["etf", "alpha"],
	},
	{
		strategy_id: "quality_stock",
		name: "Quality Stock",
		spec_json: { ...SPEC, strategy_id: "quality_stock", name: "Quality Stock", asset_class: "stock" },
		version: 1,
		status: "draft",
		created_at: "2026-08-02T09:00:00Z",
		tags: ["stock", "quality"],
	},
] as const;

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("StrategyListPage governed catalog", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/strategies", () => HttpResponse.json({ data: STRATEGIES })),
			http.get("/api/v1/strategies/:id", ({ params }) => {
				const item = STRATEGIES.find((strategy) => strategy.strategy_id === params.id) ?? STRATEGIES[0];
				return HttpResponse.json({ data: item });
			}),
		);
	});

	it("renders and filters live governance metadata without inventing performance", async () => {
		const user = userEvent.setup();
		render(<StrategyListPage />, { wrapper: createWrapper() });

		const table = await screen.findByRole("table", { name: "策略目录" });
		expect(within(table).getByText("ETF Alpha")).toBeInTheDocument();
		expect(within(table).getByText("Quality Stock")).toBeInTheDocument();
		expect(screen.getAllByText("未评估").length).toBeGreaterThanOrEqual(2);

		await user.type(screen.getByRole("searchbox", { name: "搜索策略" }), "quality");
		expect(within(table).getByText("Quality Stock")).toBeInTheDocument();
		expect(within(table).queryByText("ETF Alpha")).not.toBeInTheDocument();

		await user.clear(screen.getByRole("searchbox", { name: "搜索策略" }));
		await user.click(screen.getByRole("button", { name: "仅草稿" }));
		expect(within(table).getByText("Quality Stock")).toBeInTheDocument();
		expect(within(table).queryByText("ETF Alpha")).not.toBeInTheDocument();
	});

	it("clones the selected server strategy with an idempotent create command", async () => {
		let idempotencyKey = "";
		let payload: Record<string, unknown> = {};
		server.use(
			http.post("/api/v1/strategies", async ({ request }) => {
				idempotencyKey = request.headers.get("Idempotency-Key") ?? "";
				payload = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({
					data: {
						...STRATEGIES[0],
						strategy_id: String(payload.strategy_id),
						name: String(payload.name),
						version: 1,
						status: "draft",
					},
				});
			}),
		);

		const user = userEvent.setup();
		render(<StrategyListPage />, { wrapper: createWrapper() });
		await screen.findByRole("table", { name: "策略目录" });

		await user.click(screen.getByRole("button", { name: "克隆 alpha_etf" }));
		const sheet = screen.getByRole("dialog", { name: "克隆策略" });
		await user.clear(within(sheet).getByRole("textbox", { name: "新策略 ID" }));
		await user.type(within(sheet).getByRole("textbox", { name: "新策略 ID" }), "alpha_etf_copy");
		await user.click(within(sheet).getByRole("button", { name: "创建草稿" }));

		await expect(within(sheet).findByText("已创建草稿 alpha_etf_copy")).resolves.toBeInTheDocument();
		expect(idempotencyKey).toMatch(/^strategy-create:/);
		expect(payload.strategy_id).toBe("alpha_etf_copy");
		expect((payload.spec_json as Record<string, unknown>).strategy_id).toBe("alpha_etf_copy");
		expect(within(sheet).getByRole("link", { name: "打开 Strategy Studio" })).toHaveAttribute(
			"href",
			"/research/strategies/alpha_etf_copy/studio",
		);
	});

	it("routes destructive intent to governed deprecation instead of issuing DELETE", async () => {
		let deleteCalls = 0;
		server.use(
			http.delete("/api/v1/strategies/:id", () => {
				deleteCalls += 1;
				return new HttpResponse(null, { status: 204 });
			}),
		);

		const user = userEvent.setup();
		render(<StrategyListPage />, { wrapper: createWrapper() });
		await screen.findByRole("table", { name: "策略目录" });
		await user.click(screen.getByRole("button", { name: "删除 alpha_etf" }));

		const dialog = screen.getByRole("alertdialog", { name: "删除策略" });
		expect(within(dialog).getByText(/append-only/)).toBeInTheDocument();
		expect(within(dialog).getByRole("link", { name: "前往版本治理" })).toHaveAttribute(
			"href",
			"/research/strategies/alpha_etf",
		);
		expect(deleteCalls).toBe(0);
	});
});

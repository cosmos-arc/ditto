import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { aiHandlers } from "@/mocks/handlers/ai";
import { systemHandlers } from "@/mocks/handlers/system";
import { server } from "@/mocks/server";
import { SystemAgentOpsPage } from "./agents-page";
import { SystemSettingsPage } from "./settings-page";
import { SystemPage } from "./system-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const queryClient = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...systemHandlers, ...aiHandlers);
});

describe("System route page contract handoffs", () => {
	it("live 模式使用 catalog 治理 API，而不是 prototype only 空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<SystemPage />, { wrapper: createWrapper() });

		expect(screen.queryByText("prototype only")).not.toBeInTheDocument();
		await expect(screen.findByText("Catalog assets")).resolves.toBeInTheDocument();
		await expect(screen.findAllByText("stock_daily")).resolves.not.toHaveLength(0);
		await expect(screen.findByText("Source health")).resolves.toBeInTheDocument();
		await expect(screen.findByText("Remediation backlog")).resolves.toBeInTheDocument();
	});

	it("covers SystemPage route composition", async () => {
		const user = userEvent.setup();
		render(<SystemPage />, { wrapper: createWrapper() });

		await expect(screen.findByRole("main", { name: "平台治理总览" })).resolves.toBeInTheDocument();
		await expect(screen.findByText("Fallback control")).resolves.toBeInTheDocument();
		await expect(screen.findByText("Promotion readiness")).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "任务详情" }));
		expect(screen.getByRole("dialog", { name: "任务详情" })).toHaveTextContent("Dataset");
	});

	it("catalog 为空时保持 fail-closed 空态", async () => {
		server.use(http.get("/api/v1/ingestion/catalog/assets", () => HttpResponse.json({ data: [] })));
		render(<SystemPage />, { wrapper: createWrapper() });

		await expect(screen.findByText(/尚无 catalog asset/)).resolves.toBeInTheDocument();
		expect(screen.queryByText("tushare")).not.toBeInTheDocument();
	});

	it("catalog API 失败时提供可重试错误态", async () => {
		server.use(
			http.get("/api/v1/ingestion/catalog/assets", () =>
				HttpResponse.json({ detail: "catalog unavailable" }, { status: 503 }),
			),
		);
		render(<SystemPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("Catalog API 不可用")).resolves.toBeInTheDocument();
		await expect(screen.findByRole("alert")).resolves.toHaveTextContent("catalog unavailable");
		expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
	});

	it("covers the governed SystemAgentOpsPage route composition", async () => {
		render(<SystemAgentOpsPage />, { wrapper: createWrapper() });

		expect(screen.getByRole("region", { name: "System Agent Ops" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Runs" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "新建 Run" })).toBeDisabled();
	});

	it("renders System Settings from server-reported runtime capabilities", async () => {
		server.use(
			http.get("/api/v1/status", () =>
				HttpResponse.json({
					status: "running",
					version: "runtime-build-42",
					environment: "production-cn",
					features: { data_collection: true, data_validation: true, backtest: true, trading: true },
					observability: { level: "INFO", structured: true },
				}),
			),
			http.get("/api/v1/agent/capabilities", () =>
				HttpResponse.json({
					data: {
						enabled: true,
						runtime_state: "available",
						provider: "fixture-provider",
						available_profiles: ["balanced", "quality"],
						default_profile: "balanced",
						degradation_reason: null,
						checked_at: "2026-08-30T07:40:00Z",
					},
				}),
			),
		);
		render(<SystemSettingsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("runtime-build-42")).resolves.toBeInTheDocument();
		expect(screen.getAllByText("production-cn")).not.toHaveLength(0);
		expect(screen.getByText("fixture-provider")).toBeInTheDocument();
		expect(screen.getByText("2 catalog assets")).toBeInTheDocument();
		expect(screen.queryByText("3 groups")).not.toBeInTheDocument();
		expect(screen.queryByText("Change Log")).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "测试券商" })).not.toBeInTheDocument();
		expect(screen.queryByText(/Broker connection/i)).not.toBeInTheDocument();
	});

	it("keeps System Settings partial failures and empty catalog explicit", async () => {
		server.use(
			http.get("/api/v1/status", () => HttpResponse.json({ detail: "status unavailable" }, { status: 503 })),
			http.get("/api/v1/ingestion/catalog/assets", () => HttpResponse.json({ data: [] })),
			http.get("/api/v1/agent/capabilities", () =>
				HttpResponse.json({
					data: {
						enabled: false,
						runtime_state: "degraded",
						provider: null,
						available_profiles: [],
						default_profile: null,
						degradation_reason: "provider configuration missing",
						checked_at: "2026-08-30T07:40:00Z",
					},
				}),
			),
		);
		render(<SystemSettingsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("status unavailable")).resolves.toBeInTheDocument();
		expect(screen.getByText(/Catalog 未报告任何资产/)).toBeInTheDocument();
		expect(screen.getByText("provider configuration missing")).toBeInTheDocument();
		expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(1);
	});
});

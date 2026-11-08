import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { StatusBar } from "./status-bar";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

const status = {
	status: "running",
	version: "0.1.0",
	product_version: "0.1.0",
	git_sha: "a".repeat(40),
	api_contract_version: "v1",
	api_contract_sha256: "b".repeat(64),
	environment: "development",
	features: { data_collection: true, data_validation: true, backtest: true, trading: true },
	observability: { level: "INFO", structured: true },
};

describe("StatusBar", () => {
	it("reports the last API check, disconnection and keyboard retry without fabricated latency", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(http.get("/api/v1/status", () => HttpResponse.json({ data: status })));
		const user = userEvent.setup();
		render(<StatusBar />, { wrapper: wrapper() });
		expect(screen.getByRole("status", { name: "系统状态" })).toHaveTextContent("正在检查 API");
		await expect(screen.findByText(/API 最近检查通过/)).resolves.toBeInTheDocument();
		expect(screen.queryByText(/LIVE|12ms|⌘K/)).not.toBeInTheDocument();
		server.use(http.get("/api/v1/status", () => HttpResponse.error()));
		await user.tab();
		expect(screen.getByRole("button", { name: "检查 API 连接" })).toHaveFocus();
		await user.keyboard("{Enter}");
		await expect(screen.findByText("API 连接失败")).resolves.toBeInTheDocument();
		expect(screen.queryByText(/最近检查通过/)).not.toBeInTheDocument();
		server.use(http.get("/api/v1/status", () => HttpResponse.json({ data: status })));
		await user.click(screen.getByRole("button", { name: "检查 API 连接" }));
		await expect(screen.findByText(/API 最近检查通过/)).resolves.toBeInTheDocument();
	});

	it("identifies fixture mode without claiming an API connection", () => {
		render(<StatusBar spanRail />, { wrapper: wrapper() });
		expect(screen.getByRole("status", { name: "系统状态" })).toHaveTextContent("样例模式 · 未检查 API");
		expect(screen.queryByRole("button", { name: "检查 API 连接" })).not.toBeInTheDocument();
	});

	it("reports an incompatible API separately from a disconnected API", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/status", () => HttpResponse.json({ data: { ...status, api_contract_version: "v2" } })),
		);
		render(<StatusBar reserveRightRail />, { wrapper: wrapper() });
		await expect(screen.findByText("API 兼容性检查未通过")).resolves.toBeInTheDocument();
		expect(screen.queryByText("API 连接失败")).not.toBeInTheDocument();
	});
});

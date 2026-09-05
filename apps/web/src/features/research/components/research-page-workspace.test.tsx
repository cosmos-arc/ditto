import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";
import { ResearchPage } from "./research-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			children,
			to,
			className,
		}: {
			readonly children: ReactNode;
			readonly to: string;
			readonly className?: string;
		}) => (
			<a href={to} className={className}>
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
] as const;

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("ResearchPage factor-monitor workspace", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(...researchHandlers);
		server.use(http.get("/api/v1/research/factors", () => HttpResponse.json({ data: FACTORS })));
	});

	it("uses the governed factor catalog as the primary workspace and fails closed without diagnostics scope", async () => {
		render(<ResearchPage />, { wrapper: createWrapper() });

		const monitor = await screen.findByRole("region", { name: "因子监控" });
		await expect(within(monitor).findByText("momentum_1m")).resolves.toBeInTheDocument();
		expect(within(monitor).getByText("quality_roe")).toBeInTheDocument();
		expect(within(monitor).getAllByText("未评估").length).toBeGreaterThanOrEqual(2);
		expect(screen.getByText("请选择实验与折叠窗口后读取诊断证据")).toBeInTheDocument();
		expect(screen.queryByText("0.000")).not.toBeInTheDocument();
	});

	it("keeps the approved analytical slots and exposes the research action sheets", async () => {
		const user = userEvent.setup();
		render(<ResearchPage />, { wrapper: createWrapper() });

		await screen.findByRole("region", { name: "因子监控" });
		expect(document.querySelector("[data-slot='strip']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='main']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='activity']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='analysis']")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "新建实验" }));
		expect(screen.getByRole("dialog", { name: "新建实验" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "进入实验配置" })).toHaveAttribute("href", "/research/experiments/new");

		await user.click(screen.getByRole("button", { name: "关闭新建实验" }));
		expect(screen.queryByRole("dialog", { name: "新建实验" })).not.toBeInTheDocument();
	});
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { FactorPage } from "./factor-page";

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
		useParams: () => ({ id: "momentum_1m" }),
	};
});

const SCOPE: FactorDiagnosticsScope = {
	snapshotId: "snapshot-r3",
	startDate: "2024-01-01",
	endDate: "2024-12-31",
	registryHash: "f".repeat(64),
};

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("FactorPage governed workspace", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_USE_MOCK", "false");
	});

	it("fails closed before the complete immutable diagnostics scope is bound", () => {
		let requests = 0;
		server.use(
			http.get("/api/v1/research/factors/:factorId/diagnostics", () => {
				requests += 1;
				return HttpResponse.json({ data: {} });
			}),
		);

		render(<FactorPage />, { wrapper: createWrapper() });

		expect(screen.getByText("诊断范围未绑定")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "诊断详情" })).toBeDisabled();
		expect(screen.getByRole("region", { name: "诊断工作区" })).toHaveTextContent("等待不可变诊断");
		expect(screen.getByRole("complementary", { name: "证据要求" })).toHaveTextContent("Snapshot ID");
		expect(screen.queryByText("0.000")).not.toBeInTheDocument();
		expect(requests).toBe(0);
	});

	it("opens workflow handoffs without claiming that the downstream object was created", async () => {
		const user = userEvent.setup();
		render(<FactorPage />, { wrapper: createWrapper() });

		await user.click(screen.getByRole("button", { name: "加入回测" }));
		let dialog = screen.getByRole("dialog", { name: "加入回测" });
		expect(within(dialog).getByRole("link", { name: "前往回测列表" })).toHaveAttribute("href", "/research/backtests");
		expect(within(dialog).getByText(/尚未创建回测/)).toBeInTheDocument();
		await user.click(within(dialog).getByRole("button", { name: "Close" }));

		await user.click(screen.getByRole("button", { name: "加入实验" }));
		dialog = screen.getByRole("dialog", { name: "加入实验" });
		expect(within(dialog).getByRole("link", { name: "进入实验配置" })).toHaveAttribute(
			"href",
			"/research/experiments/new",
		);
	});

	it("shows server-backed diagnostics in detail and keeps AI analysis evidence governed", async () => {
		server.use(
			http.get("/api/v1/research/factors/:factorId/diagnostics", () =>
				HttpResponse.json({
					data: {
						factor_id: "momentum_1m",
						snapshot_id: SCOPE.snapshotId,
						snapshot_hash: "a".repeat(64),
						registry_hash: SCOPE.registryHash,
						start_date: SCOPE.startDate,
						end_date: SCOPE.endDate,
						provenance: { dataset_id: "stock_daily" },
						metrics: { rank_ic: 0.08 },
						artifact_id: "factor-diagnostic-1",
						content_hash: "c".repeat(64),
					},
				}),
			),
		);

		const user = userEvent.setup();
		render(<FactorPage initialScope={SCOPE} />, { wrapper: createWrapper() });
		await screen.findByText("factor-diagnostic-1");

		await user.click(screen.getByRole("button", { name: "诊断详情" }));
		const detail = screen.getByRole("dialog", { name: "诊断详情" });
		expect(within(detail).getByText("factor-diagnostic-1")).toBeInTheDocument();

		await user.click(within(detail).getByRole("button", { name: "Close" }));
		await user.click(screen.getByRole("button", { name: "AI 解读" }));
		const aiDrawer = screen.getByRole("dialog", { name: "AI 解读" });
		expect(within(aiDrawer).getByText(/不会生成未经服务端证据支持的结论/)).toBeInTheDocument();
		expect(within(aiDrawer).getByRole("link", { name: "请求证据分析" })).toBeInTheDocument();
	});
});

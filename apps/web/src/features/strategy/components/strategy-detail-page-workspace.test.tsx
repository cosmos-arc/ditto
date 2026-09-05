import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { server } from "@/mocks/server";
import { StrategyDetailPage } from "./strategy-detail-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useParams: () => ({ id: "seed_etf_industry_rotation" }),
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

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={
				new QueryClient({
					defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } },
				})
			}
		>
			{children}
		</QueryClientProvider>
	);
}

const renderNoGovernanceActions = () => null;

describe("StrategyDetailPage governed workspace", () => {
	beforeEach(() => server.use(...strategyHandlers));

	it("renders live strategy identity and fails closed on unbound performance evidence", async () => {
		render(<StrategyDetailPage renderGovernanceActions={renderNoGovernanceActions} />, { wrapper });

		const workspace = await screen.findByRole("region", { name: "策略详情工作区" });
		await expect(within(workspace).findByText("ETF 行业轮动")).resolves.toBeInTheDocument();
		expect(screen.getAllByText("未评估").length).toBeGreaterThanOrEqual(4);
		expect(screen.getByRole("link", { name: "编辑策略" })).toHaveAttribute(
			"href",
			"/research/strategies/seed_etf_industry_rotation/studio",
		);
		expect(screen.queryByText("1.82")).not.toBeInTheDocument();
	});

	it("forwards governance composition through the versions renderer", async () => {
		const user = userEvent.setup();
		render(
			<StrategyDetailPage
				renderGovernanceActions={({ version }) => <span>governed strategy v{version.version}</span>}
			/>,
			{ wrapper },
		);

		await user.click(await screen.findByRole("tab", { name: "版本" }));
		await expect(screen.findByText("governed strategy v4")).resolves.toBeInTheDocument();
	});

	it("hands backtest submission to exact experiment planning without creating a run", async () => {
		let experimentWrites = 0;
		server.use(
			http.post("/api/v1/research/experiments", () => {
				experimentWrites += 1;
				return HttpResponse.json({ data: {} });
			}),
		);
		const user = userEvent.setup();
		render(<StrategyDetailPage renderGovernanceActions={renderNoGovernanceActions} />, { wrapper });

		await user.click(await screen.findByRole("button", { name: "提交回测" }));
		const sheet = screen.getByRole("dialog", { name: "提交回测" });
		expect(within(sheet).getByText("seed_etf_industry_rotation")).toBeInTheDocument();
		expect(within(sheet).getByText("v3")).toBeInTheDocument();
		expect(within(sheet).getByRole("link", { name: "打开实验创建器" })).toHaveAttribute(
			"href",
			"/research/experiments/new",
		);
		expect(experimentWrites).toBe(0);
	});

	it("deprecates the current version through the audited governance command", async () => {
		const command: { key: string; payload: Record<string, unknown> | null } = { key: "", payload: null };
		server.use(
			http.post("/api/v1/strategies/:id/versions/:version/deprecate", async ({ request }) => {
				command.key = request.headers.get("Idempotency-Key") ?? "";
				command.payload = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({
					data: {
						strategy_id: "seed_etf_industry_rotation",
						version: 3,
						state: "deprecated",
						review_outcome: "approved",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<StrategyDetailPage renderGovernanceActions={renderNoGovernanceActions} />, { wrapper });

		await user.click(await screen.findByRole("button", { name: "弃用策略" }));
		const sheet = screen.getByRole("dialog", { name: "弃用版本" });
		await user.type(within(sheet).getByRole("textbox", { name: "执行者" }), "research-owner");
		await user.type(within(sheet).getByRole("textbox", { name: "原因" }), "replace with reviewed v4");
		await user.click(within(sheet).getByRole("button", { name: "确认弃用" }));

		await vi.waitFor(() => expect(command.payload).not.toBeNull());
		expect(command.key).toMatch(/^strategy-governance-/);
		expect(command.payload).toEqual({ actor: "research-owner", reason: "replace with reviewed v4" });
	});

	it("keeps copy and rollback explicit without inventing a rollback mutation", async () => {
		let rollbackWrites = 0;
		server.use(
			http.post("/api/v1/strategies/:id/rollback", () => {
				rollbackWrites += 1;
				return HttpResponse.json({ data: {} });
			}),
		);
		const user = userEvent.setup();
		render(<StrategyDetailPage renderGovernanceActions={renderNoGovernanceActions} />, { wrapper });

		await user.click(await screen.findByRole("button", { name: "复制策略" }));
		expect(screen.getByRole("dialog", { name: "克隆策略" })).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "Close" }));

		await user.click(screen.getByRole("button", { name: "版本回滚" }));
		const rollback = screen.getByRole("dialog", { name: "版本回滚" });
		expect(within(rollback).getByText(/active pointer/)).toBeInTheDocument();
		await user.click(within(rollback).getByRole("button", { name: "查看版本治理" }));
		expect(screen.getByRole("tab", { name: "版本" })).toHaveAttribute("data-state", "active");
		expect(rollbackWrites).toBe(0);
	});
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { mockExperimentSummaryList } from "@/mocks/fixtures/experiment-live";
import { server } from "@/mocks/server";
import { ExperimentListPage } from "./experiment-list-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			to,
			params,
			children,
			className,
		}: {
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
			readonly children: ReactNode;
			readonly className?: string;
		}) => (
			<a href={params?.["id"] ? to.replace("$id", params["id"]) : to} className={className}>
				{children}
			</a>
		),
	};
});

function renderPage(): void {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	render(
		<QueryClientProvider client={queryClient}>
			<ExperimentListPage />
		</QueryClientProvider>,
	);
}

describe("ExperimentListPage governed catalog", () => {
	it("renders the live queue and exact selected revision in a usable catalog workspace", async () => {
		renderPage();

		const catalog = await screen.findByRole("region", { name: "受控实验目录" });
		expect(within(catalog).getByRole("searchbox", { name: "搜索实验" })).toBeInTheDocument();
		expect(within(catalog).getByRole("link", { name: "创建实验" })).toHaveAttribute(
			"href",
			"/research/experiments/new",
		);
		expect(await within(catalog).findAllByText("exp-1042")).not.toHaveLength(0);
		const detail = within(catalog).getByRole("complementary", { name: "实验详情" });
		expect(within(detail).getByText("revision 3")).toBeInTheDocument();
		expect(within(detail).getByText("candidate_evaluation")).toBeInTheDocument();
		expect(within(detail).getByText("未报告失败")).toBeInTheDocument();
	});

	it("filters the live list and opens the selected experiment drawer", async () => {
		const user = userEvent.setup();
		renderPage();

		const search = await screen.findByRole("searchbox", { name: "搜索实验" });
		await user.type(search, "1035");
		expect(screen.queryByText("exp-1042")).not.toBeInTheDocument();
		expect(screen.getAllByText("exp-1035")).not.toHaveLength(0);
		await user.click(screen.getByRole("button", { name: "选择 exp-1035" }));
		await user.click(screen.getByRole("button", { name: "查看 exp-1035 详情" }));

		const drawer = await screen.findByRole("dialog", { name: "实验 exp-1035 详情" });
		expect(within(drawer).getByText("finalized")).toBeInTheDocument();
		expect(within(drawer).getByRole("link", { name: "打开实验工作台" })).toHaveAttribute(
			"href",
			"/research/experiments/exp-1035",
		);
	});

	it("shows a typed retry path instead of falling back to prototype data", async () => {
		const user = userEvent.setup();
		let calls = 0;
		server.use(
			http.get("/api/v1/research/experiments", () => {
				calls += 1;
				return calls === 1
					? HttpResponse.json(
							{ detail: "catalog unavailable", error_code: "EXPERIMENT_CATALOG_UNAVAILABLE" },
							{ status: 503 },
						)
					: HttpResponse.json({ data: mockExperimentSummaryList });
			}),
		);
		renderPage();

		expect(await screen.findByText(/503 EXPERIMENT_CATALOG_UNAVAILABLE/)).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "重试实验目录" }));
		expect(await screen.findAllByText("exp-1042")).not.toHaveLength(0);
		expect(calls).toBe(2);
	});
});

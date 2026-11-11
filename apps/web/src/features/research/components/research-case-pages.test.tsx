import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { researchCaseFixture, selectionRunFixtures } from "@/mocks/fixtures/selection";
import { server } from "@/mocks/server";
import { ResearchCaseDetailPage, ResearchCaseListPage } from "./research-case-pages";

function wrapper() {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

const summaryFixture = {
	as_of: researchCaseFixture.as_of,
	asset_kind: researchCaseFixture.asset_kind,
	candidate_count: researchCaseFixture.candidate_instrument_ids.length,
	case_id: researchCaseFixture.case_id,
	objective: researchCaseFixture.objective,
	selection_run_id: researchCaseFixture.selection_run_id,
	selection_status: researchCaseFixture.selection_status,
};

beforeEach(() => {
	server.use(
		http.get("/api/v1/selections/research-cases", () => HttpResponse.json({ data: [summaryFixture] })),
		// msw 路径模式会把 :sha256: 当参数语法，用参数形式按身份精确匹配。
		http.get("/api/v1/selections/research-cases/:caseId", ({ params }) =>
			decodeURIComponent(String(params["caseId"])) === researchCaseFixture.case_id
				? HttpResponse.json({ data: researchCaseFixture })
				: HttpResponse.json({ detail: "research case not found" }, { status: 404 }),
		),
		http.get("/api/v1/selections/runs/:runId", ({ params }) =>
			decodeURIComponent(String(params["runId"])) === selectionRunFixtures[0].run_id
				? HttpResponse.json({ data: selectionRunFixtures[0] })
				: HttpResponse.json({ detail: "not found" }, { status: 404 }),
		),
	);
});

describe("ResearchCaseListPage", () => {
	it("lists persisted handoff cases with objective, run, and candidate scope", async () => {
		render(<ResearchCaseListPage />, { wrapper: wrapper() });

		const link = await screen.findByRole("link", { name: /验证动量因子持续性/ });
		expect(link).toHaveAttribute("href", `/research/cases/${encodeURIComponent(researchCaseFixture.case_id)}`);
		const row = link.closest("tr");
		expect(row).not.toBeNull();
		expect(row).toHaveTextContent("2 只候选");
		expect(row).toHaveTextContent(/2026/);
		// 计数按数量单复数化（视觉门 V3）。
		expect(screen.getByText("1 case")).toBeInTheDocument();
	});

	it("pluralizes the counter beyond one case", async () => {
		server.use(
			http.get("/api/v1/selections/research-cases", () =>
				HttpResponse.json({
					data: [summaryFixture, { ...summaryFixture, case_id: `research-case:sha256:${"0".repeat(64)}` }],
				}),
			),
		);
		render(<ResearchCaseListPage />, { wrapper: wrapper() });

		await expect(screen.findByText("2 cases")).resolves.toBeInTheDocument();
	});

	it("keeps an honest empty state pointing at the selection workspace", async () => {
		server.use(http.get("/api/v1/selections/research-cases", () => HttpResponse.json({ data: [] })));
		render(<ResearchCaseListPage />, { wrapper: wrapper() });

		await expect(screen.findByText(/尚无研究用例/)).resolves.toBeInTheDocument();
		expect(screen.getByRole("link", { name: "前往 Selection Workspace" })).toHaveAttribute("href", "/markets/screener");
	});

	it("surfaces a readable error state with retry", async () => {
		server.use(
			http.get("/api/v1/selections/research-cases", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
		);
		render(<ResearchCaseListPage />, { wrapper: wrapper() });

		await expect(screen.findByRole("button", { name: "重试" })).resolves.toBeVisible();
	});
});

describe("ResearchCaseDetailPage", () => {
	it("reopens the case with objective, dates, lineage, and the selected candidates", async () => {
		const user = userEvent.setup();
		render(<ResearchCaseDetailPage caseId={researchCaseFixture.case_id} />, {
			wrapper: wrapper(),
		});

		await expect(screen.findByText(researchCaseFixture.objective)).resolves.toBeInTheDocument();
		const identity = screen.getByLabelText("用例身份");
		expect(within(identity).getByText(researchCaseFixture.case_id)).toBeInTheDocument();

		// 时间身份三要素可见（对象、日期、来源随交接保留）。
		const temporal = screen.getByLabelText("时间身份");
		expect(temporal).toHaveTextContent("2026/8/31");
		expect(temporal).toHaveTextContent("knowledge cutoff");
		expect(temporal).toHaveTextContent("publication cutoff");

		// 候选名单用来源 run 的名字与排名解释选择。
		const roster = await screen.findByLabelText("候选名单");
		expect(within(roster).getByText("贵州茅台")).toBeInTheDocument();
		expect(within(roster).getByText("宁德时代")).toBeInTheDocument();
		expect(roster).toHaveTextContent("#1");

		// 返回筛选：带固定运行身份重开（返回恢复筛选上下文）；入口在页头
		// 区域首屏可达（视觉门末族：底部入口随页长被推出视口折叠线），
		// 与候选下钻同链接语言，全页仅此一处权威返回动作。
		const backToSelection = screen.getByRole("link", { name: "← 回到该运行的筛选工作面" });
		expect(backToSelection.closest('[data-info-unit="research-case-header"]')).not.toBeNull();
		expect(backToSelection.className).toContain("text-(--color-accent)");
		expect(backToSelection.className).toContain("hover:underline");
		expect(backToSelection).toHaveAttribute(
			"href",
			`/markets/screener?run=${encodeURIComponent(selectionRunFixtures[0].run_id)}&spec=a-share-stock-discovery`,
		);
		await user.click(backToSelection);
	});

	it("keeps candidate drilldown anchored to the case's decision date", async () => {
		render(<ResearchCaseDetailPage caseId={researchCaseFixture.case_id} />, {
			wrapper: wrapper(),
		});

		const candidate = await screen.findByRole("link", { name: "贵州茅台" });
		expect(candidate).toHaveAttribute(
			"href",
			`/instruments/600519?tab=chart&observeDate=2026-08-31&selectionRunId=${encodeURIComponent(selectionRunFixtures[0].run_id)}`,
		);
		// 下钻可供性（视觉门 V2）：强调色 + hover 下划线，与域内比较入口同语言。
		expect(candidate.className).toContain("text-(--color-accent)");
		expect(candidate.className).toContain("hover:underline");
		// 观察日入口（视觉门 V2'）同样可辨认可点：指向首席选的观察日锚定图表。
		const observeEntry = screen.getByRole("link", { name: "按观察日 2026-08-31 打开首席选图表" });
		expect(observeEntry).toHaveAttribute(
			"href",
			`/instruments/600519?tab=chart&observeDate=2026-08-31&selectionRunId=${encodeURIComponent(selectionRunFixtures[0].run_id)}`,
		);
		expect(observeEntry.className).toContain("text-(--color-accent)");
		expect(observeEntry.className).toContain("hover:underline");
	});

	it("explains a missing case instead of rendering a broken page", async () => {
		server.use(
			http.get("/api/v1/selections/research-cases/:caseId", () =>
				HttpResponse.json({ detail: "research case not found" }, { status: 404 }),
			),
		);
		render(<ResearchCaseDetailPage caseId="research-case:sha256:not-there" />, {
			wrapper: wrapper(),
		});

		await expect(screen.findByText(/未找到该研究用例/)).resolves.toBeInTheDocument();
	});
});

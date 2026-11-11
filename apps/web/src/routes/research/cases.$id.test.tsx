import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { researchCaseFixture } from "@/mocks/fixtures/selection";
import { server } from "@/mocks/server";
import { routeTree } from "@/routeTree.gen";

function renderRoute(path: string): void {
	const history = createMemoryHistory({ initialEntries: [path] });
	const router = createRouter({ routeTree, history });
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false } },
	});
	const wrapper = ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
	render(<RouterProvider router={router} />, { wrapper });
}

beforeEach(() => {
	server.use(
		http.get("/api/v1/selections/research-cases/:caseId", () =>
			HttpResponse.json({ detail: "research case not found" }, { status: 404 }),
		),
	);
});

describe("research case detail route", () => {
	it("decodes the path id exactly once and requests it verbatim", async () => {
		let requested: string | undefined;
		server.use(
			http.get("/api/v1/selections/research-cases/:caseId", ({ params }) => {
				requested = String(params["caseId"]);
				return HttpResponse.json({ data: { ...researchCaseFixture, case_id: requested } }, { status: 200 });
			}),
		);
		// URL 段 `case%2520id`：useParams 解码一次得 `case%20id`；组件必须
		// 原样上送（旧实现再解一次会把 %20 变成空格）。
		renderRoute("/research/cases/case%2520id");

		expect(await screen.findByText("case%20id")).toBeInTheDocument();
		expect(requested).toBe("case%20id");
	});
});

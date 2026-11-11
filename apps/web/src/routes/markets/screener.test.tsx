import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { selectionReceiptFixture, selectionRunFixtures } from "@/mocks/fixtures/selection";
import { server } from "@/mocks/server";
import { routeTree } from "@/routeTree.gen";

type ScreenerRouter = ReturnType<typeof createRouter<typeof routeTree>>;

function renderRoute(path: string): { readonly router: ScreenerRouter } {
	const history = createMemoryHistory({ initialEntries: [path] });
	const router = createRouter({ routeTree, history });
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	render(
		<QueryClientProvider client={client}>
			<RouterProvider router={router} />
		</QueryClientProvider>,
	);
	return { router };
}

beforeEach(() => {
	server.use(
		http.get("/api/v1/selections/runs", ({ request }) => {
			const specId = new URL(request.url).searchParams.get("spec_id");
			return HttpResponse.json({
				data: selectionRunFixtures.filter((run) => run.spec_id === specId),
			});
		}),
		http.get("/api/v1/selections/runs/:runId", ({ params }) => {
			const run = selectionRunFixtures.find((item) => item.run_id === params["runId"]);
			return run ? HttpResponse.json({ data: run }) : HttpResponse.json({ detail: "not found" }, { status: 404 });
		}),
	);
});

describe("screener route search contract", () => {
	it("keeps both spec and run in the URL when one action updates them in the same tick", async () => {
		const user = userEvent.setup();
		// URL 初始 spec=A；服务端创建的固定运行属于另一条 spec（B）。
		const created = {
			...selectionReceiptFixture,
			selection_run: {
				...selectionReceiptFixture.selection_run,
				spec_id: "spec-created-b",
				run_id: `selection-run:sha256:${"7".repeat(64)}`,
			},
		};
		server.use(http.post("/api/v1/selections/runs", () => HttpResponse.json({ data: created }, { status: 201 })));
		const { router } = renderRoute("/markets/screener?spec=spec-alpha-a");
		await screen.findByRole("button", { name: "创建运行" });

		await user.click(screen.getByRole("button", { name: "创建运行" }));

		// 同 tick 的 spec+run 双导航不能互相丢弃参数（旧实现的闭包 search
		// 让第二次导航把第一次写入的 spec 覆盖回旧值）。
		await expect.poll(() => router.state.location.search.spec).toBe("spec-created-b");
		expect(router.state.location.search.run).toBe(created.selection_run.run_id);
	});
});

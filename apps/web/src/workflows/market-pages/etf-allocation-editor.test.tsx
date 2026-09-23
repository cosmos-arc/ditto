import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, expect, it } from "vitest";
import type { ETFCandidate } from "@/features/instruments";
import { server } from "@/mocks/server";
import { ETFAllocationEditor } from "./etf-allocation-editor";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

const candidate: ETFCandidate = {
	instrumentId: 1,
	name: "沪深300 ETF",
	ticker: "510300",
	exchange: "SSE",
	isActiveCurrent: true,
	fields: {},
};

afterEach(() => window.history.replaceState(null, "", "/"));

it("retries one save with the same identity and restores the saved version", async () => {
	const user = userEvent.setup();
	const attempts: Array<{ id: string; key: string }> = [];
	const reviewAttempts: Array<{ action: string; key: string }> = [];
	let stored: Record<string, unknown> | null = null;
	server.use(
		http.get("/api/v1/portfolio/etf-allocations/:id/versions", () =>
			HttpResponse.json({ data: stored ? [stored] : [] }),
		),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions", async ({ params, request }) => {
			attempts.push({ id: String(params["id"]), key: request.headers.get("Idempotency-Key") ?? "" });
			if (attempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			const body = (await request.json()) as Record<string, unknown>;
			stored = {
				version_id: "version-one",
				allocation_id: String(params["id"]),
				parent_version_id: null,
				asof: body["asof"],
				knowledge_cutoff: body["knowledge_cutoff"],
				source_snapshot_id: body["source_snapshot_id"],
				mode: "equal",
				weights: { "1": "0.80000000" },
				cash_weight: "0.2",
				max_position_weight: "1",
				tracking_exposure: { "000300.SH": "0.80000000" },
				reason: "broad exposure",
				rule_version: "etf-allocation-v1",
				paper_status: "research_only",
				created_at: "2026-09-01T09:00:00Z",
			};
			return HttpResponse.json({ data: stored }, { status: 201 });
		}),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/review", async ({ request }) => {
			const body = (await request.json()) as { action: string };
			reviewAttempts.push({ action: body.action, key: request.headers.get("Idempotency-Key") ?? "" });
			if (reviewAttempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			stored = { ...stored, paper_status: body.action === "submit" ? "review_pending" : "review_approved" };
			return HttpResponse.json({ data: stored });
		}),
	);
	const editor = (
		<ETFAllocationEditor
			items={[candidate]}
			asof="2026-09-01"
			cutoff="2026-09-01T09:00:00Z"
			cutoffInput="2026-09-01T17:00:00"
			snapshot="snapshot:recorded:etf"
		/>
	);
	const view = render(editor, { wrapper: wrapper() });
	await user.click(screen.getByRole("checkbox", { name: /沪深300 ETF/ }));
	await user.clear(screen.getByLabelText("单仓上限"));
	await user.type(screen.getByLabelText("单仓上限"), "1");
	await user.type(screen.getByLabelText("配置理由"), "broad exposure");
	await user.click(screen.getByRole("button", { name: "保存候选版本" }));
	await screen.findByRole("alert");
	view.unmount();
	const restored = render(editor, { wrapper: wrapper() });
	expect(screen.getByRole("checkbox", { name: /沪深300 ETF/ })).toBeChecked();
	expect(screen.getByLabelText("配置理由")).toHaveValue("broad exposure");
	await user.click(screen.getByRole("button", { name: "保存候选版本" }));
	await screen.findByText(/已保存 version-one/);
	expect(attempts).toHaveLength(2);
	expect(attempts[0]).toEqual(attempts[1]);
	expect(new URLSearchParams(window.location.search).get("etfVersion")).toBe("version-one");
	expect(screen.getByText(/审查批准只确认精确版本/)).toBeInTheDocument();
	await user.type(screen.getByLabelText("审查人"), "operator");
	await user.type(screen.getByLabelText("审查理由"), "checked");
	await user.click(screen.getByRole("button", { name: "提交审查" }));
	await screen.findByText(/审查失败/);
	restored.unmount();
	render(editor, { wrapper: wrapper() });
	await screen.findByRole("button", { name: "提交审查" });
	await user.type(screen.getByLabelText("审查人"), "operator");
	await user.type(screen.getByLabelText("审查理由"), "checked");
	await user.click(screen.getByRole("button", { name: "提交审查" }));
	await screen.findByRole("button", { name: "研究审查通过" });
	expect(reviewAttempts[0]).toEqual(reviewAttempts[1]);
	await user.click(screen.getByRole("button", { name: "研究审查通过" }));
	await screen.findByText(/· review_approved ·/);
	expect(reviewAttempts[2]?.action).toBe("approve");
});

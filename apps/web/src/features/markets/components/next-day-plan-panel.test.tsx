import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { NextDayPlanPanel } from "./next-day-plan-panel";

const entry = (instrumentId: number, ticker: string) => ({
	asset_class: instrumentId === 510888 ? "etf" : "stock",
	exchange: "SSE",
	instrument_id: instrumentId,
	is_active: true,
	name: `标的${ticker}`,
	ticker,
});

const resolveEntry = async (instrumentId: number) => entry(instrumentId, String(instrumentId).slice(-6));

const storedPlan = {
	plan_id: "next-day-plan:sha256:first",
	observation_date: "2026-11-10",
	candidate_notes: [
		{ instrument_id: 600779, reason: "缩量回踩半年线" },
		{ instrument_id: 510888, reason: "跟随大盘缩量" },
	],
	next_day_plan: "次日开盘观察 600779 放量情况",
	created_at: "2026-11-10T15:05:00Z",
	schema_version: 1,
};

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

afterEach(() => window.history.replaceState(null, "", "/"));

function renderPanel(overrides: Record<string, unknown> = {}) {
	return render(
		<NextDayPlanPanel
			ids={[600779, 510888]}
			resolveEntry={resolveEntry}
			defaultObservationDate="2026-11-10"
			{...overrides}
		/>,
		{ wrapper: wrapper() },
	);
}

it("records candidate reasons and the next-day plan, then reopens the saved entry", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	let recorded = false;
	server.use(
		http.get("/api/v1/market/next-day-plans", () =>
			HttpResponse.json({
				data: recorded
					? [
							{
								plan_id: storedPlan.plan_id,
								observation_date: storedPlan.observation_date,
								created_at: storedPlan.created_at,
								candidate_count: storedPlan.candidate_notes.length,
								next_day_plan: storedPlan.next_day_plan,
							},
						]
					: [],
			}),
		),
		http.post("/api/v1/market/next-day-plans", async ({ request }) => {
			posted.push(await request.json());
			recorded = true;
			return HttpResponse.json({ data: storedPlan }, { status: 201 });
		}),
		http.get("/api/v1/market/next-day-plans/:id", ({ params }) => {
			expect(decodeURIComponent(String(params["id"]))).toBe(storedPlan.plan_id);
			return HttpResponse.json({ data: storedPlan });
		}),
	);
	renderPanel();
	// 观察日期默认取最近完整交易日锚点。
	expect(screen.getByLabelText("观察日期")).toHaveValue("2026-11-10");
	await user.click(await screen.findByRole("checkbox", { name: /标的600779/ }));
	await user.type(screen.getByLabelText("600779 候选理由"), "缩量回踩半年线");
	await user.type(screen.getByLabelText("次日计划"), "次日开盘观察 600779 放量情况");
	await user.click(screen.getByRole("button", { name: "保存理由与次日计划" }));
	await expect.poll(() => posted.length).toBeGreaterThanOrEqual(1);
	// 展开重开：原观察日期、候选（业务代码）与理由、计划原文。
	await user.click(await screen.findByRole("button", { name: /展开计划原文/ }));
	const entry6 = await screen.findByText(/600779：缩量回踩半年线/);
	expect(entry6).toBeVisible();
	expect(screen.getByText(/510888：跟随大盘缩量/)).toBeVisible();
	expect(screen.getAllByText(/观察日 2026-11-10/).length).toBeGreaterThan(0);
	expect(screen.getAllByText(/次日开盘观察 600779 放量情况/).length).toBeGreaterThan(0);
});

it("shows the recorded list across reloads and keeps each original observation date", async () => {
	server.use(
		http.get("/api/v1/market/next-day-plans", () =>
			HttpResponse.json({
				data: [
					{
						plan_id: "next-day-plan:sha256:second",
						observation_date: "2026-11-11",
						created_at: "2026-11-11T15:05:00Z",
						candidate_count: 1,
						next_day_plan: "周四计划",
					},
					{
						plan_id: "next-day-plan:sha256:first",
						observation_date: "2026-11-10",
						created_at: "2026-11-10T15:05:00Z",
						candidate_count: 2,
						next_day_plan: "次日开盘观察 600779 放量情况",
					},
				],
			}),
		),
	);
	const view = renderPanel();
	const list = await screen.findByRole("region", { name: "已保存理由与次日计划" });
	await screen.findByText(/周四计划/);
	expect(list).toHaveTextContent("2026-11-11");
	expect(list).toHaveTextContent("2026-11-10");
	view.unmount();
	renderPanel();
	const reopenedList = await screen.findByRole("region", { name: "已保存理由与次日计划" });
	await screen.findByText(/周四计划/);
	expect(reopenedList).toHaveTextContent("2026-11-11");
	expect(reopenedList).toHaveTextContent("2026-11-10");
});

it("fails honestly on a rejected record and keeps the draft for retry", async () => {
	const user = userEvent.setup();
	const attempts: number[] = [];
	let failures = 1;
	server.use(
		http.get("/api/v1/market/next-day-plans", () => HttpResponse.json({ data: [] })),
		http.post("/api/v1/market/next-day-plans", () => {
			attempts.push(1);
			if (failures > 0) {
				failures -= 1;
				return HttpResponse.json(
					{ error: { code: "NEXT_DAY_PLAN_INVALID", detail: "observation_date must be an ISO calendar date" } },
					{ status: 422 },
				);
			}
			return HttpResponse.json({ data: storedPlan }, { status: 201 });
		}),
	);
	renderPanel({ defaultObservationDate: null });
	await user.click(await screen.findByRole("checkbox", { name: /标的600779/ }));
	fireEvent.change(screen.getByLabelText("观察日期"), { target: { value: "2026-11-10" } });
	await user.type(screen.getByLabelText("600779 候选理由"), "缩量回踩半年线");
	await user.type(screen.getByLabelText("次日计划"), "次日计划文本");
	await user.click(screen.getByRole("button", { name: "保存理由与次日计划" }));
	expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
	// 草稿保留：理由与计划仍可重试。
	expect(screen.getByLabelText("600779 候选理由")).toHaveValue("缩量回踩半年线");
	await user.click(screen.getByRole("button", { name: "保存理由与次日计划" }));
	await screen.findAllByText(/观察日 2026-11-10/);
	expect(attempts).toHaveLength(2);
});

it("requires the anchor or a hand-filled date before saving", async () => {
	const user = userEvent.setup();
	server.use(http.get("/api/v1/market/next-day-plans", () => HttpResponse.json({ data: [] })));
	renderPanel({ defaultObservationDate: null });
	expect(screen.getByText(/最近完整交易日尚未落定/)).toBeInTheDocument();
	await user.click(await screen.findByRole("checkbox", { name: /标的510888/ }));
	await user.type(screen.getByLabelText("510888 候选理由"), "跟随大盘");
	await user.type(screen.getByLabelText("次日计划"), "计划文本");
	expect(screen.getByRole("button", { name: "保存理由与次日计划" })).toBeDisabled();
	fireEvent.change(screen.getByLabelText("观察日期"), { target: { value: "2026-11-10" } });
	expect(screen.getByRole("button", { name: "保存理由与次日计划" })).toBeEnabled();
});

it("drops candidates that left the watchlist from the save payload", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	server.use(
		http.get("/api/v1/market/next-day-plans", () => HttpResponse.json({ data: [] })),
		http.post("/api/v1/market/next-day-plans", async ({ request }) => {
			posted.push(await request.json());
			return HttpResponse.json({ data: storedPlan }, { status: 201 });
		}),
	);
	const view = renderPanel();
	await user.click(await screen.findByRole("checkbox", { name: /标的600779/ }));
	await user.click(screen.getByRole("checkbox", { name: /标的510888/ }));
	await user.type(screen.getByLabelText("600779 候选理由"), "回踩");
	await user.type(screen.getByLabelText("510888 候选理由"), "跟随");
	await user.type(screen.getByLabelText("次日计划", { exact: true }), "计划");
	// 自选在保存前移除了 600779：不可见候选不得静默进入保存载荷。
	view.rerender(<NextDayPlanPanel ids={[510888]} resolveEntry={resolveEntry} defaultObservationDate="2026-11-10" />);
	expect(screen.getByRole("button", { name: "保存理由与次日计划" })).toBeEnabled();
	await user.click(screen.getByRole("button", { name: "保存理由与次日计划" }));
	await screen.findByText(/已保存 next-day-plan/);
	const body = posted[0] as {
		candidate_notes: Array<{ instrument_id: number }>;
	};
	expect(body.candidate_notes.map((note) => note.instrument_id)).toEqual([510888]);
});

it("trims padded reasons and plan text before submission", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	server.use(
		http.get("/api/v1/market/next-day-plans", () => HttpResponse.json({ data: [] })),
		http.post("/api/v1/market/next-day-plans", async ({ request }) => {
			posted.push(await request.json());
			return HttpResponse.json({ data: storedPlan }, { status: 201 });
		}),
	);
	renderPanel();
	await user.click(await screen.findByRole("checkbox", { name: /标的600779/ }));
	await user.type(screen.getByLabelText("600779 候选理由"), "  回踩半年线  ");
	await user.type(screen.getByLabelText("次日计划", { exact: true }), "  计划正文  ");
	await user.click(screen.getByRole("button", { name: "保存理由与次日计划" }));
	await screen.findByText(/已保存 next-day-plan/);
	const body = posted[0] as { candidate_notes: Array<{ reason: string }>; next_day_plan: string };
	expect(body.candidate_notes[0]?.reason).toBe("回踩半年线");
	expect(body.next_day_plan).toBe("计划正文");
});

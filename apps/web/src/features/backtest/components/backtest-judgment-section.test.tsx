import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { expect, it } from "vitest";
import { server } from "@/mocks/server";
import type { BacktestRun } from "../types";
import { BacktestJudgmentSection } from "./backtest-judgment-section";

const savedJudgment = {
	judgment_id: "research-judgment:sha256:" + "1".repeat(64),
	run_ids: ["sys-fx-nav-001", "sys-fx-nav-002"],
	judgment: "同口径可比；001 回撤更浅，次日观察放量修复",
	created_at: "2026-11-10T15:05:00Z",
	strategy_id: "sys-fx-etf-rotation",
	strategy_version: 2,
	schema_version: 1,
};

function run(runId: string, strategyVersion = "1"): BacktestRun {
	return {
		runId,
		strategyId: "sys-fx-etf-rotation",
		strategyVersion,
		mode: "backtest",
		status: "completed",
		startedAt: "2026-11-10T09:00:00Z",
		completedAt: "2026-11-10T09:14:00Z",
		errorMessage: "",
		parentRunId: "",
		benchmarkReturn: null,
		progressPct: 100,
		currentStep: "completed",
		completedDays: 60,
		totalDays: 60,
	};
}

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

function renderSection(runIds: readonly string[] = ["sys-fx-nav-001", "sys-fx-nav-002"]) {
	return render(
		<BacktestJudgmentSection runIds={runIds} runs={[run("sys-fx-nav-001"), run("sys-fx-nav-002", "2")]} />,
		{ wrapper: wrapper() },
	);
}

it("saves a judgment bound to the explicit comparison run identities", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	let recorded = false;
	server.use(
		http.get("/api/v1/research/judgments", () => HttpResponse.json({ data: recorded ? [savedJudgment] : [] })),
		http.post("/api/v1/research/judgments", async ({ request }) => {
			posted.push(await request.json());
			recorded = true;
			return HttpResponse.json({ data: savedJudgment }, { status: 201 });
		}),
	);
	renderSection();
	await user.type(screen.getByLabelText("判断结论"), "同口径可比；001 回撤更浅");
	await user.click(screen.getByRole("button", { name: "保存研究判断" }));
	await screen.findAllByText(/research-judgment:sha256:/);
	const body = posted[0] as { run_ids: string[]; judgment: string; strategy_id?: string };
	// 判断绑定会话比较集合的明确 run 身份（选择序原样），未选策略时省略键。
	expect(body.run_ids).toEqual(["sys-fx-nav-001", "sys-fx-nav-002"]);
	expect(body.judgment).toBe("同口径可比；001 回撤更浅");
	expect("strategy_id" in body).toBe(false);
});

it("carries the selected follow-up strategy version from comparison members", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	server.use(
		http.get("/api/v1/research/judgments", () => HttpResponse.json({ data: [] })),
		http.post("/api/v1/research/judgments", async ({ request }) => {
			posted.push(await request.json());
			return HttpResponse.json({ data: savedJudgment }, { status: 201 });
		}),
	);
	renderSection();
	// 选项 = 比较成员的 distinct strategyId@strategyVersion（去重）。
	const select = screen.getByLabelText("后续验证策略版本");
	expect(select.textContent).toContain("sys-fx-etf-rotation@1");
	expect(select.textContent).toContain("sys-fx-etf-rotation@2");
	await user.type(screen.getByLabelText("判断结论"), "转入策略版本验证");
	await user.selectOptions(select, "sys-fx-etf-rotation@2");
	await user.click(screen.getByRole("button", { name: "保存研究判断" }));
	await screen.findAllByText(/research-judgment:sha256:/);
	const body = posted[0] as { strategy_id: string; strategy_version: number };
	expect(body.strategy_id).toBe("sys-fx-etf-rotation");
	expect(body.strategy_version).toBe(2);
});

it("reopens saved judgments with run links, verification and plan hand-off entries", async () => {
	server.use(http.get("/api/v1/research/judgments", () => HttpResponse.json({ data: [savedJudgment] })));
	renderSection();
	const entry = await screen.findByTestId("research-judgment-entry");
	// 每个 run 身份链接到对应回测详情。
	expect(entry.innerHTML).toContain('href="/research/backtests/sys-fx-nav-001"');
	expect(entry.innerHTML).toContain('href="/research/backtests/sys-fx-nav-002"');
	// 进入验证 → 策略详情页（携带回程上下文）。
	expect(entry.innerHTML).toContain(
		`href="/research/strategies/sys-fx-etf-rotation?fromJudgment=${encodeURIComponent(savedJudgment.judgment_id)}"`,
	);
	// 转入次日计划 → 计划面板携带来源。
	expect(entry.innerHTML).toContain(
		`href="/markets/watchlist?judgment=${encodeURIComponent(savedJudgment.judgment_id)}"`,
	);
});

it("retries the saved-judgment list when the read fails", async () => {
	const user = userEvent.setup();
	const reads: number[] = [];
	let failures = 1;
	server.use(
		http.get("/api/v1/research/judgments", () => {
			reads.push(1);
			if (failures > 0) {
				failures -= 1;
				return HttpResponse.json({ error: { code: "UNKNOWN", detail: "boom" } }, { status: 500 });
			}
			return HttpResponse.json({ data: [savedJudgment] });
		}),
	);
	renderSection();
	const retry = await screen.findByRole("button", { name: "判断列表读取失败，重试" });
	await user.click(retry);
	const entry = await screen.findByTestId("research-judgment-entry");
	expect(entry).toHaveTextContent(savedJudgment.judgment_id);
	expect(reads).toHaveLength(2);
});

it("fails honestly on a rejected save and keeps the draft for retry", async () => {
	const user = userEvent.setup();
	const posted: unknown[] = [];
	let failures = 1;
	server.use(
		http.get("/api/v1/research/judgments", () => HttpResponse.json({ data: [] })),
		http.post("/api/v1/research/judgments", async ({ request }) => {
			posted.push(await request.json());
			if (failures > 0) {
				failures -= 1;
				return HttpResponse.json(
					{ error: { code: "RESEARCH_JUDGMENT_INVALID", detail: "judgment must be a non-empty unpadded text" } },
					{ status: 422 },
				);
			}
			return HttpResponse.json({ data: savedJudgment }, { status: 201 });
		}),
	);
	renderSection();
	await user.type(screen.getByLabelText("判断结论"), "  回撤更浅，观察放量  ");
	await user.click(screen.getByRole("button", { name: "保存研究判断" }));
	expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
	// 草稿保留（含首尾空格原文），重试成功且提交前已 trim。
	expect(screen.getByLabelText("判断结论")).toHaveValue("  回撤更浅，观察放量  ");
	await user.click(screen.getByRole("button", { name: "保存研究判断" }));
	await screen.findAllByText(/research-judgment:sha256:/);
	expect(posted).toHaveLength(2);
	expect((posted[1] as { judgment: string }).judgment).toBe("回撤更浅，观察放量");
});

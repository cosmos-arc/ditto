import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import { DailyDecisionWorkspace } from "./daily-decision-workspace";

type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];

function report(status: "blocked" | "review" | "ready"): DailyDecisionV2Response {
	return {
		identity: {
			strategy_id: "seed_etf_industry_rotation",
			strategy_version: "3",
			account_id: "paper-a",
			sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
			signal_date: "2026-07-16",
			decision_date: "2026-07-16",
			intended_trade_date: "2026-07-17",
		},
		readiness: {
			status,
			reason_codes:
				status === "blocked"
					? ["ACCOUNT_BASELINE_MISSING"]
					: status === "review"
						? ["RISK_WARNING"]
						: ["READY_FOR_REVIEW"],
			details: [status === "blocked" ? "账户基线缺失" : "人工复核后继续"],
		},
		data: {
			required_datasets: ["etf_daily"],
			snapshot_ids: { etf_daily: "sha256:dataset-1" },
			dataset_states: [
				{
					dataset: "etf_daily",
					status: "ready",
					snapshot_id: "sha256:dataset-1",
					reason: "",
				},
			],
			freshness: "ready",
			dq_state: "passed",
		},
		run_package: {
			outcome: "completed",
			batch_key: "eod-2026-07-16-seed_etf_industry_rotation-3",
			artifact_id: "signal-package-1",
			checksum: "sha256:abc123",
			checksum_valid: true,
			no_rebalance: false,
			factor_evidence: { "510300": { momentum: 0.8 } },
			risk_evidence: status === "review" ? ["RISK_WARNING"] : [],
		},
		account_positions: {
			baseline_id: "baseline-1",
			account_id: "paper-a",
			sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
			cash_available: 50_000,
			cash_settled: 50_000,
			cash_frozen: 0,
			total_value: 100_000,
			nav: 1,
			exposure: 50_000,
			as_of: "2026-07-16",
			positions: [],
		},
		actions: [
			{
				intent_id: "intent-510300",
				instrument_id: 510300,
				direction: "buy",
				target_weight: 0.3,
				current_weight: 0.12,
				delta_weight: 0.18,
				raw_quantity: 1_050,
				rounded_quantity: 1_000,
				suggested_quantity: 1_000,
				reference_price: 4.31,
				lot_size: 100,
				cash_impact: -4_310,
				reason: "rounded_down_to_board_lot",
				sizing_readiness: "ready",
				risk_flags: ["liquidity_review"],
				intent_status: "partially_filled",
				filled_quantity: 400,
				remaining_quantity: 550,
			},
		],
		execution_review: {
			effective_fills: [
				{
					fill_id: "fill-1",
					intent_id: "intent-510300",
					strategy_id: "seed_etf_industry_rotation",
					trade_date: "2026-07-18",
					instrument_id: 510300,
					direction: "buy",
					quantity: 400,
					fill_price: 4.32,
					fee: 1.2,
					slippage: 0.01,
					notes: "manual paper fill",
					settlement_date: "2026-07-20",
				},
			],
			deviation: {
				strategy_id: "seed_etf_industry_rotation",
				signal_date: "2026-07-16",
				total_signals: 1,
				filled: 1,
				unfilled: 0,
				items: [
					{
						instrument_id: 510300,
						signal_action: "buy",
						signal_weight: 0.3,
						actual_weight: 0.18,
						deviation_bps: 120,
						fill_status: "partial",
					},
				],
			},
			pnl: {
				total_realized_pnl: 20,
				total_unrealized_pnl: 180,
				total_fees: 3,
				net_pnl: 197,
			},
			exceptions: ["TRADE_DATE_MISMATCH"],
			unresolved_conflicts: [],
		},
	};
}

describe("DailyDecisionWorkspace", () => {
	it("blocked 显示稳定 reason code 和可操作恢复入口，但不展示建议", () => {
		render(<DailyDecisionWorkspace report={report("blocked")} />);

		const alert = screen.getByRole("alert");
		expect(within(alert).getByText("ACCOUNT_BASELINE_MISSING")).toBeInTheDocument();
		expect(within(alert).getByText("选择账户并导入完整账户基线")).toBeInTheDocument();
		expect(within(alert).getByRole("link", { name: "前往执行范围" })).toHaveAttribute(
			"href",
			"#trading-execution-scope",
		);
		expect(screen.queryByText("#510300")).not.toBeInTheDocument();
	});

	it("blocked 的长恢复命令可通过键盘进入横向滚动区", () => {
		const value = report("blocked");
		value.readiness.reason_codes = ["EOD_RUN_MISSING"];
		value.readiness.details = ["尚未找到 EOD 运行记录"];
		render(<DailyDecisionWorkspace report={value} />);

		const command = screen.getByText(/ditto ops run-eod/);
		expect(command).toHaveAttribute("tabindex", "0");
		expect(command).toHaveClass("overflow-x-auto");
	});

	it("兼容后端新增的 EOD 不完整与 signal-intent 不一致 reason codes", () => {
		const value = report("blocked");
		Reflect.set(value.readiness, "reason_codes", ["EOD_RUN_INCOMPLETE", "SIGNAL_INTENT_MISMATCH"]);
		render(<DailyDecisionWorkspace report={value} />);

		const alert = screen.getByRole("alert");
		expect(within(alert).getByText("EOD_RUN_INCOMPLETE")).toBeInTheDocument();
		expect(within(alert).getByText("检查不完整的 EOD 证据并安全重跑")).toBeInTheDocument();
		expect(within(alert).getByText("SIGNAL_INTENT_MISMATCH")).toBeInTheDocument();
		expect(within(alert).getByText("停止交易并核对 package 与 intent 一致性")).toBeInTheDocument();
		expect(within(alert).getByText(/ditto ops run-eod/)).toBeInTheDocument();
	});

	it("展示 D 信号、决策日与 D+1 建议交易日及身份", () => {
		render(<DailyDecisionWorkspace report={report("ready")} />);

		expect(screen.getByText("D · 信号数据")).toBeInTheDocument();
		expect(screen.getByText("决策生成")).toBeInTheDocument();
		expect(screen.getByText("D+1 · 建议交易日")).toBeInTheDocument();
		expect(screen.getByText("2026-07-17")).toBeInTheDocument();
		expect(screen.getByText("版本 3")).toBeInTheDocument();
	});

	it("ready 展示 sizing、进度、参考价、理由、风险与数据 snapshot", () => {
		render(<DailyDecisionWorkspace report={report("ready")} />);

		expect(screen.getByText("#510300")).toBeInTheDocument();
		expect(screen.getByText(/30\.00% \/ 12\.00% \/ \+18\.00%/)).toBeInTheDocument();
		expect(screen.getByText(/1,050 \/ 1,000 \/ 100/)).toBeInTheDocument();
		expect(screen.getByText(/1,000 \/ 400 \/ 550/)).toBeInTheDocument();
		expect(screen.getByText(/¥4\.31 \/ -¥4,310/)).toBeInTheDocument();
		expect(screen.getByText(/rounded_down_to_board_lot · ready/)).toBeInTheDocument();
		expect(screen.getByText("liquidity_review")).toBeInTheDocument();
		expect(screen.getByText("sha256:dataset-1")).toBeInTheDocument();
	});

	it("review 直接展示后端剩余数量、成交事实、偏差、PnL、异常与 checksum", () => {
		render(<DailyDecisionWorkspace report={report("review")} />);

		expect(screen.getAllByText("RISK_WARNING").length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("fill-1")).toBeInTheDocument();
		expect(screen.getByText("剩余 550")).toBeInTheDocument();
		expect(screen.getByText("实际日 2026-07-18")).toBeInTheDocument();
		expect(screen.getByText(/BUY 400 @ ¥4\.32/)).toBeInTheDocument();
		expect(screen.getByText(/#510300 · partial · 120 bps/)).toBeInTheDocument();
		expect(screen.getByText(/净盈亏 ¥197 · 费用 ¥3/)).toBeInTheDocument();
		expect(screen.getByText("TRADE_DATE_MISMATCH")).toBeInTheDocument();
		expect(screen.getAllByText("sha256:abc123").length).toBeGreaterThanOrEqual(1);
	});

	it("重跑冲突与零调仓均只消费稳定 reason code/package 事实", () => {
		const value = report("review");
		value.readiness.reason_codes = ["RERUN_CONFLICT", "NO_REBALANCE_REQUIRED"];
		value.readiness.details = ["checksum changed", "no intents"];
		value.run_package.no_rebalance = true;
		value.actions = [];
		render(<DailyDecisionWorkspace report={value} />);

		expect(screen.getByText("RERUN_CONFLICT")).toBeInTheDocument();
		expect(screen.getByText("NO_REBALANCE_REQUIRED")).toBeInTheDocument();
		expect(screen.getByText("零调仓：本次决策无需执行交易。")).toBeInTheDocument();
	});

	it("窄屏下建议表使用可聚焦横向滚动区", () => {
		render(<DailyDecisionWorkspace report={report("ready")} />);

		const scrollRegion = screen.getByLabelText("执行建议表");
		expect(scrollRegion).toHaveAttribute("tabindex", "0");
		expect(scrollRegion).toHaveClass("overflow-x-auto");
	});
});

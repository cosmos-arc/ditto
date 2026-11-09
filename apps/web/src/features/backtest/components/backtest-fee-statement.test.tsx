import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { mockBacktestReport } from "@/mocks/fixtures/backtest";
import { mapBacktestReport } from "../api/backtests";
import { BacktestFeeStatementView } from "./backtest-fee-statement";

it("distinguishes an absent legacy bill from an explicitly empty saved bill", () => {
	const { rerender } = render(
		<BacktestFeeStatementView statement={mapBacktestReport(mockBacktestReport).feeStatement} />,
	);
	expect(screen.getByText("本报告未保存逐笔费用账单。")).toBeInTheDocument();
	const report = mapBacktestReport({
		...mockBacktestReport,
		fee_statement: {
			currency: "CNY",
			policy: "已保存研究假设",
			rules_observed_at: "2026-11-09",
			source_ref: "docs/evidence/historical-fees-757.md",
			final_cash: null,
			fills: [],
		},
	});
	rerender(<BacktestFeeStatementView statement={report.feeStatement} />);
	expect(screen.getByText("本次运行没有实际成交。")).toBeInTheDocument();
	expect(screen.getByText(/期末现金：未记录/)).toBeInTheDocument();
});

it("renders saved fractional charges and rates without recalculating or rounding them to cents", () => {
	const report = mapBacktestReport({
		...mockBacktestReport,
		fee_statement: {
			currency: "CNY",
			policy: "研究佣金已剔除中登过户费",
			rules_observed_at: "2026-11-09",
			source_ref: "docs/evidence/historical-fees-757.md",
			final_cash: 8993.9745,
			fills: [
				{
					fill_id: "fill-1",
					order_id: "order-1",
					instrument_id: 1000001,
					symbol: "000001.SZ",
					trade_date: "2015-07-31",
					direction: "sell",
					quantity: 100,
					price: 10,
					commission: 5,
					stamp_duty: 1,
					transfer_fee: 0.0255,
					total_fee: 6.0255,
					schedule: {
						instrument_id: 1000001,
						as_of_date: "2014-01-01",
						commission_rate: 0.0003,
						min_commission: 5,
						stamp_duty_rate: 0.001,
						transfer_fee_rate: 0.0000255,
						transfer_fee_per_share: 0,
					},
				},
			],
		},
	});
	render(<BacktestFeeStatementView statement={report.feeStatement} />);
	expect(screen.getByText("0.0255")).toBeInTheDocument();
	expect(screen.getByText("6.0255")).toBeInTheDocument();
	expect(screen.getByText("2014-01-01 起")).toBeInTheDocument();
	expect(report.feeStatement?.fills[0]).toMatchObject({
		tradeDate: "2015-07-31",
		transferFee: 0.0255,
		totalFee: 6.0255,
	});
});

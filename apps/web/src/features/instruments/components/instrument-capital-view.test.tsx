import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";
import { server } from "@/mocks/server";
import { InstrumentCapitalView } from "./instrument-capital-view";

it("展示降序响应中最新十条，显式刷新仅更新当前资金画像", async () => {
	let corrected = false;
	const days = ["11-03", "11-02", "10-30", "10-29", "10-28", "10-27", "10-26", "10-23", "10-22", "10-21", "10-20", "10-19"];
	const empty = { rows: [], latest_trade_date: null, data_coverage: null };
	server.use(...instrumentsHandlers, http.post("/api/v1/capital/profile", () => HttpResponse.json({
		data: {
			instrument_id: 1000001, window: { start: "2026-10-19", end: "2026-11-03" },
			moneyflow: empty, top_list: empty, top_inst: empty,
			margin_trading: {
				rows: days.map(day => ({ trade_date: `2026-${day}`, margin_buy_balance: corrected ? 200 : 100 })),
				latest_trade_date: "2026-11-03", pending_trade_dates: ["2026-11-04"],
				read_error: corrected ? "源暂不可用" : null, freshness_promise: "下一交易日 09:15", data_coverage: null,
			},
		},
	})));
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	render(<QueryClientProvider client={client}><InstrumentCapitalView id="1000001" /></QueryClientProvider>);
	await screen.findByText("2026-11-03");
	expect(screen.getByText("2026-10-21")).toBeInTheDocument();
	expect(screen.queryByText("2026-10-20")).not.toBeInTheDocument();
	expect(screen.queryByText("2026-10-19")).not.toBeInTheDocument();
	corrected = true;
	await userEvent.click(screen.getByRole("button", { name: "刷新资金画像" }));
	await screen.findByText(/源暂不可用/);
	expect(within(screen.getByTestId("capital-margin-pending")).getByText(/2026-11-04/)).toBeInTheDocument();
	client.clear();
});

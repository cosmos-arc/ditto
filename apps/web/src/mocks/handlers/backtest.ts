import { HttpResponse, http, type RequestHandler } from "msw";
import { mockBacktestResult } from "../fixtures/backtest";

export const backtestHandlers: RequestHandler[] = [
	http.get("/api/research/backtest/:jobId", () => {
		return HttpResponse.json(mockBacktestResult);
	}),
];

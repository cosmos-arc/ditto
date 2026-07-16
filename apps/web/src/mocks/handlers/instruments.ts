import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockInstrumentChart,
	mockInstrumentDetail,
	mockInstrumentFundamentals,
} from "../fixtures/instruments";

export const instrumentsHandlers: RequestHandler[] = [
	http.get("/api/instruments/:id", () => {
		return HttpResponse.json(mockInstrumentDetail);
	}),

	http.get("/api/instruments/:id/chart", () => {
		return HttpResponse.json(mockInstrumentChart);
	}),

	http.get("/api/instruments/:id/fundamentals", () => {
		return HttpResponse.json(mockInstrumentFundamentals);
	}),
];

import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockASharesOverview,
	mockCapitalRotation,
	mockCrossMatrix,
	mockMacroDrivers,
	mockMarketCalendar,
	mockMarketContext,
	mockMarketOverview,
	mockScopeStrip,
	mockScreenerColumns,
	mockScreenerPresets,
	mockScreenerResults,
} from "../fixtures/markets";

export const marketsHandlers: RequestHandler[] = [
	http.get("/api/markets/context", () => {
		return HttpResponse.json(mockMarketContext);
	}),

	http.get("/api/markets/scope-strip", () => {
		return HttpResponse.json(mockScopeStrip);
	}),

	http.get("/api/markets/overview", () => {
		return HttpResponse.json(mockMarketOverview);
	}),

	http.get("/api/markets/cross-matrix", () => {
		return HttpResponse.json(mockCrossMatrix);
	}),

	http.get("/api/markets/macro-drivers", () => {
		return HttpResponse.json(mockMacroDrivers);
	}),

	http.get("/api/markets/capital-rotation", () => {
		return HttpResponse.json(mockCapitalRotation);
	}),

	http.get("/api/markets/a-shares", () => {
		return HttpResponse.json(mockASharesOverview);
	}),

	http.get("/api/market/calendar", () => {
		return HttpResponse.json(mockMarketCalendar);
	}),

	http.get("/api/screener/run", () => {
		return HttpResponse.json(mockScreenerResults);
	}),

	http.get("/api/screener/presets", () => {
		return HttpResponse.json(mockScreenerPresets);
	}),

	http.get("/api/screener/columns", () => {
		return HttpResponse.json(mockScreenerColumns);
	}),
];

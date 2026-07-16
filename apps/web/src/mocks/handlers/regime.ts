import { HttpResponse, http, type RequestHandler } from "msw";
import { mockRegimeCurrent, mockRegimeDrivers, mockRegimeHistory, mockRegimeStrategyImpact } from "../fixtures/regime";

export const regimeHandlers: RequestHandler[] = [
	http.get("/api/research/regime/current", () => {
		return HttpResponse.json(mockRegimeCurrent);
	}),

	http.get("/api/research/regime/drivers", () => {
		return HttpResponse.json(mockRegimeDrivers);
	}),

	http.get("/api/research/regime/history", () => {
		return HttpResponse.json(mockRegimeHistory);
	}),

	http.get("/api/research/regime/strategy-impact", () => {
		return HttpResponse.json(mockRegimeStrategyImpact);
	}),
];

import { HttpResponse, http, type RequestHandler } from "msw";
import { mockRiskBreaches, mockRiskDrawdown, mockRiskExposure, mockRiskVar } from "../fixtures/risk";

export const riskHandlers: RequestHandler[] = [
	http.get("/api/trading/risk/var", () => {
		return HttpResponse.json(mockRiskVar);
	}),

	http.get("/api/trading/risk/drawdown", () => {
		return HttpResponse.json(mockRiskDrawdown);
	}),

	http.get("/api/trading/risk/exposure", () => {
		return HttpResponse.json(mockRiskExposure);
	}),

	http.get("/api/trading/risk/breaches", () => {
		return HttpResponse.json(mockRiskBreaches);
	}),
];

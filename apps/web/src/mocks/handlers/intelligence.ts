import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockIntelligenceFlow,
	mockIntelligenceMacro,
	mockIntelligenceFundamentals,
} from "../fixtures/intelligence";

export const intelligenceHandlers: RequestHandler[] = [
	http.get("/api/markets/intelligence/flow", () => {
		return HttpResponse.json(mockIntelligenceFlow);
	}),

	http.get("/api/markets/intelligence/macro", () => {
		return HttpResponse.json(mockIntelligenceMacro);
	}),

	http.get("/api/markets/intelligence/fundamentals", () => {
		return HttpResponse.json(mockIntelligenceFundamentals);
	}),
];

import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockAgentFindings,
	mockDataHealth,
	mockDecisionBanner,
	mockHomeAlerts,
	mockHomePulse,
	mockMarketIndices,
	mockMarketPulseMetrics,
	mockPendingActions,
	mockRecentSignals,
} from "../fixtures/home";

export const homeHandlers: RequestHandler[] = [
	http.get("/api/home/pulse", () => {
		return HttpResponse.json(mockHomePulse);
	}),

	http.get("/api/home/decision-banner", () => {
		return HttpResponse.json(mockDecisionBanner);
	}),

	http.get("/api/home/pending-actions", () => {
		return HttpResponse.json({ actions: mockPendingActions });
	}),

	http.get("/api/home/alerts", () => {
		return HttpResponse.json({ alerts: mockHomeAlerts });
	}),

	http.get("/api/home/signals/recent", () => {
		return HttpResponse.json({ signals: mockRecentSignals });
	}),

	http.get("/api/home/agent-findings", () => {
		return HttpResponse.json({ findings: mockAgentFindings });
	}),

	http.get("/api/home/data-health", () => {
		return HttpResponse.json({ providers: mockDataHealth });
	}),

	http.get("/api/market/indices", () => {
		return HttpResponse.json({ indices: mockMarketIndices });
	}),

	http.get("/api/home/pulse-metrics", () => {
		return HttpResponse.json({ metrics: mockMarketPulseMetrics });
	}),
];

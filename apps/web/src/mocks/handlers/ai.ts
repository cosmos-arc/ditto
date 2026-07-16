import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockAiPulse,
	mockAgentQuickView,
	mockCopilotQuickView,
	mockCopilotSessions,
	mockCopilotMessages,
	mockAgentPlans,
	mockAgentRuns,
	mockAgentFindings,
} from "../fixtures/ai";

export const aiHandlers: RequestHandler[] = [
	http.get("/api/ai/pulse", () => {
		return HttpResponse.json(mockAiPulse);
	}),

	http.get("/api/ai/agents/quick-view", () => {
		return HttpResponse.json(mockAgentQuickView);
	}),

	http.get("/api/ai/copilot/quick-view", () => {
		return HttpResponse.json(mockCopilotQuickView);
	}),

	http.get("/api/ai/copilot/sessions", () => {
		return HttpResponse.json(mockCopilotSessions);
	}),

	http.get("/api/ai/copilot/sessions/:id/messages", () => {
		return HttpResponse.json({ messages: mockCopilotMessages });
	}),

	http.get("/api/ai/agents/plans", () => {
		return HttpResponse.json(mockAgentPlans);
	}),

	http.get("/api/agents/runs", () => {
		return HttpResponse.json(mockAgentRuns);
	}),

	http.get("/api/ai/agents/findings", () => {
		return HttpResponse.json(mockAgentFindings);
	}),
];

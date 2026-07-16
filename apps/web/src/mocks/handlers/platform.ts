import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockPipelineRuns,
	mockPipelines,
	mockPlatformAlerts,
	mockPlatformHealth,
	mockPlatformResources,
	mockProviders,
} from "../fixtures/platform";

export const platformHandlers: RequestHandler[] = [
	http.get("/api/platform/health", () => {
		return HttpResponse.json(mockPlatformHealth);
	}),

	http.get("/api/platform/providers", () => {
		return HttpResponse.json({ providers: mockProviders });
	}),

	http.get("/api/platform/pipelines", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);

		const start = (page - 1) * pageSize;
		const items = mockPipelines.slice(start, start + pageSize);

		return HttpResponse.json({
			items,
			total: mockPipelines.length,
			page,
			pageSize,
		});
	}),

	http.get("/api/platform/pipelines/:pipelineId/runs", () => {
		return HttpResponse.json({
			items: mockPipelineRuns,
			total: mockPipelineRuns.length,
			page: 1,
			pageSize: 20,
		});
	}),

	http.get("/api/platform/alerts", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);

		const start = (page - 1) * pageSize;
		const items = mockPlatformAlerts.slice(start, start + pageSize);

		return HttpResponse.json({
			items,
			total: mockPlatformAlerts.length,
			page,
			pageSize,
		});
	}),

	http.get("/api/platform/resources", () => {
		return HttpResponse.json({ resources: mockPlatformResources });
	}),

	http.post("/api/platform/alerts/:alertId/handle", () => {
		return HttpResponse.json({ success: true });
	}),

	http.post("/api/platform/pipelines/:pipelineId/rerun", () => {
		return HttpResponse.json({ success: true, message: "Pipeline rerun triggered" });
	}),
];

import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockExperiments,
	mockFactorAnalysis,
	mockFactorDetail,
	mockFactors,
	mockResearchPulse,
	mockResearchRuns,
	mockReviewQueue,
} from "../fixtures/research";

export const researchHandlers: RequestHandler[] = [
	http.get("/api/research/pulse", () => {
		return HttpResponse.json(mockResearchPulse);
	}),

	http.get("/api/factors", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);
		const start = (page - 1) * pageSize;
		const items = mockFactors.items.slice(start, start + pageSize);

		return HttpResponse.json({
			items,
			total: mockFactors.total,
			page,
			pageSize,
		});
	}),

	http.get("/api/factors/:id", () => {
		return HttpResponse.json(mockFactorDetail);
	}),

	http.get("/api/factors/:id/analysis", () => {
		return HttpResponse.json(mockFactorAnalysis);
	}),

	http.get("/api/research/runs", () => {
		return HttpResponse.json(mockResearchRuns);
	}),

	http.get("/api/research/experiments", () => {
		return HttpResponse.json(mockExperiments);
	}),

	http.get("/api/research/review-queue", () => {
		return HttpResponse.json(mockReviewQueue);
	}),
];

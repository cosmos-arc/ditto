import { HttpResponse, http, type RequestHandler } from "msw";
import { mockExperimentSummaryList } from "../fixtures/experiment-live";
import {
	mockExperiments,
	mockFactorAnalysis,
	mockFactorDetail,
	mockFactors,
	mockReviewQueue as mockPrototypeReviewQueue,
	mockResearchPulse,
	mockResearchRuns,
} from "../fixtures/research";
import { mockReviewPacket, mockReviewQueue } from "../fixtures/review-live";

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
		return HttpResponse.json(mockPrototypeReviewQueue);
	}),

	// === R3 live-shape handler（/api/v1/research/experiments，generated DTO + {data} 信封）===
	http.get("/api/v1/research/experiments", () =>
		HttpResponse.json({
			data: mockExperimentSummaryList,
			pagination: { total: mockExperimentSummaryList.length, limit: 50, offset: 0, has_more: false },
		}),
	),

	// === R3 review queue + review-packet live-shape（generated DTO + {data} 信封）===
	http.get("/api/v1/research/reviews", () => HttpResponse.json({ data: mockReviewQueue })),
	http.get("/api/v1/research/experiments/:experimentId/review-packet", ({ params }) => {
		const experimentId = String(params.experimentId);
		if (experimentId !== mockReviewPacket.experiment_id) {
			return new HttpResponse(null, { status: 404 });
		}
		return HttpResponse.json({ data: mockReviewPacket });
	}),
];

import { HttpResponse, http, type RequestHandler } from "msw";

export const intelligenceHandlers: RequestHandler[] = [
	http.get("/api/v1/macro/indicators/metadata", ({ request }) => {
		const query = new URL(request.url).searchParams;
		if (query.get("allow_experimental_data") !== "true") {
			return HttpResponse.json({ detail: "experimental dataset requires explicit opt-in" }, { status: 409 });
		}
		return HttpResponse.json({
			data: [
				{
					category: "economic",
					code: "cn_pmi_manufacturing",
					date: "2026-07-31",
					frequency: "monthly",
					indicator_id: 2001,
					name: "PMI 制造业",
					unit: "%",
					value: 50.4,
				},
				{
					category: "prices",
					code: "cn_cpi_yoy",
					date: "2026-07-31",
					frequency: "monthly",
					indicator_id: 2002,
					name: "CPI 同比",
					unit: "%",
					value: 0.7,
				},
			],
		});
	}),
];

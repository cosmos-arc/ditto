import { http, HttpResponse, type RequestHandler } from "msw";
import { mockOrderDetail, mockOrders } from "../fixtures/orders";

export const ordersHandlers: RequestHandler[] = [
	http.get("/api/trading/orders", ({ request }) => {
		const url = new URL(request.url);
		const tab = url.searchParams.get("tab");
		const page = Number(url.searchParams.get("page") ?? 1);
		const limit = Number(url.searchParams.get("limit") ?? 20);
		const sort = url.searchParams.get("sort");

		let filtered = mockOrders.items;

		if (tab) {
			filtered = filtered.filter((order) => order.status === tab);
		}

		if (sort) {
			const [field, direction] = sort.split(":");
			const sorted = [...filtered].sort((a, b) => {
				const aVal = String(a[field as keyof typeof a]);
				const bVal = String(b[field as keyof typeof b]);
				return direction === "desc" ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
			});
			filtered = sorted;
		}

		const start = (page - 1) * limit;
		const paged = filtered.slice(start, start + limit);

		return HttpResponse.json({
			items: paged,
			total: filtered.length,
			page,
			pageSize: limit,
		});
	}),

	http.get("/api/trading/orders/:id", () => {
		return HttpResponse.json(mockOrderDetail);
	}),
];

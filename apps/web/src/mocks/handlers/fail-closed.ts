import { HttpResponse, http, type RequestHandler } from "msw";

/** Final mock boundary: an unknown API request is a deterministic failure, never a network fallback. */
export const failClosedApiHandler: RequestHandler = http.all("*", ({ request }) => {
	const url = new URL(request.url);
	if (!url.pathname.startsWith("/api/")) return undefined;
	return HttpResponse.json(
		{
			error: "Unhandled mock API request",
			error_code: "MOCK_API_UNHANDLED",
			status_code: 501,
		},
		{ status: 501 },
	);
});

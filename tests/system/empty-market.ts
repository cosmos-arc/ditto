import { expect, type ConsoleMessage, type Response } from "@playwright/test";

// Empty isolated stores have no completed market snapshots. Suppress only this
// browser network diagnostic; callers also assert the actual rejection payload.
export function isEmptyMarketDiagnostic(message: ConsoleMessage): boolean {
	return (
		message.location().url.includes("/api/v1/market/context?") &&
		message.text() ===
			"Failed to load resource: the server responded with a status of 422 (Unprocessable Entity)"
	);
}

export async function expectEmptyMarketResponse(
	response: Response,
): Promise<void> {
	expect(response.status()).toBe(422);
	expect(await response.json()).toMatchObject({
		error_code: "MARKET_CONTEXT_INVALID",
		detail: "market context requires unique explicit source snapshot IDs",
	});
}

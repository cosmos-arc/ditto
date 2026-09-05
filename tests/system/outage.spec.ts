import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

test("production Web fails closed while the real API is offline", async ({
	page,
	request,
}) => {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	await expect(
		request.get(`${apiOrigin}/healthz`, { timeout: 1_000 }),
	).rejects.toThrow();

	const reportedErrors: string[] = [];
	const networkDiagnostics: { text: string; url: string }[] = [];
	const failedRequests: { url: string; error: string | undefined }[] = [];
	page.on("pageerror", (error) => reportedErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") networkDiagnostics.push({ text: message.text(), url: message.location().url });
	});
	page.on("requestfailed", (request) => {
		failedRequests.push({ url: request.url(), error: request.failure()?.errorText });
	});
	await page.goto("/");
	const alert = page.getByRole("alert");
	await expect(alert).toHaveText(
		"Ditto 启动已阻断：运行配置或后端兼容性验证失败。",
	);
	await expect(alert).toHaveAttribute("data-ditto-error-code", "BACKEND_UNREACHABLE");
	await expect(alert).toHaveAttribute(
		"data-ditto-bootstrap-diagnostic",
		JSON.stringify({
			schema: "ditto.bootstrap-diagnostic",
			schemaVersion: 1,
			stage: "backend_compatibility",
			code: "BACKEND_UNREACHABLE",
		}),
	);
	expect(reportedErrors).toEqual([]);
	// Chromium reports the deliberately refused request even when fetch rejection is handled.
	// Assert the exact diagnostic and endpoint; do not suppress unrelated console errors.
	expect(networkDiagnostics).toEqual([{
		text: "Failed to load resource: net::ERR_CONNECTION_REFUSED",
		url: `${apiOrigin}/api/v1/status`,
	}]);
	expect(failedRequests).toEqual([{
		url: `${apiOrigin}/api/v1/status`,
		error: "net::ERR_CONNECTION_REFUSED",
	}]);
});

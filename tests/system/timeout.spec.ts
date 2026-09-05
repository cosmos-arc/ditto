import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

test("production Web fails closed when a real TCP peer never responds", async ({
	page,
	request,
}) => {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	await expect(
		request.get(`${apiOrigin}/api/v1/status`, { timeout: 250 }),
	).rejects.toThrow();

	const reportedErrors: string[] = [];
	page.on("pageerror", (error) => reportedErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") reportedErrors.push(message.text());
	});
	await page.goto("/");
	const alert = page.getByRole("alert");
	await expect(alert).toHaveText(
		"Ditto 启动已阻断：运行配置或后端兼容性验证失败。",
		{ timeout: 20_000 },
	);
	await expect(alert).toHaveAttribute("data-ditto-error-code", "BACKEND_TIMEOUT");
	await expect(alert).toHaveAttribute(
		"data-ditto-bootstrap-diagnostic",
		JSON.stringify({
			schema: "ditto.bootstrap-diagnostic",
			schemaVersion: 1,
			stage: "backend_compatibility",
			code: "BACKEND_TIMEOUT",
		}),
	);
	expect(reportedErrors).toEqual([]);
});

import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

test("production Web rejects a real backend with an incompatible contract version", async ({
	page,
	request,
}) => {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	const status = await request.get(`${apiOrigin}/api/v1/status`);
	expect(status.status()).toBe(200);
	await expect(status.json()).resolves.toMatchObject({
		status: "running",
		api_contract_version: "v2",
	});

	const reportedErrors: string[] = [];
	page.on("pageerror", (error) => reportedErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") reportedErrors.push(message.text());
	});
	await page.goto("/");
	const alert = page.getByRole("alert");
	await expect(alert).toHaveText(
		"Ditto 启动已阻断：运行配置或后端兼容性验证失败。",
	);
	await expect(alert).toHaveAttribute("data-ditto-error-code", "API_CONTRACT_INCOMPATIBLE");
	await expect(alert).toHaveAttribute(
		"data-ditto-bootstrap-diagnostic",
		JSON.stringify({
			schema: "ditto.bootstrap-diagnostic",
			schemaVersion: 1,
			stage: "backend_compatibility",
			code: "API_CONTRACT_INCOMPATIBLE",
		}),
	);
	expect(reportedErrors).toEqual([]);
});

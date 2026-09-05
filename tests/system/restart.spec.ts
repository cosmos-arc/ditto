import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
const contractHeaders = { "X-Ditto-API-Contract-Version": "v1" } as const;

test("a clean API restart recovers the isolated manual and paper state", async ({
	page,
	request,
}) => {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	const status = await request.get(`${apiOrigin}/api/v1/status`, {
		headers: contractHeaders,
	});
	expect(status.status()).toBe(200);
	await expect(status.json()).resolves.toMatchObject({
		status: "running",
		api_contract_version: "v1",
	});

	const manual = await request.get(
		`${apiOrigin}/api/v1/manual/accounts/system-manual/ledger?as_of=2026-09-04`,
		{ headers: contractHeaders },
	);
	expect(manual.status()).toBe(200);
	await expect(manual.json()).resolves.toMatchObject({
		data: {
			account: { account_id: "system-manual", kind: "manual" },
			events: expect.arrayContaining([
				expect.objectContaining({
					note: "system browser reversal",
					reverses_event_id: expect.stringMatching(/\S/u),
				}),
			]),
		},
	});

	const paper = await request.get(
		`${apiOrigin}/api/v1/paper/sessions/system-paper-session`,
		{
			headers: contractHeaders,
		},
	);
	expect(paper.status()).toBe(200);
	await expect(paper.json()).resolves.toMatchObject({
		data: {
			session: { session_id: "system-paper-session", status: "paused" },
			executions: expect.arrayContaining([
				expect.objectContaining({
					order_id: expect.stringMatching(/\S/u),
					order_status: "filled",
					ledger_event_id: expect.stringMatching(/\S/u),
				}),
			]),
			latest_reconciliation: expect.objectContaining({ balanced: true }),
		},
	});

	const browserErrors: string[] = [];
	page.on("pageerror", (error) => browserErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") browserErrors.push(message.text());
	});
	await page.goto("/");
	await expect(page.getByText("今日优先事项")).toBeVisible();
	expect(browserErrors).toEqual([]);
});

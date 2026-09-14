import { expect, test, type APIResponse, type Page, type Response } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");
const contractHeaders = { "X-Ditto-API-Contract-Version": "v1" } as const;

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function jsonObject(response: APIResponse | Response): Promise<Record<string, unknown>> {
	const payload: unknown = await response.json();
	expect(typeof payload).toBe("object");
	expect(payload).not.toBeNull();
	return payload as Record<string, unknown>;
}

test.describe("real product flow: paper onboarding, order, and readback", () => {
	test("creates a paper workspace through the form, trades, and reads state back", async ({
		page,
		request,
	}) => {
		// Fixed identity + pinned as_of keeps every run deterministic and consistent
		// with the shared cohort fixtures; each run uses a fresh isolated state root.
		const accountId = "flow-paper-e2e";
		const sessionId = "flow-session-e2e";
		const errors = captureBrowserErrors(page);

		await page.goto("/portfolio/paper?as_of=2026-09-04", { waitUntil: "networkidle" });
		await expect(
			page.getByRole("heading", { name: "创建隔离的模拟账户" }),
		).toBeVisible();
		// The pinned as_of must drive both the onboarding form's 交易日 and the
		// order composer's trade date so the fill cannot hit a date mismatch.
		await expect(page.getByLabel("交易日")).toHaveValue("2026-09-04");

		await page.getByLabel("Paper 账户 ID").fill(accountId);
		await page.getByLabel("Paper 账户名称").fill("产品流验收账户");
		await page.getByLabel("Paper 会话 ID").fill(sessionId);
		await page.getByLabel("策略 ID").fill("flow-strategy");
		await page.getByLabel("期初现金").fill("100000");

		const sessionCreated = page.waitForResponse(
			(response) =>
				response.request().method() === "POST" &&
				response.url() === `${apiOrigin}/api/v1/paper/sessions`,
		);
		await page
			.getByRole("button", { name: "创建 PAPER 账户并启动会话" })
			.click();
		expect((await sessionCreated).status()).toBe(201);
		// The onboarding view hands off to the live workspace immediately.
		await expect(page.getByText("PAPER 模拟账户")).toBeVisible();
		await expect(page.getByText("RUNNING", { exact: true }).first()).toBeVisible();

		const workspace = new URL(page.url());
		expect(workspace.searchParams.get("account_id")).toBe(accountId);
		expect(workspace.searchParams.get("session_id")).toBe(sessionId);

		const orderPosted = page.waitForResponse(
			(response) =>
				response.request().method() === "POST" &&
				response.url() ===
					`${apiOrigin}/api/v1/paper/sessions/${sessionId}/orders`,
		);
		await page.getByRole("button", { name: "提交模拟订单" }).click();
		const orderResponse = await orderPosted;
		expect(orderResponse.status()).toBe(201);
		const receipt = await jsonObject(orderResponse);
		const receiptData = receipt["data"] as Record<string, unknown>;
		expect(receiptData).toMatchObject({
			order_status: "filled",
			ledger_event_id: expect.any(String),
		});
		const orderId = receiptData["order_id"] as string;
		const ledgerEventId = receiptData["ledger_event_id"] as string;
		await expect(page.getByText(/模拟成交已持久化/u).first()).toBeVisible();
		await expect(page.getByText("1 / 1", { exact: true }).first()).toBeVisible();

		await page.reload({ waitUntil: "networkidle" });
		await expect(page.getByText("PAPER 模拟账户")).toBeVisible();
		await expect(page.getByText("RUNNING", { exact: true }).first()).toBeVisible();
		await expect(page.getByText("1 / 1", { exact: true }).first()).toBeVisible();
		await expect(page.getByText(orderId, { exact: true }).first()).toBeVisible();

		const persisted = await request.get(
			`${apiOrigin}/api/v1/paper/sessions/${sessionId}`,
			{ headers: contractHeaders },
		);
		expect(persisted.status()).toBe(200);
		const persistedPayload = await jsonObject(persisted);
		const sessionData = persistedPayload["data"] as Record<string, unknown>;
		expect(sessionData).toMatchObject({
			session: { status: "running" },
			executions: expect.arrayContaining([
				expect.objectContaining({
					order_id: orderId,
					order_status: "filled",
					ledger_event_id: expect.any(String),
				}),
			]),
		});
		const tradeDate = (sessionData["session"] as Record<string, unknown>)["trade_date"] as string;

		const ledger = await request.get(
			`${apiOrigin}/api/v1/paper/accounts/${accountId}/ledger?as_of=${tradeDate}`,
			{ headers: contractHeaders },
		);
		expect(ledger.status()).toBe(200);
		await expect(ledger.json()).resolves.toMatchObject({
			data: {
				account: { account_id: accountId },
				events: expect.arrayContaining([
					expect.objectContaining({ event_id: ledgerEventId }),
				]),
			},
		});

		expect(errors).toEqual([]);
	});
});

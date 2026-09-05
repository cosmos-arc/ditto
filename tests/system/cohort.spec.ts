import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type APIResponse, expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");
const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");
const productVersion = requiredEnvironment("DITTO_PRODUCT_VERSION");
const gitSha = requiredEnvironment("DITTO_GIT_SHA");
const contractSha256 = createHash("sha256")
	.update(readFileSync("contracts/openapi/v1.json"))
	.digest("hex");
const contractHeaders = { "X-Ditto-API-Contract-Version": "v1" } as const;

async function expectJson(
	response: APIResponse,
	status: number,
): Promise<Record<string, unknown>> {
	expect(response.status()).toBe(status);
	expect(response.headers()["content-type"]).toContain("application/json");
	expect(response.headers()["x-request-id"]).toMatch(/^[0-9a-f-]{36}$/u);
	expect(response.headers()["x-trace-id"]).toMatch(/^[0-9a-f-]{36}$/u);
	const payload: unknown = await response.json();
	expect(payload).not.toBeNull();
	expect(typeof payload).toBe("object");
	return payload as Record<string, unknown>;
}

function objectField(
	source: Record<string, unknown>,
	name: string,
): Record<string, unknown> {
	const value = source[name];
	expect(value, `${name} must be an object`).not.toBeNull();
	expect(typeof value, `${name} must be an object`).toBe("object");
	expect(Array.isArray(value), `${name} must not be an array`).toBe(false);
	return value as Record<string, unknown>;
}

function stringField(source: Record<string, unknown>, name: string): string {
	const value = source[name];
	expect(typeof value, `${name} must be a string`).toBe("string");
	return value as string;
}

function arrayField(source: Record<string, unknown>, name: string): unknown[] {
	const value = source[name];
	expect(Array.isArray(value), `${name} must be an array`).toBe(true);
	return value as unknown[];
}

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function expectNoSeriousAccessibilityViolations(
	page: Page,
): Promise<void> {
	const accessibility = await new AxeBuilder({ page }).analyze();
	const serious = accessibility.violations.filter((violation) =>
		["critical", "serious"].includes(violation.impact ?? ""),
	);
	expect(serious).toEqual([]);
}

test.describe
	.serial("one production cohort over real HTTP", () => {
		test("binds the production Web build to the exact API and OpenAPI snapshot", async ({
			page,
			request,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			const health = await expectJson(
				await request.get(`${apiOrigin}/healthz`),
				200,
			);
			expect(health).toMatchObject({ status: "ok", service: "ditto-api" });
			const ready = await expectJson(
				await request.get(`${apiOrigin}/readyz`),
				200,
			);
			expect(ready).toMatchObject({ status: "ready", service: "ditto-api" });

			const status = await expectJson(
				await request.get(`${apiOrigin}/api/v1/status`),
				200,
			);
			expect(status).toMatchObject({
				status: "running",
				product_version: productVersion,
				git_sha: gitSha,
				api_contract_version: "v1",
				api_contract_sha256: contractSha256,
			});

			await page.goto("/");
			await expect(page.locator("#root")).not.toBeEmpty();
			await expect(page.getByText("今日优先事项")).toBeVisible();
			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		test("Today and Markets fail closed when certified market data is absent", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto("/markets/");
			await expect(page.getByText("市场覆盖")).toBeVisible();
			await expect(page.getByRole("alert")).toContainText(
				"没有回退到 latest 数据",
			);
			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});

		for (const route of [
			"/",
			"/markets/",
			"/portfolio/",
			"/portfolio/manual",
			"/research/",
			"/research/agent",
		]) {
			test(`has no serious accessibility violations on ${route}`, async ({
				page,
			}) => {
				const browserErrors = captureBrowserErrors(page);
				await page.goto(route, { waitUntil: "networkidle" });
				await expect(page.locator("#root")).not.toBeEmpty();
				await expectNoSeriousAccessibilityViolations(page);
				expect(browserErrors).toEqual([]);
			});
		}

		test("enforces exact CORS, contract-version, and structured error boundaries", async ({
			request,
		}) => {
			const allowed = await request.get(`${apiOrigin}/api/v1/status`, {
				headers: { Origin: webOrigin, ...contractHeaders },
			});
			await expectJson(allowed, 200);
			expect(allowed.headers()["access-control-allow-origin"]).toBe(webOrigin);

			const denied = await request.fetch(`${apiOrigin}/api/v1/status`, {
				method: "OPTIONS",
				headers: {
					Origin: "https://public.example.invalid",
					"Access-Control-Request-Method": "GET",
				},
			});
			expect(denied.status()).toBe(400);
			expect(denied.headers()["access-control-allow-origin"]).toBeUndefined();

			const incompatible = await expectJson(
				await request.get(`${apiOrigin}/api/v1/status`, {
					headers: { "X-Ditto-API-Contract-Version": "v2" },
				}),
				422,
			);
			expect(incompatible).toMatchObject({
				detail: "Invalid request parameters",
				error: "VALIDATION_ERROR",
				status_code: 422,
				success: false,
			});

			const missing = await expectJson(
				await request.get(`${apiOrigin}/api/v1/paper/sessions/missing`, {
					headers: contractHeaders,
				}),
				404,
			);
			expect(missing).toMatchObject({
				success: false,
				status_code: 404,
				error_code: "NOT_FOUND",
			});

			const unavailable = await expectJson(
				await request.post(`${apiOrigin}/api/v1/agent/sessions`, {
					headers: {
						...contractHeaders,
						"Idempotency-Key": "system-agent-unavailable",
					},
					data: { retention_class: "ephemeral" },
				}),
				503,
			);
			expect(unavailable).toMatchObject({
				success: false,
				status_code: 503,
				error_code: "AGENT_UNAVAILABLE",
			});
		});

		test("creates, corrects, reverses, and rebuilds an isolated manual ledger", async ({
			page,
			request,
		}) => {
			const created = await expectJson(
				await request.post(`${apiOrigin}/api/v1/manual/accounts`, {
					headers: contractHeaders,
					data: {
						account_id: "system-manual",
						name: "System Manual",
						opened_at: "2026-09-04T00:00:00Z",
						currency: "CNY",
					},
				}),
				201,
			);
			expect(objectField(created, "data")).toMatchObject({
				status: "created",
				account: { account_id: "system-manual", kind: "manual" },
				event: null,
			});

			const openingBody = {
				event_type: "opening_cash",
				trade_date: "2026-09-04",
				settlement_date: "2026-09-04",
				idempotency_key: "system-manual-opening",
				actor: "system-e2e",
				gross_amount: "100000",
			};
			const opening = await expectJson(
				await request.post(
					`${apiOrigin}/api/v1/manual/accounts/system-manual/events`,
					{
						headers: contractHeaders,
						data: openingBody,
					},
				),
				201,
			);
			expect(objectField(opening, "data")).toMatchObject({ status: "created" });
			const openingEventId = stringField(
				objectField(objectField(opening, "data"), "event"),
				"event_id",
			);

			const buyBody = {
				event_type: "buy",
				trade_date: "2026-09-04",
				settlement_date: "2026-09-07",
				idempotency_key: "system-manual-buy",
				actor: "system-e2e",
				instrument_id: 600519,
				quantity: "100",
				price: "100",
				fees: "5",
			};
			const buy = await expectJson(
				await request.post(
					`${apiOrigin}/api/v1/manual/accounts/system-manual/events`,
					{
						headers: contractHeaders,
						data: buyBody,
					},
				),
				201,
			);
			const buyEventId = stringField(
				objectField(objectField(buy, "data"), "event"),
				"event_id",
			);

			const browserErrors = captureBrowserErrors(page);
			await page.goto("/portfolio/manual?account_id=system-manual&as_of=2026-09-04", {
				waitUntil: "networkidle",
			});
			await expect(page.getByText("MANUAL 手工实际账户")).toBeVisible();
			await expect(
				page.getByText("system-manual", { exact: true }),
			).toBeVisible();
			await expect(
				page.getByText("System Manual", { exact: true }),
			).toBeVisible();
			// No certified price was seeded, so the ledger is durable but its
			// valuation correctly remains fail-closed instead of fabricating a mark.
			await expect(page.getByText("需要核对", { exact: true })).toBeVisible();

			// Correction and reversal are both driven through production React.
			// Their HTTP receipts plus refreshed ledger rows prove typed transport,
			// real handlers, append-only SQLite persistence, and query invalidation.
			await page.getByRole("button", { name: `更正 ${openingEventId}` }).click();
			await expect(page.getByText(`更正 ${openingEventId}`, { exact: true })).toBeVisible();
			await page.getByLabel("总额").fill("120000");
			await page.getByLabel("备注").fill("system browser correction");
			const browserCorrection = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/manual/accounts/system-manual/corrections`,
			);
			await page.getByRole("button", { name: "追加更正事件" }).click();
			const correctionResponse = await browserCorrection;
			expect(correctionResponse.status()).toBe(201);
			const correctionPayload = (await correctionResponse.json()) as Record<string, unknown>;
			expect(objectField(objectField(correctionPayload, "data"), "event")).toMatchObject({
				corrects_event_id: openingEventId,
				note: "system browser correction",
			});
			await expect(page.getByText("更正事件已追加；原记录保持不变")).toBeVisible();
			await expect(
				page.locator("article").getByText("system browser correction", { exact: true }),
			).toBeVisible();

			await page.getByRole("button", { name: `冲正 ${buyEventId}` }).click();
			await page.getByLabel("冲正原因").fill("system browser reversal");
			const browserReversal = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/manual/accounts/system-manual/reversals`,
			);
			await page.getByRole("button", { name: "确认追加冲正" }).click();
			const reversalResponse = await browserReversal;
			expect(reversalResponse.status()).toBe(201);
			const reversalPayload = (await reversalResponse.json()) as Record<string, unknown>;
			expect(objectField(objectField(reversalPayload, "data"), "event")).toMatchObject({
				reverses_event_id: buyEventId,
				note: "system browser reversal",
			});
			await expect(page.getByText("冲正事件已追加；原记录仍可审计")).toBeVisible();
			await expect(page.locator("article").getByText("system browser reversal", { exact: true })).toBeVisible();

			const ledger = await expectJson(
				await request.get(
					`${apiOrigin}/api/v1/manual/accounts/system-manual/ledger?as_of=2026-09-04`,
					{ headers: contractHeaders },
				),
				200,
			);
			const ledgerData = objectField(ledger, "data");
			expect(arrayField(ledgerData, "events")).toHaveLength(4);
			const cash = objectField(objectField(ledgerData, "snapshot"), "cash");
			expect(Number(cash["available"])).toBe(120_000);

			await page.reload({ waitUntil: "networkidle" });
			await expect(page.getByText("system browser correction", { exact: true })).toBeVisible();
			await expect(page.getByText("system browser reversal", { exact: true })).toBeVisible();
			expect(browserErrors).toEqual([]);
		});

		test("executes, replays, reconciles, pauses, and recovers a paper session", async ({
			page,
			request,
		}) => {
			const account = await expectJson(
				await request.post(`${apiOrigin}/api/v1/paper/accounts`, {
					headers: contractHeaders,
					data: {
						account_id: "system-paper",
						name: "System Paper",
						opened_at: "2026-09-04T00:00:00Z",
						trade_date: "2026-09-04",
						initial_cash: "100000",
						idempotency_key: "system-paper-create",
					},
				}),
				201,
			);
			expect(objectField(account, "data")).toMatchObject({
				account_id: "system-paper",
				account_kind: "paper",
				status: "created",
			});

			const session = await expectJson(
				await request.post(`${apiOrigin}/api/v1/paper/sessions`, {
					headers: contractHeaders,
					data: {
						session_id: "system-paper-session",
						account_id: "system-paper",
						strategy_id: "system-strategy",
						trade_date: "2026-09-04",
						idempotency_key: "system-paper-session-create",
						start_immediately: true,
					},
				}),
				201,
			);
			expect(objectField(session, "data")).toMatchObject({
				action: "start",
				session: { session_id: "system-paper-session", status: "running" },
			});

			const browserErrors = captureBrowserErrors(page);
			await page.goto(
				"/portfolio/paper?account_id=system-paper&session_id=system-paper-session&as_of=2026-09-04",
				{ waitUntil: "networkidle" },
			);
			await expect(page.getByText("PAPER 模拟账户")).toBeVisible();
			const browserOrder = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/paper/sessions/system-paper-session/orders`,
			);
			await page.getByRole("button", { name: "提交模拟订单" }).click();
			const orderResponse = await browserOrder;
			expect(orderResponse.status()).toBe(201);
			const orderPayload = (await orderResponse.json()) as Record<string, unknown>;
			const orderReceipt = objectField(orderPayload, "data");
			const orderId = stringField(orderReceipt, "order_id");
			expect(orderReceipt).toMatchObject({
				status: "created",
				order_status: "filled",
				ledger_event_id: expect.any(String),
			});
			await expect(page.getByText(/模拟成交已持久化/u)).toBeVisible();

			const browserReconcile = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/paper/sessions/system-paper-session/reconcile`,
			);
			await page.getByRole("button", { name: "日终对账" }).click();
			const reconciliationResponse = await browserReconcile;
			expect(reconciliationResponse.status()).toBe(200);
			const reconciliationPayload = (await reconciliationResponse.json()) as Record<string, unknown>;
			expect(objectField(reconciliationPayload, "data")).toMatchObject({
				balanced: true,
				fill_count: 1,
				ledger_fill_count: 1,
			});
			await expect(page.getByText("日终对账通过：1/1 笔成交已入账")).toBeVisible();
			await expect(page.getByText("日终已平衡", { exact: true })).toBeVisible();

			const browserRecover = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/paper/sessions/system-paper-session/recover`,
			);
			await page.getByRole("button", { name: "恢复账本缺口" }).click();
			const recoveredResponse = await browserRecover;
			expect(recoveredResponse.status()).toBe(200);
			const recoveredPayload = (await recoveredResponse.json()) as Record<string, unknown>;
			expect(objectField(recoveredPayload, "data")).toMatchObject({
				recovered_execution_count: expect.any(Number),
			});
			await expect(page.getByText(/恢复检查完成：\d+ 条执行记录已核验/u)).toBeVisible();

			const browserPause = page.waitForResponse(
				(response) =>
					response.request().method() === "POST" &&
					response.url() === `${apiOrigin}/api/v1/paper/sessions/system-paper-session/pause`,
			);
			await page.getByRole("button", { name: "暂停会话" }).click();
			const pausedResponse = await browserPause;
			expect(pausedResponse.status()).toBe(200);
			const pausedPayload = (await pausedResponse.json()) as Record<string, unknown>;
			expect(objectField(pausedPayload, "data")).toMatchObject({
				session: { status: "paused", revision: 2 },
			});
			await expect(page.getByText("PAUSED", { exact: true })).toBeVisible();

			const persistedSession = await expectJson(
				await request.get(`${apiOrigin}/api/v1/paper/sessions/system-paper-session`, {
					headers: contractHeaders,
				}),
				200,
			);
			expect(objectField(persistedSession, "data")).toMatchObject({
				session: { status: "paused", revision: 2 },
				latest_reconciliation: { balanced: true, fill_count: 1, ledger_fill_count: 1 },
			});

			await page.goto(
				"/portfolio/paper?account_id=system-paper&session_id=system-paper-session&as_of=2026-09-04",
				{ waitUntil: "networkidle" },
			);
			await expect(page.getByText("PAPER 模拟账户")).toBeVisible();
			await expect(
				page.getByText("system-paper", { exact: true }),
			).toBeVisible();
			await expect(page.getByText("PAUSED", { exact: true })).toBeVisible();
			await expect(page.getByText("日终已平衡", { exact: true })).toBeVisible();
			await expect(page.getByText(orderId, { exact: true })).toBeVisible();
			expect(browserErrors).toEqual([]);
		});

		test("exposes empty research control-plane truth without fabricated live results", async ({
			request,
		}) => {
			for (const path of [
				"/api/v1/research/experiments",
				"/api/v1/research/reviews",
			] as const) {
				const payload = await expectJson(
					await request.get(`${apiOrigin}${path}`, {
						headers: contractHeaders,
					}),
					200,
				);
				expect(arrayField(payload, "data")).toEqual([]);
			}
		});
	});

import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];
if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");

test.use({ timezoneId: "Asia/Shanghai" });

test("approved ETF target fills once through the real Paper ledger", async ({
	page,
	request,
}) => {
	const fixtureResponse = await request.get(
		`${apiOrigin}/system-fixture/etf-paper`,
	);
	expect(fixtureResponse.ok()).toBe(true);
	const fixture = (await fixtureResponse.json()) as {
		signal_reference: string;
		execution_reference: string;
		market: string;
		account_id: string;
	};
	await page.goto("/markets");
	const workspace = page.locator('[data-info-unit="etf-candidates"]');
	await workspace.getByLabel("研究日期").fill("2026-09-01");
	await workspace.getByLabel("知识截止").fill("2026-09-01T17:00");
	await workspace.getByLabel("来源快照").selectOption(fixture.signal_reference);
	await workspace.getByLabel("指数暴露").fill("000300.SH");
	await expect(
		workspace.getByRole("checkbox", { name: /沪深300ETF-Paper验收/ }),
	).toBeVisible();
	await workspace
		.getByRole("checkbox", { name: /沪深300ETF-Paper验收/ })
		.check();
	await workspace.getByLabel("现金比例").fill("0.5");
	await workspace.getByLabel("配置理由").fill("recorded acceptance target");
	await workspace.getByLabel("权重模式").selectOption("manual");
	await workspace.getByLabel("ETF 2000101 权重").fill("0.8");
	await workspace.getByRole("button", { name: "保存候选版本" }).click();
	await expect(workspace.getByRole("alert")).toContainText("保存失败");
	await expect(workspace.getByLabel("ETF 2000101 权重")).toHaveValue("0.8");
	await workspace.getByLabel("权重模式").selectOption("equal");
	await workspace.getByRole("button", { name: "保存候选版本" }).click();
	await expect(workspace.getByText(/已保存 etf-allocation-/)).toBeVisible();
	const allocationId = new URL(page.url()).searchParams.get("etfAllocation");
	const versionId = new URL(page.url()).searchParams.get("etfVersion");
	expect(allocationId).toBeTruthy();
	expect(versionId).toBeTruthy();
	await workspace.getByLabel("审查人").fill("browser reviewer");
	await workspace.getByLabel("审查理由").fill("approved recorded target");
	await workspace.getByRole("button", { name: "提交审查" }).click();
	await workspace.getByRole("button", { name: "研究审查通过" }).click();
	await expect(workspace.getByText(/review_approved/)).toBeVisible();
	await workspace.getByLabel("Paper 账户").selectOption(fixture.account_id);
	await workspace.getByLabel("下一交易日").fill("2026-09-02");
	await workspace.getByLabel("Paper 授权人").fill("browser operator");
	await workspace
		.getByLabel("Paper 授权理由")
		.fill("controlled recorded execution");
	await workspace.getByRole("button", { name: "授权此版本进入 Paper" }).click();
	await workspace.getByRole("button", { name: "创建 Paper 会话" }).click();
	await expect(workspace.getByText(/Paper 会话 .+ 已创建/)).toBeVisible();
	const sessionId = new URL(page.url()).searchParams.get("paperSession");
	expect(sessionId).toBeTruthy();
	await page.reload();
	await expect(workspace.getByText(/Paper 会话 .+ 已创建/)).toBeVisible();
	await workspace.getByLabel("执行日证据截止时间").fill("2026-09-03T16:00");
	await workspace
		.getByLabel("执行日 ETF 参考快照 ID")
		.fill(fixture.execution_reference);
	await workspace.getByLabel("执行日 ETF 行情快照 ID").fill(fixture.market);
	await workspace.getByLabel("执行日证据截止时间").fill("2026-09-03T14:00");
	await workspace.getByRole("button", { name: "按已批准意图模拟成交" }).click();
	await expect(workspace.getByRole("alert")).toContainText("Paper 执行失败");
	await workspace.getByLabel("执行日证据截止时间").fill("2026-09-03T16:00");
	await workspace.getByRole("button", { name: "按已批准意图模拟成交" }).click();
	await expect(workspace.getByText(/工具 2000101：filled/)).toBeVisible();
	const ledger = await request.get(
		`${apiOrigin}/api/v1/paper/accounts/${fixture.account_id}/ledger?as_of=2026-09-02`,
	);
	expect(ledger.status()).toBe(200);
	const firstEvents = ((await ledger.json()) as { data: { events: unknown[] } })
		.data.events;
	expect(firstEvents).toHaveLength(2);
	await workspace.getByRole("button", { name: "按已批准意图模拟成交" }).click();
	const replay = await request.get(
		`${apiOrigin}/api/v1/paper/accounts/${fixture.account_id}/ledger?as_of=2026-09-02`,
	);
	expect(
		((await replay.json()) as { data: { events: unknown[] } }).data.events,
	).toEqual(firstEvents);
	await workspace.getByLabel("配置理由").fill("recorded acceptance revision");
	await workspace.getByRole("button", { name: "保存候选版本" }).click();
	await expect
		.poll(() => new URL(page.url()).searchParams.get("etfVersion"))
		.not.toBe(versionId);
	const originalUrl = new URL(page.url());
	originalUrl.searchParams.set("etfVersion", versionId ?? "");
	await page.goto(originalUrl.toString());
	await expect(workspace.getByLabel("配置理由")).toHaveValue(
		"recorded acceptance target",
	);
	await workspace.getByRole("link", { name: "查看 Paper 账户" }).click();
	await expect(page.getByText("PAPER 模拟账户")).toBeVisible();
	expect(page.url()).toContain(`session_id=${sessionId}`);
});

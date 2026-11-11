import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");
const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

// 与 tests/system/fixtures/watchlist_journey_app.py 保持同一身份。
const FAR_STOCK_ID = 3_000_115;
const FAR_STOCK_NAME = "目录样本股115";
const ETF_NAME = "样本ETF观察";
const DELISTED_ID = 3_000_121;
const DELISTED_NAME = "已退市样本";
const WATCHLIST_STORAGE_KEY = "ditto.market-watchlist.v1";

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function openAddOverlay(page: Page): Promise<void> {
	await page.goto(`${webOrigin}/markets/watchlist`);
	await page.getByRole("button", { name: "添加标的" }).click();
}

async function searchAndAssertCandidate(
	page: Page,
	term: string,
	candidateName: string,
	{ submitViaKeyboard = false }: { readonly submitViaKeyboard?: boolean } = {},
): Promise<void> {
	const input = page.getByLabel("搜索代码或名称");
	await input.fill(term);
	// 键盘路径（Enter 提交）与按钮路径至少各验收一次。
	if (submitViaKeyboard) {
		await input.press("Enter");
	} else {
		await page.getByRole("button", { name: "检索" }).click();
	}
	await expect(page.getByRole("button", { name: `加入自选 ${candidateName}` })).toBeVisible();
}

test.describe.serial("watchlist name/code search and durable reopen over a seeded production API", () => {
	test("search beyond the first catalog page, save, reload and reopen by exact identity", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		await openAddOverlay(page);

		// 保存对象在默认目录首页（limit 100）之外：只能靠检索与精确身份解析触达。
		const firstPage = await page.request.get(`${apiOrigin}/api/v1/metadata/instruments`, {
			params: { limit: 100, offset: 0 },
			headers: { "X-Ditto-API-Contract-Version": "v1" },
		});
		expect(firstPage.status()).toBe(200);
		const firstPageIds = ((await firstPage.json()).data as Array<{ instrument_id: number }>).map(
			(item) => item.instrument_id,
		);
		expect(firstPageIds).not.toContain(FAR_STOCK_ID);

		// 名称检索（Enter 键盘提交）→ 选择 → 保存。
		await searchAndAssertCandidate(page, FAR_STOCK_NAME, FAR_STOCK_NAME, { submitViaKeyboard: true });
		await page.getByRole("button", { name: `加入自选 ${FAR_STOCK_NAME}` }).click();
		await expect(page.getByRole("link", { name: FAR_STOCK_NAME })).toBeVisible();
		await expect(page.locator(`[data-row-state="active"]`)).toContainText("600115 · SSE");

		// 刷新后重开：localStorage 持久化 + 每个对象经真实单对象接口重新解析。
		await page.reload();
		await expect(page.getByRole("link", { name: FAR_STOCK_NAME })).toBeVisible();
		await expect(page.locator('[data-info-unit="watchlist-row"]')).toHaveCount(1);
		const stored = await page.evaluate(
			(key: string) => window.localStorage.getItem(key),
			WATCHLIST_STORAGE_KEY,
		);
		expect(JSON.parse(stored ?? "[]")).toEqual([FAR_STOCK_ID]);
		expect(browserErrors).toEqual([]);
	});

	test("code search reaches the same identity through ticker", async ({ page }) => {
		await openAddOverlay(page);
		await searchAndAssertCandidate(page, "510777", ETF_NAME);
		await page.getByRole("button", { name: `加入自选 ${ETF_NAME}` }).click();
		await expect(page.getByRole("link", { name: ETF_NAME })).toBeVisible();
	});

	test("no-match search states the empty result instead of fabricating candidates", async ({ page }) => {
		await openAddOverlay(page);
		await page.getByLabel("搜索代码或名称").fill("不存在的标的字样");
		await page.getByRole("button", { name: "检索" }).click();
		await expect(page.getByText(/没有匹配的标的/)).toBeVisible();
		await expect(page.getByRole("button", { name: /^加入自选/ })).toHaveCount(0);
	});

	test("large result sets show total evidence and load every match", async ({ page }) => {
		await openAddOverlay(page);
		// 「目录样本股」命中 fixture 全部 120 只股票，远超单页 20。
		await page.getByLabel("搜索代码或名称").fill("目录样本股");
		await page.getByRole("button", { name: "检索" }).click();
		const evidence = page.getByTestId("watchlist-search-evidence");
		await expect(evidence).toContainText("共 120 项 · 已加载 20");
		await expect(page.getByRole("button", { name: /^加入自选/ })).toHaveCount(20);

		// 全部命中可达：加载更多按 offset 续载下一页。
		await page.getByRole("button", { name: "加载更多" }).click();
		await expect(page.getByRole("button", { name: /^加入自选/ })).toHaveCount(40);
		await expect(evidence).toContainText("共 120 项 · 已加载 40");
	});

	test("unknown saved object is explained, never silently dropped or replaced", async ({ page }) => {
		await page.addInitScript(
			(ids: string) => {
				window.localStorage.setItem("ditto.market-watchlist.v1", ids);
			},
			"[9999999]",
		);
		await page.goto(`${webOrigin}/markets/watchlist`);
		const unknownRow = page.locator('[data-info-unit="watchlist-row"][data-row-state="unknown"]');
		await expect(unknownRow).toBeVisible();
		await expect(unknownRow).toContainText("目录中未找到");
		await expect(unknownRow).toContainText("9999999");
		await page.getByRole("button", { name: "移除 未知标的 9999999" }).click();
		await expect(page.getByText("尚未添加标的")).toBeVisible();
	});

	test("delisted saved object stays visible with an explicit delisted state", async ({ page }) => {
		await page.addInitScript(
			(ids: string) => {
				window.localStorage.setItem("ditto.market-watchlist.v1", ids);
			},
			JSON.stringify([DELISTED_ID]),
		);
		await page.goto(`${webOrigin}/markets/watchlist`);
		const delistedRow = page.locator('[data-info-unit="watchlist-row"][data-row-state="delisted"]');
		await expect(delistedRow).toBeVisible();
		await expect(delistedRow).toContainText(DELISTED_NAME);
		await expect(delistedRow.getByText("已退出")).toBeVisible();
	});

	test("returning from the instrument page restores the watchlist context", async ({ page }) => {
		await page.addInitScript(
			(ids: string) => {
				window.localStorage.setItem("ditto.market-watchlist.v1", ids);
			},
			JSON.stringify([FAR_STOCK_ID]),
		);
		await page.goto(`${webOrigin}/markets/watchlist`);
		await expect(page.getByRole("link", { name: FAR_STOCK_NAME })).toBeVisible();

		// 从自选进入标的页：对象身份一致；返回后清单上下文（对象集合）保留。
		await page.getByRole("link", { name: FAR_STOCK_NAME }).click();
		await expect(page).toHaveURL(new RegExp(`/instruments/${FAR_STOCK_ID}`));
		await expect(page.getByText(FAR_STOCK_NAME).first()).toBeVisible();
		await page.goBack();
		await expect(page).toHaveURL(/\/markets\/watchlist/);
		await expect(page.getByRole("link", { name: FAR_STOCK_NAME })).toBeVisible();
		const stored = await page.evaluate(
			(key: string) => window.localStorage.getItem(key),
			WATCHLIST_STORAGE_KEY,
		);
		expect(JSON.parse(stored ?? "[]")).toEqual([FAR_STOCK_ID]);
	});
});

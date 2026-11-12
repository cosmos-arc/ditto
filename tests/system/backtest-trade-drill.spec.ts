import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

// fixture 常量（tests/system/fixtures/backtest_nav_app.py）：真实引擎产物，
// 118 笔成交 + 164 条 pre-trade 审计记录，标的 2001001/2001002 有全区间日 K。
const RUN_ID = "sys-fx-nav-001";

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
	const accessibility = await new AxeBuilder({ page }).analyze();
	const serious = accessibility.violations.filter((violation) =>
		["critical", "serious"].includes(violation.impact ?? ""),
	);
	expect(serious).toEqual([]);
}

test.describe
	.serial("backtest trade drill-down chain over a real engine run", () => {
		test("report row → evidence drawer → instrument chart focus, keyboard reachable end to end", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);

			// 进入成交 tab
			await page.getByRole("tab", { name: "成交" }).click();
			const firstEvidence = page.locator("[data-testid^='trade-evidence-']").first();
			await expect(firstEvidence).toBeVisible();

			// 键盘可达：Tab 聚焦到首个「查证据」按钮并回车打开抽屉
			const firstRowButton = firstEvidence;
			await firstRowButton.focus();
			await page.keyboard.press("Enter");
			await expect(screenDrawer(page)).toBeVisible();

			// 抽屉内：精确成交身份 + 按标的/日期过滤的 pre-trade 审计证据
			await expect(screenDrawer(page).getByText(/Entry/)).toBeVisible();
			const rows = page.getByTestId("trade-evidence-rows");
			await expect(rows).toBeVisible();
			expect((await rows.textContent()) ?? "").toMatch(/buy|sell/);

			// 抽屉内跳转链接携带跨域上下文（对象/原因/知识时间/方向），键盘可达
			const buyLink = page.locator("[data-testid^='drill-link-buy-']").first();
			const href = (await buyLink.getAttribute("href")) ?? "";
			expect(href).toContain(`/instruments/`);
			expect(href).toContain("tab=chart");
			expect(href).toContain("focusDate=");
			expect(href).toContain(`drillRunId=${RUN_ID}`);
			expect(href).toContain("drillAsOf=");
			expect(href).toContain("drillDirection=buy");
			await buyLink.focus();
			await page.keyboard.press("Enter");

		// 落地标的页 K 线：drill-focus 状态条 + 定位 marker + as_of 水位线一致
		const chip = page.locator("[data-state='drill-focus']").first();
		await expect(chip).toBeVisible();
		expect((await chip.textContent()) ?? "").toContain(RUN_ID);
		expect((await chip.textContent()) ?? "").toContain("买入");

		const host = page.locator("[data-chart-interaction-contract^='instrument-candles-']");
		await expect(host).toBeVisible();
		await expect(host).toHaveAttribute("data-chart-marker-times", /\d+/);
		await expect(host).toHaveAttribute("data-chart-as-of", /\d+/);
		// 定位生效：目标时点在可视窗口附近（而非 fitContent 的首尾全览）
		await expect
			.poll(async () => (await host.getAttribute("data-chart-visible-range")) ?? "")
			.not.toBe("");

		// 定位标的与日期后可以返回：回程入口把用户带回源运行工作面（键盘可达）
		const backLink = page.getByRole("link", { name: `返回回测 ${RUN_ID}` });
		await backLink.focus();
		await page.keyboard.press("Enter");
		await expect(page.getByTestId("backtest-detail-meta")).toBeVisible();
		await expect(page.getByTestId("backtest-detail-identity")).toContainText(RUN_ID);

		expect(browserErrors).toEqual([]);
	});

		test("sell drill marks the exit date with a below-bar marker", async ({ page }) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);
			await page.getByRole("tab", { name: "成交" }).click();
			const firstEvidence = page.locator("[data-testid^='trade-evidence-']").first();
			await firstEvidence.click();
			const sellLink = page.locator("[data-testid^='drill-link-sell-']").first();
			const href = (await sellLink.getAttribute("href")) ?? "";
			expect(href).toContain("drillDirection=sell");
			const focusMatch = href.match(/focusDate=([0-9-]+)/);
			expect(focusMatch).not.toBeNull();
			await sellLink.click();

			const chip = page.locator("[data-state='drill-focus']").first();
			await expect(chip).toBeVisible();
			expect((await chip.textContent()) ?? "").toContain("卖出");

			// marker 时间 = 卖出定位日（UTC 日锚定）
			const host = page.locator("[data-chart-interaction-contract^='instrument-candles-']");
			await expect(host).toBeVisible();
			const expectedTime = Date.parse(`${focusMatch![1]}T00:00:00Z`) / 1000;
		await expect(host).toHaveAttribute("data-chart-marker-times", String(expectedTime));

		await expectNoSeriousAccessibilityViolations(page);
		expect(browserErrors).toEqual([]);
	});

	test("trades tab exports a CSV with the same rows and identity as the displayed table", async ({ page }) => {
		const browserErrors = captureBrowserErrors(page);
		await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);
		await page.getByRole("tab", { name: "成交" }).click();

		const tableRows = await page.locator("[data-info-unit='trade-record']").count();
		expect(tableRows).toBeGreaterThan(0);

		const exportButton = page.getByRole("button", { name: "导出成交 CSV" });
		await exportButton.focus();
		const downloaded = page.waitForEvent("download");
		await page.keyboard.press("Enter");
		const download = await downloaded;
		expect(download.suggestedFilename()).toBe(`${RUN_ID}-trades.csv`);
		const path = await download.path();
		if (!path) throw new Error("trades CSV download missing");
		const csv = await readFile(path, "utf8");
		// 身份注释 + 与表格同值的行：行数（去身份注释与表头）与页面表格行数一致
		expect(csv).toContain(`# run_id=${RUN_ID}`);
		const dataRows = csv
			.split("\n")
			.filter((line) => line && !line.startsWith("#") && !line.startsWith("trade_date,"));
		expect(dataRows).toHaveLength(tableRows);
		// 每行都是日期/instrument 开头的结构化数据（与表格同源同口径）
		for (const row of dataRows) {
			expect(row).toMatch(/^\d{4}-\d{2}-\d{2},\d+,(buy|sell|long|short),/);
		}

		expect(browserErrors).toEqual([]);
	});
});

function screenDrawer(page: Page) {
	return page.locator("[role='dialog'], [data-state='open']").filter({ hasText: "成交证据下钻" }).first();
}

test.describe("drill banner integrity at capture state", () => {
	// 视觉门回归锁：状态条行高由内容撑开（无固定高度/行内裁切），
	// 且落地瞬间完整落在最近滚动祖先内（不呈现半裁形态）。
	test("drill strip keeps full text height across viewports", async ({ browser }) => {
		for (const [label, size] of [
			["standard", { width: 1512, height: 900 }],
			["compact", { width: 1366, height: 768 }],
			["narrow", { width: 1024, height: 768 }],
		] as const) {
			const context = await browser.newContext({ viewport: size });
			const page = await context.newPage();
			try {
				const browserErrors = captureBrowserErrors(page);
				await page.goto(`${webOrigin}/research/backtests/${RUN_ID}`);
				await page.getByRole("tab", { name: "成交" }).click();
				await page.locator("[data-testid^='trade-evidence-']").first().click();
				await page.locator("[data-testid^='drill-link-buy-']").first().click();
				const banner = page.locator("[data-state='drill-focus']");
				await banner.waitFor({ timeout: 20000 });
				// 等 K 线宿主渲染：内容增高后的真实形态才是被裁风险形态
				await page
					.locator("[data-chart-interaction-contract^='instrument-candles-']")
					.waitFor({ timeout: 20000 });

				const state = await banner.evaluate((element) => {
					const box = element.getBoundingClientRect();
					let clippedBy = "";
					let node: Element | null = element.parentElement;
					while (node) {
						const style = window.getComputedStyle(node);
						const clips =
							style.overflowY === "hidden" ||
							style.overflow === "hidden" ||
							/(auto|scroll)/.test(style.overflowY);
						if (clips) {
							const nodeBox = node.getBoundingClientRect();
							if (box.top < nodeBox.top - 1 || box.bottom > nodeBox.bottom + 1) {
								clippedBy = `${node.tagName}.${String(node.className).slice(0, 50)}`;
								break;
							}
						}
						node = node.parentElement;
					}
					const lineHeight = Number.parseFloat(window.getComputedStyle(element).lineHeight);
					return {
						rectH: box.height,
						scrollH: element.scrollHeight,
						clientH: element.clientHeight,
						lineHeight,
						clippedBy,
					};
				});
				expect(state.rectH, `strip height @${label}`).toBeGreaterThanOrEqual(24);
				expect(state.rectH, `content-driven height @${label}`).toBeGreaterThanOrEqual(state.lineHeight + 16);
				expect(state.scrollH - state.clientH, `no inner clip @${label}`).toBeLessThanOrEqual(2);
				expect(state.clippedBy, `fully inside clip boxes at capture @${label}`).toBe("");
				expect(browserErrors).toEqual([]);
			} finally {
				await context.close();
			}
		}
	});
});

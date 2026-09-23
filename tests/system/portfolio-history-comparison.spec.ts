import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * #263 三组合共同区间比较浏览器旅程：真实 fixture（portfolio_history_app）
 * 经生产 three-leg 查询产出共同窗口；验证选择、缺口、重试恢复与导出。
 */

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

test.use({ acceptDownloads: true });

interface JourneyWindow {
	readonly start: string;
	readonly end: string;
	readonly model_return: string;
	readonly paper_return: string;
	readonly manual_return: string;
}

interface JourneyIdentity {
	readonly strategy_id: string;
	readonly paper_account_id: string;
	readonly paper_session_id: string;
	readonly gap_paper_account_id: string;
	readonly gap_paper_session_id: string;
	readonly manual_account_id: string;
	readonly snapshot_id: string;
	readonly start_date: string;
	readonly end_date: string;
	readonly knowledge_cutoff: string;
	readonly frontend_path?: string;
	readonly expected_window: JourneyWindow;
	readonly expected_gap_window: JourneyWindow;
}

test.describe.serial("portfolio history comparison over the live fixture", () => {
	test("selects entities, compares the common window, exports, and recovers", async ({ page, request }) => {
		test.setTimeout(120_000);
		const browserErrors = captureBrowserErrors(page);
		const fixture = await (await request.get(`${apiOrigin}/system-fixture/portfolio-history`)).json();
		const identity = fixture.identity as JourneyIdentity;

		await page.goto(identity.frontend_path ?? "/portfolio/?mode=comparison");
		const panel = page.getByTestId("history-comparison-panel");
		await expect(panel).toBeVisible();

		// 选择器由真实目录填充（策略/账户/会话），无需手填内部 ID。
		const modelStrategy = page.getByLabel("Model 策略");
		await expect(modelStrategy).toHaveValue(identity.strategy_id);
		await expect(page.getByLabel("Paper 账户")).toHaveValue(identity.paper_account_id);
		await expect(page.getByLabel("Paper 会话")).toHaveValue(identity.paper_session_id);
		await expect(page.getByLabel("Manual 账户")).toHaveValue(identity.manual_account_id);

		await page.getByLabel("比较开始日期").fill(identity.start_date);
		await page.getByLabel("比较结束日期").fill(identity.end_date);
		await page.getByLabel("比较知识截止").fill(identity.knowledge_cutoff);
		await page.getByLabel("比较价格快照").fill(identity.snapshot_id);

		// 一次性注入失败 → 真实浏览器里走错误与重试恢复。
		await request.post(`${apiOrigin}/system-fixture/portfolio-history/arm-failure`);
		await page.getByTestId("history-comparison-submit").click();
		const failureAlert = page.getByRole("alert").filter({ hasText: "共同区间比较失败" });
		await expect(failureAlert).toBeVisible();
		await page.getByRole("button", { name: "重试" }).click();

		// 共同窗口：Model +21.00% / Paper +10.50% / Manual +16.80%。
		const result = page.getByTestId("history-comparison-result");
		await expect(result).toBeVisible();
		const window = identity.expected_window;
		await expect(page.getByTestId("history-comparison-window-return-model")).toContainText(
			window.model_return,
		);
		await expect(page.getByTestId("history-comparison-window-return-paper")).toContainText(
			window.paper_return,
		);
		await expect(page.getByTestId("history-comparison-window-return-manual")).toContainText(
			window.manual_return,
		);
		await expect(result).toContainText(`${window.start} ~ ${window.end}`);
		await expect(result).toContainText("history-comparison:sha256:");
		await expect(result).toContainText("twr-linked-v1");
		for (const kind of ["model", "paper", "manual"]) {
			await expect(page.getByTestId(`history-comparison-line-${kind}`)).toHaveAttribute(
				"points",
				/.+/,
			);
		}
		await expect(result).toContainText("1.2100");
		const paperLeg = page.getByTestId("history-comparison-leg-paper");
		await expect(paperLeg).toContainText("paper-history:sha256:");
		await expect(paperLeg).toContainText("account-ledger:sha256:");

		// 导出与图表引用同一后端结果身份：CSV 与 PNG 各自触发下载。
		const csvDownload = page.waitForEvent("download");
		await page.getByTestId("history-comparison-export-csv").click();
		const csv = await csvDownload;
		expect(csv.suggestedFilename()).toContain("history-comparison");
		const pngDownload = page.waitForEvent("download");
		await page.getByTestId("history-comparison-export-png").click();
		const png = await pngDownload;
		expect(png.suggestedFilename()).toMatch(/\.png$/);

		// 缺口旅程：切到只持有 510300 的模拟账户，03-04 无效收盘价把共同
		// 窗口截断在 03-03，收益变为两位个位数百分比。
		await page.getByLabel("Paper 账户").selectOption(identity.gap_paper_account_id);
		await expect(page.getByLabel("Paper 会话")).toHaveValue(identity.gap_paper_session_id);
		await page.getByTestId("history-comparison-submit").click();
		const gapWindow = identity.expected_gap_window;
		await expect(page.getByTestId("history-comparison-window-return-model")).toContainText(
			gapWindow.model_return,
		);
		await expect(page.getByTestId("history-comparison-window-return-paper")).toContainText(
			gapWindow.paper_return,
		);
		await expect(page.getByTestId("history-comparison-window-return-manual")).toContainText(
			gapWindow.manual_return,
		);
		await expect(page.getByTestId("history-comparison-leg-paper")).toContainText("缺口 1");

		const accessibility = await new AxeBuilder({ page }).analyze();
		const serious = accessibility.violations.filter((violation) =>
			["critical", "serious"].includes(violation.impact ?? ""),
		);
		expect(serious).toEqual([]);
		expect(browserErrors).toEqual([]);
	});
});

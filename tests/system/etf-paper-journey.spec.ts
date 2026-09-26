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
	await workspace.getByLabel("复盘账户").selectOption(`paper:${fixture.account_id}`);
	await workspace.getByRole("link", { name: "查看配置与账户复盘" }).click();
	const review = page.getByRole("region", { name: "ETF 配置复盘" });
	await expect(review.getByLabel("复盘配置版本")).toHaveValue(versionId ?? "");
	await review.getByLabel("复盘账本日期").fill("2026-09-02");
	await expect(review.getByText(/Paper 模拟成交账本/)).toBeVisible();
	await expect(review.getByText(/#2000101：实际/)).toBeVisible();
	await expect(review.getByText(/缺少同日价格证据，无法计算实际权重/)).toBeVisible();
	const now = new Date();
	const reviewDay = new Date(now.getTime() + 86_400_000).toISOString().slice(0, 10);
	await review.getByLabel("复盘账本日期").fill(reviewDay);
	await review.getByLabel("复盘价格快照").fill(fixture.market);
	await review.getByLabel("复盘知识截止").fill("2026-09-03T14:00");
	// The pre-evidence cutoff hides target details and fails the valuation.
	await expect(review.getByText(/所选知识截止早于该版本/)).toBeVisible();
	await expect(review.getByText(/估值失败：/)).toBeVisible();
	await review.getByLabel("复盘知识截止").fill(
		await page.evaluate(() => {
			const instant = new Date();
			return new Date(instant.getTime() + 60_000 - instant.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
		}),
	);
	const valuationResponse = await request.get(
		`${apiOrigin}/api/v1/portfolio/etf-allocations/${allocationId}/versions/${versionId}/review`,
		{ params: { account_kind: "paper", account_id: fixture.account_id, as_of: reviewDay, knowledge_cutoff: now.toISOString(), source_snapshot_ids: fixture.market } },
	);
	expect(valuationResponse.status(), await valuationResponse.text()).toBe(200);
	const valuationData = (await valuationResponse.json()) as {
		data: {
			target: { positions: { weight: string }[]; cash_weight: string };
			actual: { positions: { weight: string }[]; cash_weight: string };
			actual_exposure: Record<string, string>;
			unknown_exposure_instrument_ids: number[];
		};
	};
	expect(Number(valuationData.data.target.positions[0]?.weight)).toBeCloseTo(0.5, 6);
	expect(Number(valuationData.data.actual.positions[0]?.weight)).toBeGreaterThan(0.5);
	expect(valuationData.data.actual_exposure).toEqual({});
	expect(valuationData.data.unknown_exposure_instrument_ids).toContain(2000101);
	const valued = review.getByRole("region", { name: "ETF 目标与实际估值" });
	await expect(valued.getByText(/ETF #2000101：目标/)).toBeVisible();
	await expect(valued.getByText(/已知同指数实际暴露：未知/)).toBeVisible();
	await expect(valued.getByText(/指数归属未知的实际持仓：2000101/)).toBeVisible();
	await expect(valued.getByText(/目标现金 .*实际现金 .*现金差异/)).toBeVisible();
	await expect(page.getByTestId("history-comparison-submit")).toBeDisabled();
	await page.reload();
	await expect(review.getByLabel("复盘配置版本")).toHaveValue(versionId ?? "");
	await expect(review.getByLabel("复盘账户")).toHaveValue(`paper:${fixture.account_id}`);
	await expect(review.getByLabel("复盘账本日期")).toHaveValue(reviewDay);
	await expect(valued.getByText(/ETF #2000101：目标/)).toBeVisible();
	await page.goBack();
	await expect(review.getByLabel("复盘配置版本")).toHaveValue(versionId ?? "");
	await review.getByRole("link", { name: "返回 ETF 配置" }).click();
	await expect(workspace.getByLabel("已保存版本")).toHaveValue(versionId ?? "");
});

test("restricted ETF cannot enter Paper and returns to tool selection", async ({
	page,
	request,
}) => {
	const fixtureResponse = await request.get(
		`${apiOrigin}/system-fixture/etf-paper`,
	);
	expect(fixtureResponse.ok()).toBe(true);
	const fixture = (await fixtureResponse.json()) as {
		signal_reference: string;
		account_id: string;
	};
	await page.goto("/markets");
	const workspace = page.locator('[data-info-unit="etf-candidates"]');
	await workspace.getByLabel("研究日期").fill("2026-09-01");
	await workspace.getByLabel("知识截止").fill("2026-09-01T17:00");
	await workspace.getByLabel("来源快照").selectOption(fixture.signal_reference);
	await workspace.getByLabel("指数暴露").fill("000300.SH");
	await workspace.getByRole("checkbox", { name: /受限ETF-Paper验收/ }).check();
	await workspace.getByLabel("现金比例").fill("0.5");
	await workspace.getByLabel("配置理由").fill("restricted tool refusal");
	await workspace.getByRole("button", { name: "保存候选版本" }).click();
	await expect(workspace.getByText(/已保存 etf-allocation-/)).toBeVisible();
	await workspace.getByLabel("审查人").fill("browser reviewer");
	await workspace.getByLabel("审查理由").fill("research approval only");
	await workspace.getByRole("button", { name: "提交审查" }).click();
	await workspace.getByRole("button", { name: "研究审查通过" }).click();
	await workspace.getByLabel("Paper 账户").selectOption(fixture.account_id);
	await workspace.getByLabel("下一交易日").fill("2026-09-02");
	await workspace.getByLabel("Paper 授权人").fill("browser operator");
	await workspace
		.getByLabel("Paper 授权理由")
		.fill("check restriction at handoff");
	await workspace.getByRole("button", { name: "授权此版本进入 Paper" }).click();
	await workspace.getByRole("button", { name: "创建 Paper 会话" }).click();
	await expect(workspace.getByRole("alert")).toContainText(
		"not investable; choose alternatives",
	);
	await expect(
		workspace.getByRole("link", { name: "返回工具选择" }),
	).toHaveAttribute("href", "#etf-tool-selection");
	expect(new URL(page.url()).searchParams.has("paperSession")).toBe(false);
});

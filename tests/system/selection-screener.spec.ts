import { expect, test, type Page } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");
const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");
const API_HEADERS = { "X-Ditto-API-Contract-Version": "v1" };

// 与 tests/system/fixtures/selection_screener_app.py 保持同一身份：
// A 强动量（秩 1.0）、B 居中（0.667）、C 下跌（0.333）。
const STOCK_A = "筛选样本A";
const STOCK_B = "筛选样本B";
const STOCK_C = "筛选样本C";
const SPEC_ID = "screener-fixture";
// 固定决策时点为最近完整交易日收盘（服务端同一会话地板）。live 读模型
// 的知识截止由服务端按发起时刻签发，不能固定为过去时刻；同一策略条件
// 重复提交会各得一个固定运行身份（知识时刻不同），结果集一致。
const AS_OF = "2026-11-10T15:00";
const STOCK_A_ID = "1420001";
const STOCK_B_ID = "1420002";

test.describe.serial("visual conditions and factor weights produce saved fixed runs (#740)", () => {
	test("factor catalog loads with readable unit, lookback, and group metadata", async ({ page }) => {
		await page.goto(`${webOrigin}/markets/screener`);
		// 目录是条件构建的先决：可用后才能添加条件组。
		await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();
		// 全局口径说明可读（单位 + 缺失处理）。
		await expect(page.getByText(/截面分数秩 \(0,1\]/)).toBeVisible();
		await expect(page.getByText(/缺失的标的按缺证据排除/)).toBeVisible();

		await page.getByRole("button", { name: "添加条件组" }).click();
		const factorSelect = page.getByLabel("条件组 1 因子 1");
		await expect(factorSelect).toBeVisible();
		// 选择因子后展示元信息（描述 + 回看窗口）。
		await factorSelect.selectOption("momentum_1m");
		// 条件行与权重行共享元信息组件：断言至少一处完整呈现。
		await expect(
			page.getByText(/1-month price momentum \(20-day return\) · 回看 20 个交易日/).first(),
		).toBeVisible();
		// 键盘可达：因子选择聚焦后 Tab 依序到达算子与阈值输入。
		await factorSelect.focus();
		await page.keyboard.press("Tab");
		await expect(page.getByLabel("条件组 1 算子 1")).toBeFocused();
		await page.keyboard.press("Tab");
		await expect(page.getByLabel("条件组 1 阈值 1")).toBeFocused();
	});

	test("conditions and weights create a fixed run with candidate and exclusion evidence", async ({ page }) => {
		const browserErrors: string[] = [];
		page.on("pageerror", (error) => browserErrors.push(error.message));

		await page.goto(`${webOrigin}/markets/screener`);
		await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();

		// 表单：命名 spec、固定时间身份、放开流动性硬过滤。
		await page.getByLabel("spec_id").fill(SPEC_ID);
		await page.getByLabel("top_k（入选数量）").fill("2");
		await page.getByLabel("最小日均成交额（元）").fill("0");
		await page.getByLabel("决策时点 as_of").fill(AS_OF);

		// 条件组：momentum_1m ≥ 0.5（截面分数秩）。
		await page.getByRole("button", { name: "添加条件组" }).click();
		await page.getByLabel("条件组 1 因子 1").selectOption("momentum_1m");
		await page.getByLabel("条件组 1 算子 1").selectOption("gte");
		await page.getByLabel("条件组 1 阈值 1").fill("0.5");

		// 权重保持 momentum_1m=1（合格因子目录驱动）。
		await expect(page.getByLabel("因子 1", { exact: true })).toHaveValue("momentum_1m");

		await page.getByRole("button", { name: "创建运行" }).click();

		// 保存反馈区分可重跑条件（spec）与固定结果（run）两种身份。
		const feedback = page.getByRole("status").filter({ hasText: "已保存固定 SelectionRun" });
		await expect(feedback).toContainText(`可重跑条件 ${SPEC_ID}:1`);
		const runHash = (await feedback.textContent())?.match(/SelectionRun ([0-9a-f]{12})/)?.[1];
		expect(runHash).toBeTruthy();

		// 候选与贡献：A 第一、B 第二（截面秩即贡献值）。
		await expect(page.getByRole("link", { name: STOCK_A })).toBeVisible();
		await expect(page.getByRole("link", { name: STOCK_B })).toBeVisible();
		await expect(page.locator("tbody tr").first()).toContainText("#1");
		await expect(page.locator("tbody tr").nth(1)).toContainText("#2");

		// 排除证据链：C 因条件不满足被排除，理由带可读条件文本。
		await page.getByRole("tab", { name: /排除 1/ }).click();
		const exclusion = page.locator("article").filter({ hasText: STOCK_C });
		await expect(exclusion).toContainText("factor_condition_unsatisfied");
		await expect(exclusion).toContainText("momentum_1m>=0.5");

		// 同一策略条件重复提交：各自固定为一次运行（知识时刻不同 → 新
		// 身份），候选与排除结果一致——重复提交不报错、不静默合并。
		await page.getByRole("tab", { name: /入选 2/ }).click();
		await page.getByRole("button", { name: "创建运行" }).click();
		const fetchHistory = async () =>
			await page
				.request.get(`${apiOrigin}/api/v1/selections/runs?spec_id=${SPEC_ID}`, { headers: API_HEADERS })
				.then((response) => response.json())
				.then(
					(payload) =>
						payload.data as {
							run_id: string;
							candidates: { instrument_name: string; rank: number }[];
							exclusions: { reason_code: string }[];
						}[],
				);
		await expect.poll(() => fetchHistory().then((runs) => runs.length), { timeout: 15_000 }).toBe(2);
		const history = await fetchHistory();
		expect(new Set(history.map((run) => run.run_id)).size).toBe(2);
		for (const run of history) {
			expect(run.candidates.map((c) => c.instrument_name)).toEqual([STOCK_A, STOCK_B]);
			expect(run.exclusions.map((e) => e.reason_code)).toEqual(["factor_condition_unsatisfied"]);
		}

		// 刷新后从持久化再次读取：运行历史恢复，候选/排除可下钻。
		await page.reload();
		const historyCard = page.locator("section").filter({ hasText: "RUN HISTORY" }).first();
		await expect(historyCard).toContainText("2 runs");
		await expect(page.getByRole("link", { name: STOCK_A })).toBeVisible();
		await page.getByRole("tab", { name: /排除 1/ }).click();
		await expect(page.locator("article").filter({ hasText: STOCK_C })).toContainText(
			"factor_condition_unsatisfied",
		);
		expect(browserErrors).toEqual([]);
	});

	test("illegal threshold blocks creation client-side with an in-place message", async ({ page }) => {
		await page.goto(`${webOrigin}/markets/screener`);
		await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();

		await page.getByRole("button", { name: "添加条件组" }).click();
		await page.getByLabel("条件组 1 因子 1").selectOption("momentum_1m");
		await page.getByLabel("条件组 1 阈值 1").fill("1.5");

		await expect(page.getByRole("alert")).toContainText("条件组 1 行 1 阈值需在 0 到 1 之间");
		await expect(page.getByRole("button", { name: "创建运行" })).toBeDisabled();
	});

	test("server rejects unknown condition factors fail-closed with a readable error", async ({ page }) => {
		await page.goto(`${webOrigin}/markets/screener`);
		await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();

		await page.getByLabel("spec_id").fill(SPEC_ID);
		await page.getByLabel("top_k（入选数量）").fill("2");
		await page.getByLabel("最小日均成交额（元）").fill("0");
		await page.getByLabel("决策时点 as_of").fill(AS_OF);
		await page.getByRole("button", { name: "添加条件组" }).click();
		await page.getByLabel("条件组 1 因子 1").selectOption("momentum_1m");

		// 直接走 API 提交 PIT 不合格列（ep_ttm 不在目录，UI 无法选中）：
		// 服务端对绕过 UI 的条件引用 fail closed。
		const response = await page.request.post(`${apiOrigin}/api/v1/selections/runs`, {
			headers: API_HEADERS,
			data: {
				universe_id: "screener-fixture-market",
				asset_kind: "stock",
				spec_id: SPEC_ID,
				spec_version: "4",
				top_k: 2,
				min_average_turnover: 0,
				min_listing_days: 60,
				factor_weights: [{ name: "momentum_1m", weight: 1.0 }],
				factor_filter_groups: [
					{ conditions: [{ factor_name: "ep_ttm", operator: "gte", value: 0.5 }] },
				],
				seed: 0,
			},
		});
		expect(response.status()).toBe(422);
		const payload = (await response.json()) as { error_code?: string };
		expect(payload.error_code).toContain("ASSEMBLY_FACTOR");
	});

	test("no-candidate policy keeps an honest empty state with exclusion reasons", async ({ page }) => {
		await page.goto(`${webOrigin}/markets/screener`);
		await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();

		await page.getByLabel("spec_id").fill("screener-fixture-empty");
		await page.getByLabel("top_k（入选数量）").fill("2");
		await page.getByLabel("最小日均成交额（元）").fill("0");
		await page.getByLabel("决策时点 as_of").fill(AS_OF);
		// lte 0.1：三只样本截面秩均高于 0.1，全部因条件不满足被排除 → 无候选。
		await page.getByRole("button", { name: "添加条件组" }).click();
		await page.getByLabel("条件组 1 因子 1").selectOption("momentum_1m");
		await page.getByLabel("条件组 1 算子 1").selectOption("lte");
		await page.getByLabel("条件组 1 阈值 1").fill("0.1");

		await page.getByRole("button", { name: "创建运行" }).click();

		await expect(page.getByText(/没有入选候选/)).toBeVisible();
		await page.getByRole("tab", { name: /排除 3/ }).click();
		await expect(page.locator("article").filter({ hasText: STOCK_A })).toContainText(
			"factor_condition_unsatisfied",
		);
		expect(
			await page
				.request.get(`${apiOrigin}/api/v1/selections/runs?spec_id=screener-fixture-empty`, {
					headers: API_HEADERS,
				})
				.then((r) => r.json())
				.then((p) => (p.data as unknown[]).length),
		).toBe(1);
	});
});

/** 填写并提交一次固定运行；返回完整 run 身份（URL 携带）。 */
async function createFixedRun(page: Page, topK: string): Promise<string> {
	await page.goto(`${webOrigin}/markets/screener`);
	await expect(page.getByRole("button", { name: "添加条件组" })).toBeVisible();

	await page.getByLabel("spec_id").fill("screener-fixture-handoff");
	await page.getByLabel("top_k（入选数量）").fill(topK);
	await page.getByLabel("最小日均成交额（元）").fill("0");
	await page.getByLabel("决策时点 as_of").fill(AS_OF);
	await page.getByRole("button", { name: "添加条件组" }).click();
	await page.getByLabel("条件组 1 因子 1").selectOption("momentum_1m");
	await page.getByLabel("条件组 1 算子 1").selectOption("gte");
	await page.getByLabel("条件组 1 阈值 1").fill("0.5");
	await page.getByRole("button", { name: "创建运行" }).click();

	await expect(page).toHaveURL(/run=selection-run%3Asha256%3A[0-9a-f]{64}/, { timeout: 15_000 });
	const encoded = page.url().match(/run=([^&]+)/)?.[1];
	if (!encoded) throw new Error("run identity missing from URL");
	return decodeURIComponent(encoded);
}

async function candidatesOf(runId: string): Promise<string[]> {
	return await fetch(`${apiOrigin}/api/v1/selections/runs/${encodeURIComponent(runId)}`, {
		headers: API_HEADERS,
	})
		.then((response) => response.json())
		.then(
			(payload) =>
				(payload.data as { candidates: { instrument_id: number }[] }).candidates.map(
					(item) => String(item.instrument_id),
				),
		);
}

test.describe.serial("reopen fixed runs and hand off to research (#741)", () => {
	let firstRunId = "";
	let secondRunId = "";

	test("candidate drilldown carries object, source, and observe date and returning restores the run", async ({
		page,
	}) => {
		firstRunId = await createFixedRun(page, "2");

		// 候选主链接进图表并锚定运行决策日（对象、来源、观察日随链接携带）。
		const candidateLink = page.getByRole("link", { name: STOCK_A });
		await expect(candidateLink).toHaveAttribute(
			"href",
			`/instruments/${STOCK_A_ID}?tab=chart&selectionRunId=${encodeURIComponent(firstRunId)}&observeDate=2026-11-10`,
		);
		await candidateLink.click();
		await expect(page).toHaveURL(
			new RegExp(`/instruments/${STOCK_A_ID}\\?tab=chart&selectionRunId=`),
		);
		const anchorChip = page.getByTestId(`observe-anchor-${STOCK_A_ID}`);
		await expect(anchorChip).toHaveAttribute("data-state", "observe-anchor");
		await expect(anchorChip).toContainText("2026-11-10");

		// 返回恢复：URL 仍带固定运行身份，候选名单回到该运行的证据。
		await page.goBack();
		await expect(page).toHaveURL(new RegExp(`run=${encodeURIComponent(firstRunId)}`));
		await expect(page.getByRole("link", { name: STOCK_A })).toBeVisible();
		await expect(page.getByRole("link", { name: STOCK_B })).toBeVisible();

		// 排除视图切到 URL（?tab=），刷新后恢复（返回位置的一部分）。
		await page.getByRole("tab", { name: /排除 1/ }).click();
		await expect(page).toHaveURL(/tab=exclusions/);
		await page.reload();
		await expect(page.locator("article").filter({ hasText: STOCK_C })).toContainText(
			"factor_condition_unsatisfied",
		);
	});

	test("a later run never rewrites the frozen one and comparisons explain membership drift", async ({
		page,
	}) => {
		secondRunId = await createFixedRun(page, "1");
		expect(secondRunId).not.toBe(firstRunId);

		// 冻结证据：第一次运行的候选在第二次创建后原样（不偷换、不改写）。
		expect(await candidatesOf(firstRunId)).toEqual([STOCK_A_ID, STOCK_B_ID]);
		expect(await candidatesOf(secondRunId)).toEqual([STOCK_A_ID]);

		// 比较名单变化：退出候选与 why-out 迁移可见。两次运行 as_of 相同、
		// 历史按 run 身份字典序排列，按身份勾选保证 before=第一次运行。
		const shortLabel = (runId: string) =>
			`加入运行对比 ${runId.split(":sha256:")[1]?.slice(0, 12)}`;
		await page.getByRole("checkbox", { name: shortLabel(secondRunId) }).check();
		await page.getByRole("checkbox", { name: shortLabel(firstRunId) }).check();
		await page.getByRole("button", { name: "比较 2 个运行" }).click();
		await expect(page.getByText(/退出候选/)).toContainText(STOCK_B_ID);
		await expect(page.getByText(`${STOCK_B_ID} · 入选 → below_top_k`)).toBeVisible();

		// 旧结果缺失时不偷换最新：指向从未创建的运行得到诚实错误。
		const missing = `selection-run:sha256:${"f".repeat(64)}`;
		await page.goto(
			`${webOrigin}/markets/screener?spec=screener-fixture-handoff&run=${encodeURIComponent(missing)}`,
		);
		await expect(page.getByText("未找到该固定运行")).toBeVisible();
		await expect(page.getByText(missing)).toBeVisible();
		await expect(page.getByText("exact run required")).toBeVisible();
	});

	test("hand off to a research case and reopen it without any agent", async ({ page }) => {
		// 从固定运行直接进入（不依赖前序页面的会话状态）。
		await page.goto(
			`${webOrigin}/markets/screener?spec=screener-fixture-handoff&run=${encodeURIComponent(firstRunId)}`,
		);
		await expect(page.getByRole("link", { name: STOCK_A })).toBeVisible();

		const objective = "验证强动量候选在次月的持续性";
		await page.getByRole("textbox", { name: "研究假设 objective" }).fill(objective);
		await page.getByRole("button", { name: "创建研究用例" }).click();
		const openLink = page.getByRole("link", { name: "在研究中打开" });
		await expect(openLink).toBeVisible();

		// 研究入口保留对象、日期、来源与选择（关闭 Agent 主线仍成立）。
		await openLink.click();
		await expect(page).toHaveURL(/\/research\/cases\/research-case%3Asha256%3A/);
		await expect(page.getByRole("heading", { name: objective })).toBeVisible();
		const roster = page.getByLabel("候选名单");
		await expect(roster.getByRole("link", { name: STOCK_A })).toHaveAttribute(
			"href",
			`/instruments/${STOCK_A_ID}?tab=chart&observeDate=2026-11-10&selectionRunId=${encodeURIComponent(firstRunId)}`,
		);
		await expect(roster.getByText(STOCK_B)).toBeVisible();
		const temporal = page.getByLabel("时间身份");
		await expect(temporal).toContainText("2026/11/10");
		await expect(temporal).toContainText("knowledge cutoff");

		// 返回筛选：带固定运行身份重开（返回恢复筛选上下文）；入口在页头
		// 首屏可达（页长时底部入口被推出视口折叠线）。
		await page.getByRole("link", { name: "← 回到该运行的筛选工作面" }).click();
		await expect(page).toHaveURL(new RegExp(`run=${encodeURIComponent(firstRunId)}`));
		await expect(page.getByRole("link", { name: STOCK_B })).toBeVisible();

		// 用例列表重开持久化交接：刷新后再次读取仍然存在。
		await page.goto(`${webOrigin}/research/cases`);
		const caseRow = page.locator("tr").filter({ hasText: objective });
		await expect(caseRow).toBeVisible();

		// 键盘可达：聚焦用例行链接后 Enter 同样进入详情（真实键盤动作）。
		await caseRow.getByRole("link", { name: objective }).focus();
		await expect(caseRow.getByRole("link", { name: objective })).toBeFocused();
		await page.keyboard.press("Enter");
		await expect(page).toHaveURL(/\/research\/cases\/research-case%3Asha256%3A/);
		await expect(page.getByRole("heading", { name: objective })).toBeVisible();

		// 持久化重读：回到列表刷新后用例仍在。
		await page.goto(`${webOrigin}/research/cases`);
		await page.reload();
		await expect(page.locator("tr").filter({ hasText: objective })).toBeVisible();
	});
});

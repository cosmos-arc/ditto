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

test.describe.serial("research templates form explicit strategy versions (#744)", () => {
	let createdStrategyId = "";

	test("case handoff converts weights, explains unconverted conditions, and saves a readable version", async ({
		page,
	}) => {
		const browserErrors: string[] = [];
		page.on("pageerror", (error) => browserErrors.push(error.message));

		// 全程真实链路：筛选 → 固定运行 → 研究用例 → 模板草稿 → 策略版本。
		const runId = await createFixedRun(page, "2");
		const objective = "验证动量候选的模板化月度研究";
		await page.getByRole("textbox", { name: "研究假设 objective" }).fill(objective);
		await page.getByRole("button", { name: "创建研究用例" }).click();
		await page.getByRole("link", { name: "在研究中打开" }).click();
		await expect(page).toHaveURL(/\/research\/cases\/research-case%3Asha256%3A/);

		// 形成策略版本：股票用例只提供股票模板，不把 ETF 模板错配给股票条件。
		const handoff = page.getByLabel("形成策略版本");
		await expect(handoff.getByRole("radio", { name: /股票多因子选股/ })).toBeVisible();
		await expect(handoff.getByRole("radio", { name: /ETF/ })).toHaveCount(0);

		await handoff.getByRole("radio", { name: /股票多因子选股/ }).check();
		// 提案忠实呈现：权重转入信号表达式（同因子注册表），不可转换条件有解释。
		await expect(handoff.getByText(/momentum_1mx1/)).toBeVisible();
		await expect(handoff.getByText(/不能直接转换/)).toBeVisible();
		await expect(handoff.getByText(/截面分数秩阈值/)).toBeVisible();
		await expect(handoff.getByText("csi_a_share", { exact: true })).toBeVisible();
		// 名义池未随请求携带：池身份不可核对，缺口明示而不是静默换池。
		await expect(handoff.getByText(/池成员身份冻结在其 universe 快照/)).toBeVisible();

		// 修改身份后创建草稿（用户修改与模板共存，创建走真实策略命令）。
		const stamp = Date.now().toString(36);
		const strategyId = `handoff-journey-${stamp}`;
		createdStrategyId = strategyId;
		await handoff.getByLabel("新策略 ID").fill(strategyId);
		await handoff.getByRole("button", { name: "创建策略草稿" }).click();
		await expect(handoff.getByText(`已创建策略草稿 ${strategyId} · v1`)).toBeVisible();

		// 版本重读：策略详情按服务端持久化展示同一模板配置与因子权重。
		await handoff.getByRole("link", { name: "查看策略版本" }).click();
		await expect(page).toHaveURL(new RegExp(`/research/strategies/${strategyId}`));
		await expect(page.getByText("因子表达式")).toBeVisible();
		await expect(page.getByText("momentum_1m")).toBeVisible();
		await expect(page.getByTestId("strategy-detail-bottom")).toContainText("csi_a_share");

		// 刷新重读：草稿版本仍持久（不依赖创建页面会话）。
		await page.reload();
		await expect(page.getByText("momentum_1m")).toBeVisible();
		await expect(page.getByTestId("strategy-detail-bottom")).toContainText("csi_a_share");
		expect(browserErrors).toEqual([]);
		expect(runId).toContain("selection-run:sha256:");
	});

	test("editing a controlled formula in the studio gets row-located readable validation", async ({
		page,
	}) => {
		const browserErrors: string[] = [];
		page.on("pageerror", (error) => browserErrors.push(error.message));

		// 同一策略版本流程内编辑受控公式：Studio 表单模式直接可编辑信号表达式。
		await page.goto(`${webOrigin}/research/strategies/${createdStrategyId}/studio`);
		const expressionInput = page.getByLabel("信号表达式 1");
		await expect(expressionInput).toHaveValue("momentum_1m", { timeout: 15_000 });

		// 键盘焦点可达：聚焦后直接键入非法公式（未知函数）。
		await expressionInput.focus();
		await expressionInput.fill("unknown_fn(close)");
		await page.getByRole("button", { name: "Author 预览" }).click();

		// 只读预览给出可读诊断：类别+代码+位置+源码行，行号定位到具体表达式。
		const sheet = page.getByRole("dialog", { name: "Author 安全预览" });
		await expect(sheet).toBeVisible();
		await expect(sheet.getByText("表达式 1")).toBeVisible();
		await expect(sheet.getByText("unknown_fn(close)").first()).toBeVisible();
		const diagnostic = sheet.getByRole("alert");
		await expect(diagnostic).toContainText(/错误/);
		await expect(diagnostic).toContainText(/E0/);
		await expect(diagnostic).toContainText("第 1 行");

		// 编辑器行内同步失败状态（错误不只藏在预览抽屉里）；模态打开时
		// 背景在 aria-hidden 内，先关闭抽屉再断言行状态。
		await sheet.getByRole("button", { name: "关闭" }).click();
		await expect(sheet).toBeHidden();
		const rowStatus = page.getByRole("alert").filter({ hasText: "表达式 1" });
		await expect(rowStatus).toContainText("unknown");

		// 改回合法表达式后重新预览：同一行回到通过，形成可收敛的编辑回路。
		await expressionInput.fill("momentum_1m");
		await page.getByRole("button", { name: "Author 预览" }).click();
		await expect(page.getByText("表达式 1 编译通过")).toBeVisible();
		expect(browserErrors).toEqual([]);
	});
});

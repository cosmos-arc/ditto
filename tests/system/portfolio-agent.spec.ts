import { expect, test } from "@playwright/test";

test("exact portfolios survive refresh and a real Agent query preserves business inputs", async ({ page, request }) => {
	const origin = process.env["DITTO_SYSTEM_API_ORIGIN"];
	if (!origin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	const fixture = await (await request.get(`${origin}/system-fixture/portfolio`)).json();
	const identity = fixture.identity;
	const url = new URL(identity.frontend_path, origin);
	url.pathname = "/api/v1/portfolio/comparison";
	url.searchParams.delete("mode");
	const response = await request.get(url.toString());
	expect(response.status()).toBe(200);
	const comparison = (await response.json()).data;
	expect(comparison.model_vs_paper.attribution.fee_amount).toBe("15.51");
	expect(Number(comparison.model_vs_paper.attribution.unfilled_bps)).toBe(3000);
	expect(comparison.model_vs_manual.attribution.user_choice_bps).toBe("2277.48");
	const before = await (await request.get(`${origin}/system-fixture/portfolio`)).json();
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	await page.goto(identity.frontend_path);
	for (let attempt = 0; attempt < 2; attempt++) {
		await expect(page.getByRole("heading", { name: "MODEL / PAPER / MANUAL" })).toBeVisible();
		for (const kind of ["model", "paper", "manual"] as const) {
			const column = page.getByTestId(`portfolio-column-${kind}`);
			await expect(column).toContainText(comparison[kind].portfolio_id);
			await expect(column).toContainText(new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2 }).format(Number(comparison[kind].total_value)));
		}
		await expect(page.getByText(`AS OF ${comparison.as_of}`, { exact: true })).toBeVisible();
		await expect(page.getByTitle(identity.valuation_snapshot_id, { exact: true })).toBeVisible();
		await expect(page.getByTitle(identity.source_snapshot_id, { exact: true })).toBeVisible();
		expect(new URL(page.url()).search).toBe(new URL(identity.frontend_path, origin).search);
		if (attempt === 0) await page.reload();
	}
	await page.getByRole("link", { name: "请求组合诊断" }).click();
	await page.getByRole("button", { name: "新建 Run", exact: true }).click();
	const sheet = page.getByRole("dialog", { name: "创建 governed run" });
	await expect(sheet.getByLabel("Context type")).toHaveValue("portfolio");
	for (const label of ["Decision time", "Knowledge cutoff", "Publication cutoff"]) {
		await sheet.getByLabel(label, { exact: true }).fill("2026-08-31T07:30:00Z");
	}
	await sheet.getByLabel("Source snapshot", { exact: true }).fill(identity.source_snapshot_id);
	await sheet.getByLabel("Allowed universe", { exact: true }).fill("600519.SH,510300.SH");
	const execution = page.waitForResponse((res) => res.url().endsWith("/execute") && res.request().method() === "POST");
	await sheet.getByRole("button", { name: "创建并执行" }).click();
	const executed = await execution;
	expect(executed.status()).toBe(200);
	const run = (await executed.json()).data;
	expect(run.status).toBe("completed");
	expect(run.guardrail.status).toBe("passed");
	expect(run.evidence_refs).toHaveLength(1);
	expect(run.tool_records).toHaveLength(1);
	expect(run.tool_records[0].tool_name).toBe("portfolio_comparison_evidence");
	await page.getByText("已读取精确组合证据。", { exact: true }).scrollIntoViewIfNeeded();
	await expect(page.getByText("已读取精确组合证据。", { exact: true })).toBeVisible();
	await page.reload();
	await page.getByText("已读取精确组合证据。", { exact: true }).scrollIntoViewIfNeeded();
	await expect(page.getByText("已读取精确组合证据。", { exact: true })).toBeVisible();
	const reread = await (await request.get(`${origin}/api/v1/agent/runs/${run.run_id}`)).json();
	expect(reread.data).toEqual(run);
	const after = await (await request.get(`${origin}/system-fixture/portfolio`)).json();
	expect(after.business_hashes).toEqual(before.business_hashes);
	expect(after.model_evidence).toHaveLength(1);
	expect(after.model_evidence[0].evidence_id).toBe(run.evidence_refs[0]);
	expect(after.model_evidence[0].tool_name).toBe("portfolio_comparison_evidence");
	expect(after.model_evidence[0].result.payload).toMatchObject({
		as_of: comparison.as_of,
		valuation_snapshot_id: identity.valuation_snapshot_id,
		source_snapshot_ids: [identity.source_snapshot_id],
		model_vs_paper: { attribution: { fee_amount: "15.51" } },
		model_vs_manual: { attribution: { user_choice_bps: "2277.48" } },
	});
	const replay = await request.get(`${origin}/api/v1/agent/runs/${run.run_id}/events`);
	expect(replay.status()).toBe(200);
	expect(await replay.text()).toContain(`id: ${run.event_cursor}`);
	const resumed = await request.get(`${origin}/api/v1/agent/runs/${run.run_id}/events`, { headers: { "Last-Event-ID": String(run.event_cursor) } });
	expect(resumed.status()).toBe(200);
	expect(await resumed.text()).not.toContain("data:");
	await page.screenshot({ path: `${process.env["DITTO_SYSTEM_OUTPUT_ROOT"]}/portfolio-agent-completed.png` });
	expect((await (await request.get(url.toString())).json()).data).toEqual(comparison);
	expect(errors).toEqual([]);
});

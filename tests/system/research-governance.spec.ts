import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

type JsonObject = Record<string, unknown>;

function requiredApiOrigin(): string {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	return apiOrigin;
}

function objectField(source: JsonObject, name: string): JsonObject {
	const value = source[name];
	expect(value, `${name} must be an object`).not.toBeNull();
	expect(typeof value, `${name} must be an object`).toBe("object");
	expect(Array.isArray(value), `${name} must not be an array`).toBe(false);
	return value as JsonObject;
}

function stringField(source: JsonObject, name: string): string {
	const value = source[name];
	expect(typeof value, `${name} must be a string`).toBe("string");
	return value as string;
}

function numberField(source: JsonObject, name: string): number {
	const value = source[name];
	expect(typeof value, `${name} must be a number`).toBe("number");
	return value as number;
}

test("real research and strategy handlers launch, review, publish, and reactivate", async ({
	page,
	request,
}) => {
	const browserErrors: string[] = [];
	page.on("pageerror", (error) => browserErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") browserErrors.push(message.text());
	});
	const origin = requiredApiOrigin();
	const fixtureResponse = await request.get(
		`${origin}/system-fixture/research-plan`,
	);
	expect(fixtureResponse.status()).toBe(200);
	const fixture = (await fixtureResponse.json()) as JsonObject;
	const document = objectField(fixture, "document");
	const experimentId = stringField(document, "experiment_id");

	const wrongIdentity = await request.post(
		`${origin}/api/v1/research/experiments/different/preflight`,
		{ data: document },
	);
	expect(wrongIdentity.status()).toBe(422);
	await expect(wrongIdentity.json()).resolves.toMatchObject({
		success: false,
		error_code: "SPEC_INVALID",
	});

	const preflight = await request.post(
		`${origin}/api/v1/research/experiments/${experimentId}/preflight`,
		{ data: document },
	);
	expect(preflight.status()).toBe(200);
	const preflightPayload = (await preflight.json()) as JsonObject;
	const preflightData = objectField(preflightPayload, "data");
	expect(preflightData).toMatchObject({
		status: "research_only",
		candidate_count: 2,
		planned_fold_count: 8,
	});
	const planHash = stringField(preflightData, "plan_hash");

	const staleLaunch = await request.post(
		`${origin}/api/v1/research/experiments`,
		{
			headers: { "Idempotency-Key": "system-research-stale-plan" },
			data: { ...document, confirmed_plan_hash: "0".repeat(64) },
		},
	);
	expect(staleLaunch.status()).toBe(409);
	await expect(staleLaunch.json()).resolves.toMatchObject({
		success: false,
		error_code: "PLAN_HASH_MISMATCH",
	});

	const launchBody = { ...document, confirmed_plan_hash: planHash };
	const launch = await request.post(`${origin}/api/v1/research/experiments`, {
		headers: { "Idempotency-Key": "system-research-launch" },
		data: launchBody,
	});
	expect(launch.status()).toBe(200);
	const launchPayload = (await launch.json()) as JsonObject;
	expect(objectField(launchPayload, "data")).toMatchObject({
		experiment_id: experimentId,
		status: "queued",
		candidate_count: 2,
		fold_count: 8,
		plan_hash: planHash,
	});
	const launchReplay = await request.post(
		`${origin}/api/v1/research/experiments`,
		{
			headers: { "Idempotency-Key": "system-research-launch" },
			data: launchBody,
		},
	);
	expect(launchReplay.status()).toBe(200);
	expect(await launchReplay.json()).toEqual(launchPayload);

	const detail = await request.get(
		`${origin}/api/v1/research/experiments/${experimentId}`,
	);
	expect(detail.status()).toBe(200);
	await expect(detail.json()).resolves.toMatchObject({
		data: {
			experiment_id: experimentId,
			status: "queued",
			desired_state: "run",
			candidate_count: 2,
			fold_count: 8,
		},
	});

	const prepared = await request.post(
		`${origin}/system-fixture/prepare-review`,
	);
	expect(prepared.status()).toBe(200);
	const preparedPayload = (await prepared.json()) as JsonObject;
	const bundleHash = stringField(preparedPayload, "bundle_hash");
	const strategyId = stringField(preparedPayload, "strategy_id");
	const candidateVersion = numberField(preparedPayload, "candidate_version");
	expect(preparedPayload).toMatchObject({
		experiment_id: experimentId,
		initial_active_version: 1,
	});

	// Drive every governance mutation through the production React controls.
	// The fixture only installs invisible, deterministic packet/spec prerequisites.
	await page.goto(`/research/strategies/${encodeURIComponent(strategyId)}`);
	await page.getByRole("tab", { name: "版本" }).click();
	const submitButton = page.getByRole("button", { name: "提交审查" });
	await expect(submitButton).toBeEnabled();
	const submitResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response.url() ===
				`${origin}/api/v1/strategies/${strategyId}/versions/${candidateVersion}/submit-review`,
	);
	await submitButton.click();
	await page.getByLabel("执行者").fill("system-e2e-ui");
	await page.getByLabel("原因").fill("submit deterministic persisted research evidence");
	await page.getByRole("button", { name: "确认提交" }).click();
	const submitResponse = await submitResponsePromise;
	expect(submitResponse.status()).toBe(200);
	await expect(submitResponse.json()).resolves.toMatchObject({
		data: {
			strategy_id: strategyId,
			version: candidateVersion,
			state: "review",
			review_outcome: "pending",
		},
	});

	const reviewUrl = `/research/reviews/${encodeURIComponent(experimentId)}?strategyId=${encodeURIComponent(strategyId)}&version=${candidateVersion}`;
	await page.goto(reviewUrl);
	const approveButton = page.getByRole("button", { name: "批准" });
	await expect(approveButton).toBeEnabled();
	const approveResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response.url() === `${origin}/api/v1/strategies/${strategyId}/versions/${candidateVersion}/approve`,
	);
	await approveButton.click();
	await page.getByLabel("执行者").fill("system-e2e-ui");
	await page.getByLabel("原因").fill("approve the exact evidence-bound candidate");
	await page.getByRole("button", { name: "确认批准" }).click();
	const approveResponse = await approveResponsePromise;
	expect(approveResponse.status()).toBe(200);
	await expect(approveResponse.json()).resolves.toMatchObject({
		data: {
			strategy_id: strategyId,
			version: candidateVersion,
			state: "review",
			review_outcome: "approved",
		},
	});

	const publishButton = page.getByRole("button", { name: "发布" });
	await expect(publishButton).toBeEnabled();
	const publishResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response.url() === `${origin}/api/v1/strategies/${strategyId}/versions/${candidateVersion}/publish`,
	);
	await publishButton.click();
	await expect(page.getByRole("dialog").getByTitle(bundleHash)).toBeVisible();
	await page.getByLabel("执行者").fill("system-e2e-ui");
	await page.getByLabel("原因").fill("publish the exact approved research packet");
	await page.getByLabel("确认句").fill(`发布 v${candidateVersion}`);
	await page.getByRole("button", { name: "确认发布" }).click();
	const publishResponse = await publishResponsePromise;
	expect(publishResponse.status()).toBe(200);
	const publishPayload = (await publishResponse.json()) as JsonObject;
	const published = objectField(publishPayload, "data");
	expect(published).toMatchObject({
		strategy_id: strategyId,
		active_version: candidateVersion,
	});
	const pointerRevision = numberField(published, "pointer_revision");

	await page.goto(`/research/strategies/${encodeURIComponent(strategyId)}`);
	await page.getByRole("tab", { name: "版本" }).click();
	const versionOneActions = page.getByText("v1", { exact: true }).locator("../..");
	const reactivateButton = versionOneActions.getByRole("button", { name: "重新激活" });
	await expect(reactivateButton).toBeVisible();
	const reactivateResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response.url() === `${origin}/api/v1/strategies/${strategyId}/versions/1/reactivate`,
	);
	await reactivateButton.click();
	await page.getByLabel("执行者").fill("system-e2e-ui");
	await page.getByLabel("原因").fill("restore the prior published version");
	await page.getByLabel("影响摘要").fill("return to the deterministic baseline");
	await page
		.getByLabel("确认句")
		.fill(`strategy:reactivate:${strategyId}@1:pointer-revision:${pointerRevision}:confirm`);
	await page.getByRole("button", { name: "确认重新激活" }).click();
	const reactivateResponse = await reactivateResponsePromise;
	expect(reactivateResponse.status()).toBe(200);
	await expect(reactivateResponse.json()).resolves.toMatchObject({
		data: {
			strategy_id: strategyId,
			active_version: 1,
			pointer_revision: pointerRevision + 1,
		},
	});
	await expect(page.getByRole("heading", { name: "重新激活 v1" })).toHaveCount(0);

	const active = await request.get(
		`${origin}/api/v1/strategies/${strategyId}/active`,
	);
	expect(active.status()).toBe(200);
	await expect(active.json()).resolves.toMatchObject({
		data: {
			strategy_id: strategyId,
			active_version: 1,
			pointer_revision: pointerRevision + 1,
		},
	});

	// Governance receipts must be visible through the production audit query,
	// not merely inferred from network responses or direct SQLite inspection.
	await page.goto(reviewUrl);
	await page.getByRole("tab", { name: "治理审计" }).click();
	for (const [eventLabel, receipt] of [
		[`decision · submit_review · target v${candidateVersion}`, "submit deterministic persisted research evidence"],
		[`decision · approve · target v${candidateVersion}`, "approve the exact evidence-bound candidate"],
		[`decision · publish · target v${candidateVersion}`, "publish the exact approved research packet"],
		[`activation · publish · target v${candidateVersion}`, "publish the exact approved research packet"],
		["activation · reactivate · target v1", JSON.stringify({
			impact_summary: "return to the deterministic baseline",
			reason: "restore the prior published version",
		})],
	] as const) {
		const auditReceipt = page
			.getByRole("region", { name: "Governance Audit", exact: true })
			.getByRole("article")
			.filter({ hasText: eventLabel });
		await expect(auditReceipt).toHaveCount(1);
		await expect(auditReceipt).toBeVisible();
		await expect(auditReceipt).toContainText("system-e2e-ui");
		await expect(auditReceipt).toContainText(`"human_reason":${JSON.stringify(receipt)}`);
	}

	await page.goto(`/research/experiments/${experimentId}`);
	await expect(
		page.getByRole("heading", { name: `Experiment ${experimentId}` }),
	).toBeVisible();
	await expect(page.getByText("queued · preflight · revision 1")).toBeVisible();

	const cancelResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response.url() ===
				`${origin}/api/v1/research/experiments/${experimentId}/cancel`,
	);
	await page.getByRole("button", { name: "取消", exact: true }).click();
	const cancelResponse = await cancelResponsePromise;
	expect(cancelResponse.status()).toBe(200);
	await expect(cancelResponse.json()).resolves.toMatchObject({
		data: {
			experiment_id: experimentId,
			status: "cancel_requested",
			desired_state: "cancel",
			revision: 2,
		},
	});
	await expect(
		page.getByText("cancel_requested · revision 2", { exact: true }),
	).toBeVisible();
	await expect(
		page.getByText("cancel_requested · preflight · revision 2", {
			exact: true,
		}),
	).toBeVisible();

	const persistedCancel = await request.get(
		`${origin}/api/v1/research/experiments/${experimentId}`,
	);
	expect(persistedCancel.status()).toBe(200);
	await expect(persistedCancel.json()).resolves.toMatchObject({
		data: {
			experiment_id: experimentId,
			status: "cancel_requested",
			desired_state: "cancel",
			revision: 2,
		},
	});

	await page.reload();
	await expect(
		page.getByText("cancel_requested · preflight · revision 2", {
			exact: true,
		}),
	).toBeVisible();
	await expect(
		page.getByRole("button", { name: "取消", exact: true }),
	).toHaveCount(0);
	expect(browserErrors).toEqual([]);
});

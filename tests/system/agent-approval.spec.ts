import { expect, test } from "@playwright/test";

const apiOrigin = process.env["DITTO_SYSTEM_API_ORIGIN"];

function requiredApiOrigin(): string {
	if (!apiOrigin) throw new Error("DITTO_SYSTEM_API_ORIGIN is required");
	return apiOrigin;
}

test("production Web approves, rejects, and forbids an inexact approval", async ({
	page,
	request,
}) => {
	const origin = requiredApiOrigin();
	const browserErrors: string[] = [];
	page.on("pageerror", (error) => browserErrors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") browserErrors.push(message.text());
	});
	const health = await request.get(`${origin}/healthz`);
	expect(health.status()).toBe(200);
	await expect(health.json()).resolves.toMatchObject({
		status: "ok",
		environment: "testing",
		seeded_approval_ids: [
			"approval-live-author",
			"approval-live-author-reject",
		],
	});

	const inbox = await request.get(`${origin}/api/v1/agent/approvals`);
	expect(inbox.status()).toBe(200);
	const inboxPayload = (await inbox.json()) as {
		data: Array<{ approval_id: string; action_hash: string; status: string }>;
	};
	const approvedSubject = inboxPayload.data.find(
		(item) => item.approval_id === "approval-live-author",
	);
	const rejectedSubject = inboxPayload.data.find(
		(item) => item.approval_id === "approval-live-author-reject",
	);
	expect(approvedSubject).toMatchObject({ status: "pending" });
	expect(rejectedSubject).toMatchObject({ status: "pending" });
	if (!approvedSubject || !rejectedSubject) {
		throw new Error("seeded approval subjects are unavailable");
	}

	const drift = await request.post(
		`${origin}/api/v1/agent/approvals/${approvedSubject.approval_id}/decision`,
		{
			data: {
				decision: "approve",
				expected_action_hash: "f".repeat(64),
				operator_id: "system-e2e",
				reason: "action hash drift must fail closed",
			},
		},
	);
	expect(drift.status()).toBe(409);
	await expect(drift.json()).resolves.toMatchObject({
		success: false,
		status_code: 409,
		error_code: "AGENT_APPROVAL_HASH_CONFLICT",
	});

	await page.goto(
		`/system/approvals?tab=approvals&selected=${encodeURIComponent(approvedSubject.approval_id)}`,
	);
	await expect(
		page.getByRole("region", { name: "Agent Approval Inbox" }),
	).toBeVisible();
	await expect(
		page.getByText(approvedSubject.approval_id, { exact: true }).first(),
	).toBeVisible();
	await page.getByRole("button", { name: "审查精确动作" }).click();
	const approvalDialog = page.getByRole("dialog", { name: "审查精确动作" });
	await expect(approvalDialog).toBeVisible();
	await approvalDialog
		.getByRole("textbox", { name: "Approval operator" })
		.fill("system-e2e-ui");
	await approvalDialog
		.getByRole("textbox", { name: "Approval reason" })
		.fill("reviewed exact persisted action");
	const confirmation = approvalDialog.getByRole("textbox", {
		name: "Exact approval confirmation",
	});
	await confirmation.fill(`approval:${"0".repeat(64)}`);
	await expect(
		approvalDialog.getByRole("button", { name: "批准当前 hash" }),
	).toBeDisabled();
	await expect(
		approvalDialog.getByRole("button", { name: "拒绝" }),
	).toBeDisabled();
	const stillPending = await request.get(
		`${origin}/api/v1/agent/approvals/${approvedSubject.approval_id}`,
	);
	expect(stillPending.status()).toBe(200);
	await expect(stillPending.json()).resolves.toMatchObject({
		data: { status: "pending" },
	});

	await confirmation.fill(`approval:${approvedSubject.action_hash}`);
	const approveResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response
				.url()
				.endsWith(
					`/api/v1/agent/approvals/${approvedSubject.approval_id}/decision`,
				),
	);
	await approvalDialog.getByRole("button", { name: "批准当前 hash" }).click();
	const approveResponse = await approveResponsePromise;
	expect(approveResponse.status()).toBe(200);
	await expect
		.poll(async () => {
			const response = await request.get(
				`${origin}/api/v1/agent/approvals/${approvedSubject.approval_id}`,
			);
			const payload = (await response.json()) as { data: { status: string } };
			return payload.data.status;
		})
		.toBe("approved");
	await expect(approvalDialog).toBeHidden();

	await page.goto(
		`/system/approvals?tab=approvals&selected=${encodeURIComponent(rejectedSubject.approval_id)}`,
	);
	await expect(
		page.getByText(rejectedSubject.approval_id, { exact: true }).first(),
	).toBeVisible();
	await page.getByRole("button", { name: "审查精确动作" }).click();
	const rejectionDialog = page.getByRole("dialog", { name: "审查精确动作" });
	await rejectionDialog
		.getByRole("textbox", { name: "Approval operator" })
		.fill("system-e2e-ui");
	await rejectionDialog
		.getByRole("textbox", { name: "Approval reason" })
		.fill("reject exact persisted action");
	await rejectionDialog
		.getByRole("textbox", { name: "Exact approval confirmation" })
		.fill(`approval:${rejectedSubject.action_hash}`);
	const rejectResponsePromise = page.waitForResponse(
		(response) =>
			response.request().method() === "POST" &&
			response
				.url()
				.endsWith(
					`/api/v1/agent/approvals/${rejectedSubject.approval_id}/decision`,
				),
	);
	await rejectionDialog.getByRole("button", { name: "拒绝" }).click();
	const rejectResponse = await rejectResponsePromise;
	expect(rejectResponse.status()).toBe(200);
	await expect
		.poll(async () => {
			const response = await request.get(
				`${origin}/api/v1/agent/approvals/${rejectedSubject.approval_id}`,
			);
			const payload = (await response.json()) as { data: { status: string } };
			return payload.data.status;
		})
		.toBe("rejected");
	await expect(rejectionDialog).toBeHidden();

	const duplicate = await request.post(
		`${origin}/api/v1/agent/approvals/${approvedSubject.approval_id}/decision`,
		{
			data: {
				decision: "approve",
				expected_action_hash: approvedSubject.action_hash,
				operator_id: "system-e2e",
				reason: "a terminal decision must not execute twice",
			},
		},
	);
	expect(duplicate.status()).toBe(409);
	await expect(duplicate.json()).resolves.toMatchObject({
		success: false,
		status_code: 409,
		error_code: "AGENT_APPROVAL_ALREADY_DECIDED",
	});
	expect(browserErrors).toEqual([]);
});

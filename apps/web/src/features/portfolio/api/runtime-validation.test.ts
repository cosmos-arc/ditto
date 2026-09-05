import { describe, expect, it } from "vitest";
import {
	assertFillAdjustment,
	assertManualAccountReceipt,
	assertPaperExecutionReceipt,
	parseManualAccountReceipt,
} from "./runtime-validation";

describe("portfolio runtime validation", () => {
	it("rejects a manual ledger receipt whose account discriminator is not manual", () => {
		const receipt = {
			account: {
				account_id: "manual-1",
				kind: "manual",
				name: "Main",
				opened_at: "2026-09-04T00:00:00Z",
				currency: "CNY",
			},
			status: "created",
			event: null,
		};
		expect(() => assertManualAccountReceipt(receipt)).not.toThrow();
		expect(() => assertManualAccountReceipt({ ...receipt, account: { ...receipt.account, kind: "paper" } })).toThrow(
			/manual/u,
		);
		const mapped = parseManualAccountReceipt(receipt);
		expect(mapped).not.toBe(receipt);
		expect(mapped.account).not.toBe(receipt.account);
	});

	it("rejects a paper execution receipt without its immutable request identity", () => {
		const receipt = {
			status: "created",
			execution_id: "execution-1",
			idempotency_key: "idem-1",
			request_hash: "a".repeat(64),
			order_id: "order-1",
			order_status: "filled",
			reality_status: "filled",
			reason: null,
			fill: null,
			ledger_event_id: null,
		};
		expect(() => assertPaperExecutionReceipt(receipt)).not.toThrow();
		expect(() => assertPaperExecutionReceipt({ ...receipt, request_hash: "" })).toThrow(/request_hash/u);
		expect(() => assertPaperExecutionReceipt({ ...receipt, reality_status: "mystery" })).toThrow(/reality_status/u);
	});

	it("validates fill-adjustment discriminators", () => {
		const adjustment = {
			adjustment_id: "adjustment-1",
			fill_id: "fill-1",
			adjustment_type: "void",
			replacement_fill_id: null,
			reason: "duplicate",
			created_at: "2026-09-04T00:00:00Z",
		};
		expect(() => assertFillAdjustment(adjustment)).not.toThrow();
		expect(() => assertFillAdjustment({ ...adjustment, adjustment_type: "overwrite" })).toThrow(/adjustment_type/u);
	});
});

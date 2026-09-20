import { describe, expect, it } from "vitest";
import type { components } from "@/api/generated/schema";
import { toAdmissionView } from "./admission";

const blocked: components["schemas"]["SelectionAdmissionResponse"] = {
	allowed: false,
	purpose: "formal_research",
	rule_version: "field-admission-v1",
	fields: [
		{
			dataset_id: "stock_daily",
			field: "amount",
			snapshot_id: "snapshot",
			consumer_field: "instruments.average_turnover",
			allowed_uses: ["display"],
			reason_codes: ["LICENSE_RESTRICTED"],
			license_record_id: "reviewed-license",
			certification_report_id: "reviewed-certificate",
			covered_from: "2026-09-01",
			covered_to: "2026-09-18",
			time_precision: "timestamp",
			evidence_uri: "evidence://synthetic",
		},
	],
};

describe("field admission adapter", () => {
	it("preserves a licensed display use while explaining blocked research", () => {
		const view = toAdmissionView(blocked);
		expect(view.allowed).toBe(false);
		expect(view.fields[0]?.uses).toBe("展示");
		expect(view.fields[0]?.reasons[0]).toContain("许可不允许");
	});
	it("rejects contradictory or empty positive qualifications", () => {
		expect(() => toAdmissionView({ ...blocked, allowed: true })).toThrow("准入响应无效");
		expect(() => toAdmissionView({ ...blocked, allowed: true, fields: [] })).toThrow("准入响应无效");
	});
});

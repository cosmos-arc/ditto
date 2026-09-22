import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DataSpecimenCategory } from "../api";
import { DataProductSpecimens } from "./data-product-specimens";

function category(override: Partial<DataSpecimenCategory> & { category: string }): DataSpecimenCategory {
	return {
		collected: true,
		unresolved_gaps: [],
		latest: null,
		...override,
	};
}

describe("DataProductSpecimens", () => {
	it("renders verified conclusions with anchors, uses and independence", () => {
		const categories = [
			category({
				category: "dividend_etf",
				latest: {
					specimen_id: "specimen:dividend_etf:sha256:x",
					category: "dividend_etf",
					dataset_id: "dividend",
					anchor: "510300.SH",
					sources: [{ source: "tushare", provider_snapshot_id: "s-1", upstream_group: null }],
					upstream_independent: true,
					convention_alignment: "single_source",
					coverage_from: "2026-01-01",
					coverage_to: "2026-06-30",
					knowable_from: "2026-07-01T00:00:00Z",
					time_precision: "date",
					as_of_counterexample: "cutoff keeps prior value",
					license_record_ids: ["license-1"],
					gaps: [],
					allowed_uses: ["display", "exploration"],
					verification_status: "verified",
					procurement: [],
					adjudicated_by: "chevy",
					adjudicated_at: "2026-09-20T00:00:00Z",
					evidence_uri: "evidence://specimen",
				},
			}),
		];
		render(<DataProductSpecimens categories={categories} isLoading={false} isError={false} />);
		const row = screen.getByRole("row", { name: /分红 ETF/ });
		expect(row).toHaveTextContent("已验证");
		expect(row).toHaveTextContent("510300.SH");
		expect(row).toHaveTextContent("展示、探索");
		expect(row).toHaveTextContent("是");
	});

	it("keeps missing categories explicitly unverified with their gap reasons", () => {
		const categories = [
			category({
				category: "cross_border_etf",
				collected: false,
				unresolved_gaps: ["SPECIMEN_NOT_COLLECTED"],
			}),
		];
		render(<DataProductSpecimens categories={categories} isLoading={false} isError={false} />);
		const row = screen.getByRole("row", { name: /跨境 ETF/ });
		expect(row).toHaveTextContent("未验证");
		expect(row).toHaveTextContent("SPECIMEN_NOT_COLLECTED");
		expect(row).toHaveTextContent("—");
	});

	it("fails closed on API errors instead of faking readiness", () => {
		render(<DataProductSpecimens categories={undefined} isLoading={false} isError={true} />);
		expect(screen.getByRole("alert")).toHaveTextContent("试样 API 不可用");
	});
});

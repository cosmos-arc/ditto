import { describe, expect, it } from "vitest";
import { buildPngFooterLines, toCsvExport } from "@/components/chart/cockpit/chart-data";
import { mockBacktestReport } from "@/mocks/fixtures/backtest";
import { mapBacktestReport } from "../api/backtests";
import { backtestExportContext } from "./export-context";

describe("backtest chart export scope", () => {
	it("retains scope, exact source and strategy identities in both exported formats", () => {
		const report = mapBacktestReport({
			...mockBacktestReport,
			strategy_promotion: {
				data_catalog_identities: [{ source_snapshot_id: "snapshot:exact-revision" }, "legacy-source", {}, null],
			},
		});
		const identity = {
			dataSourceName: backtestExportContext("run-1", "strategy@7", report),
			productVersion: "0.1.0",
			exportedAtMs: 0,
		};
		for (const exported of [toCsvExport([], identity), buildPngFooterLines(identity).join(" ")]) {
			expect(exported).toContain("受限历史研究");
			expect(exported).toContain("严格历史可得性未认证");
			expect(exported).toContain("strategy@7");
			expect(exported).toContain("snapshot:exact-revision");
		}
		expect(backtestExportContext("run-2", "strategy@8", undefined)).toContain("样本池语义未记录");
	});
});

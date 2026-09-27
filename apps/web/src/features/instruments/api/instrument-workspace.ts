import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type InstrumentIdentity = components["schemas"]["Instrument"];
export type InstrumentChart = components["schemas"]["MarketChartResponse"];
export type InstrumentBar = components["schemas"]["MarketChartBarResponse"];
export type BarAdjustment = components["schemas"]["Adjustment"];

export type InstrumentBarRange = {
	readonly startDate: string;
	readonly endDate: string;
	readonly adjustment: BarAdjustment;
	readonly allowExperimental: boolean;
	readonly period: "daily" | "weekly" | "monthly";
};

export function parseInstrumentId(value: string): number {
	const instrumentId = Number(value);
	if (!Number.isInteger(instrumentId) || instrumentId <= 0) {
		throw new Error("标的 ID 必须是正整数");
	}
	return instrumentId;
}

export function fetchInstrumentIdentity(value: string): Promise<InstrumentIdentity> {
	const instrumentId = parseInstrumentId(value);
	return apiClient.get("/api/v1/metadata/instruments/{instrument_id}", {
		params: { path: { instrument_id: instrumentId } },
	});
}

export async function fetchInstrumentBars(value: string, range: InstrumentBarRange): Promise<InstrumentChart> {
	const instrumentId = parseInstrumentId(value);
	if (!range.startDate || !range.endDate || range.startDate > range.endDate) {
		throw new Error("行情查询日期范围无效");
	}

	return apiClient.post("/api/v1/market/chart", {
		body: {
			adjustment: range.adjustment,
			allow_experimental_data: range.allowExperimental,
			end_date: range.endDate,
			instrument_id: instrumentId,
			period: range.period,
			start_date: range.startDate,
		},
	});
}

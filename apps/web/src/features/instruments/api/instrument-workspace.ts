import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type InstrumentIdentity = components["schemas"]["Instrument"];
export type InstrumentBar = components["schemas"]["Bar"];

export type InstrumentBarRange = {
	readonly startDate: string;
	readonly endDate: string;
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
	return apiClient.get<InstrumentIdentity>(`/v1/metadata/instruments/${instrumentId}`);
}

export async function fetchInstrumentBars(value: string, range: InstrumentBarRange): Promise<readonly InstrumentBar[]> {
	const instrumentId = parseInstrumentId(value);
	if (!range.startDate || !range.endDate || range.startDate > range.endDate) {
		throw new Error("行情查询日期范围无效");
	}

	const bars = await apiClient.post<InstrumentBar[]>("/v1/market/bars", {
		adjustment: "none",
		allow_experimental_data: false,
		end_date: range.endDate,
		instrument_ids: [instrumentId],
		limit: 120,
		start_date: range.startDate,
	});
	return [...bars].sort((left, right) => right.trade_date.localeCompare(left.trade_date));
}

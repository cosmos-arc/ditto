import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";
import { parseInstrumentId } from "./instrument-workspace";

export type IndicatorSeriesResponse = components["schemas"]["IndicatorSeriesResponse"];
export type EtfNavResponse = components["schemas"]["EtfNavResponse"];
export type OverlayKind = "ma" | "donchian" | "macd" | "rsi" | "atr";
export type BarAdjustment = components["schemas"]["Adjustment"];

export type IndicatorSeriesRange = {
	readonly startDate: string;
	readonly endDate: string;
	readonly adjustment: BarAdjustment;
	readonly allowExperimental: boolean;
	readonly indicators: readonly OverlayKind[];
};

export async function fetchIndicatorSeries(
	value: string,
	range: IndicatorSeriesRange,
): Promise<IndicatorSeriesResponse> {
	const instrumentId = parseInstrumentId(value);
	return apiClient.post("/api/v1/market/indicator-series", {
		body: {
			instrument_id: instrumentId,
			adjustment: range.adjustment,
			allow_experimental_data: range.allowExperimental,
			start_date: range.startDate,
			end_date: range.endDate,
			ma_windows: [5, 20, 60],
			indicators: [...range.indicators],
		},
	});
}

export async function fetchEtfNav(
	value: string,
	range: { readonly startDate: string; readonly endDate: string },
): Promise<EtfNavResponse> {
	const instrumentId = parseInstrumentId(value);
	return apiClient.post("/api/v1/market/etf-nav", {
		body: {
			instrument_id: instrumentId,
			start_date: range.startDate,
			end_date: range.endDate,
		},
	});
}

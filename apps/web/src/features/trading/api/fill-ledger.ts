import type { FillLedgerEntry, GetFillLedgerResponse, OrderSide } from "@/types";
import { fetchFills, type FetchFillsParams, type FillResponse } from "./fills";

function mapDirection(direction: string): OrderSide {
	return direction.toLowerCase() === "sell" ? "SELL" : "BUY";
}

function mapFillToLedgerEntry(fill: FillResponse): FillLedgerEntry {
	return {
		id: fill.fill_id,
		intentId: fill.intent_id,
		tradeDate: fill.trade_date,
		instrument: `#${fill.instrument_id}`,
		direction: mapDirection(fill.direction),
		quantity: fill.quantity,
		fillPrice: fill.fill_price,
		fee: fill.fee,
		slippage: fill.slippage,
		notes: fill.notes,
	};
}

export async function fetchFillLedger(
	params: FetchFillsParams = {},
): Promise<GetFillLedgerResponse> {
	const fills = await fetchFills(params);

	return {
		fills: fills.map(mapFillToLedgerEntry),
	};
}

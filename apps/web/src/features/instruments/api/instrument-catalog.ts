import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type CatalogInstrument = components["schemas"]["Instrument"];
export type InstrumentCatalogFilter = {
	readonly assetClass?: components["schemas"]["AssetClass"];
	readonly exchange?: string;
	readonly isActive?: boolean;
	readonly limit?: number;
	readonly offset?: number;
};

export type InstrumentCatalog = {
	readonly items: readonly CatalogInstrument[];
	readonly total: number;
};

export async function fetchInstrumentCatalog(filter: InstrumentCatalogFilter = {}): Promise<InstrumentCatalog> {
	const limit = filter.limit ?? 100;
	const offset = filter.offset ?? 0;
	const response = await apiClient.getResponse<CatalogInstrument[]>(
		withQueryParams("/v1/metadata/instruments", {
			asset_class: filter.assetClass,
			exchange: filter.exchange,
			is_active: filter.isActive,
			limit,
			offset,
		}),
	);
	return {
		items: response.data,
		total: response.pagination?.total ?? response.data.length,
	};
}

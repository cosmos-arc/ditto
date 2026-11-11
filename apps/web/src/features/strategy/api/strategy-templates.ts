import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

/** 研究模板目录：三类模板（股票多因子/ETF 轮动/ETF 趋势）与可运行默认值。 */
export type StrategyTemplateCatalogEntry = components["schemas"]["StrategyTemplateCatalogEntryResponse"];
export type StrategyTemplateParamConstraint = components["schemas"]["StrategyTemplateParamConstraintResponse"];

export const strategyTemplateKeys = {
	catalog: ["strategy", "templates"] as const,
};

export function fetchStrategyTemplates(): Promise<readonly StrategyTemplateCatalogEntry[]> {
	return apiClient.get("/api/v1/strategies/templates");
}

export function useStrategyTemplates() {
	return useQuery({
		queryKey: strategyTemplateKeys.catalog,
		queryFn: fetchStrategyTemplates,
		staleTime: 300_000,
	});
}

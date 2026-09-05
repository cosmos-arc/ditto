import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

type FactorDescriptorResponse = components["schemas"]["FactorDescriptorResponse"];

export type FactorDiagnosticPreview = {
	readonly rankIc: number | null;
	readonly icIr: number | null;
	readonly sharpe: number | null;
	readonly turnover: number | null;
	readonly decay: number | null;
	readonly coverage: number | null;
	readonly universe: string | null;
	readonly status: string | null;
};

export type FactorCatalogItem = {
	readonly factorId: string;
	readonly lanes: readonly string[];
	readonly lookback: string;
	readonly pitRequirement: string;
	readonly diagnosticPreview: FactorDiagnosticPreview | null;
};

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
	return typeof value === "object" && value !== null;
}

function text(value: unknown): string | null {
	return typeof value === "string" && value.trim() ? value : null;
}

function finiteNumber(value: unknown): number | null {
	return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): readonly string[] {
	return Array.isArray(value)
		? value.filter((item): item is string => typeof item === "string" && item.length > 0)
		: [];
}

function lookbackLabel(value: unknown): string {
	if (!isRecord(value)) return "—";
	const amount = finiteNumber(value["value"]);
	const unit = text(value["unit"]);
	return amount === null || unit === null ? "—" : `${amount} ${unit}`;
}

function diagnosticPreview(value: unknown): FactorDiagnosticPreview | null {
	if (!isRecord(value)) return null;
	return {
		rankIc: finiteNumber(value["rank_ic"]),
		icIr: finiteNumber(value["ic_ir"]),
		sharpe: finiteNumber(value["sharpe"]),
		turnover: finiteNumber(value["turnover"]),
		decay: finiteNumber(value["decay"]),
		coverage: finiteNumber(value["coverage"]),
		universe: text(value["universe"]),
		status: text(value["status"]),
	};
}

export function mapFactorCatalogItem(dto: FactorDescriptorResponse): FactorCatalogItem {
	const payload = dto.resolved_payload;
	return {
		factorId: dto.factor_id,
		lanes: stringList(payload["lanes"]),
		lookback: lookbackLabel(payload["lookback"]),
		pitRequirement: text(payload["pit_requirement"]) ?? "unspecified",
		diagnosticPreview: diagnosticPreview(payload["diagnostic_preview"]),
	};
}

export async function fetchFactorCatalog(): Promise<readonly FactorCatalogItem[]> {
	const rows = await apiClient.get("/api/v1/research/factors");
	return rows.map(mapFactorCatalogItem);
}

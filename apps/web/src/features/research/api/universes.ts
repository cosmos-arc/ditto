import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

type UniverseResponse = components["schemas"]["UniverseResponse"];
type MemberResponse = components["schemas"]["MemberResponse"];
type CreateUniverseRequest = components["schemas"]["CreateUniverseRequest"];
type UpdateUniverseRequest = components["schemas"]["UpdateUniverseRequest"];

export interface UniverseDefinition {
	readonly universeId: string;
	readonly name: string;
	readonly universeType: string;
	readonly description: string;
	readonly sourceRef: string;
}

export interface UniverseMember {
	readonly instrumentId: number;
}

function mapUniverse(dto: UniverseResponse): UniverseDefinition {
	return {
		universeId: dto.universe_id,
		name: dto.name,
		universeType: dto.universe_type,
		description: dto.description ?? "",
		sourceRef: dto.source_ref ?? "",
	};
}

export async function fetchUniverses(): Promise<UniverseDefinition[]> {
	const rows = await apiClient.get<UniverseResponse[]>("/v1/universes");
	return rows.map(mapUniverse);
}

export async function fetchUniverseMembers(universeId: string, asOf: string): Promise<UniverseMember[]> {
	const rows = await apiClient.get<MemberResponse[]>(
		withQueryParams(`/v1/universes/${encodeURIComponent(universeId)}/members`, { asof: asOf }),
	);
	return rows.map((row) => ({ instrumentId: row.instrument_id }));
}

export async function createUniverse(input: {
	readonly universeId: string;
	readonly name: string;
	readonly description?: string;
}): Promise<UniverseDefinition> {
	const payload: CreateUniverseRequest = {
		universe_id: input.universeId,
		name: input.name,
		description: input.description || null,
	};
	return mapUniverse(await apiClient.post<UniverseResponse>("/v1/universes", payload));
}

export async function updateUniverse(
	universeId: string,
	input: {
		readonly name: string;
		readonly description?: string;
		readonly effectiveDate?: string;
		readonly members?: readonly string[];
	},
): Promise<UniverseDefinition> {
	const payload: UpdateUniverseRequest = {
		name: input.name,
		description: input.description || null,
		effective_date: input.effectiveDate || null,
		members: input.members ? [...input.members] : null,
	};
	return mapUniverse(await apiClient.put<UniverseResponse>(`/v1/universes/${encodeURIComponent(universeId)}`, payload));
}

export function deleteUniverse(universeId: string): Promise<boolean> {
	return apiClient.delete<boolean>(`/v1/universes/${encodeURIComponent(universeId)}`);
}

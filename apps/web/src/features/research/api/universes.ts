import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export type UniverseResponse = components["schemas"]["UniverseResponse"];
export type MemberResponse = components["schemas"]["MemberResponse"];
export type CreateUniverseRequest = components["schemas"]["CreateUniverseRequest"];
export type UpdateUniverseRequest = components["schemas"]["UpdateUniverseRequest"];

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
	const rows = await apiClient.get("/api/v1/universes");
	return rows.map(mapUniverse);
}

export async function fetchUniverseMembers(universeId: string, asOf: string): Promise<UniverseMember[]> {
	const rows = await apiClient.get("/api/v1/universes/{universe_id}/members", {
		params: { path: { universe_id: universeId }, query: { asof: asOf } },
	});
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
	return mapUniverse(await apiClient.post("/api/v1/universes", { body: payload }));
}

export async function updateUniverse(
	universeId: string,
	input: {
		readonly name: string;
		readonly description?: string;
		readonly effectiveDate?: string | undefined;
		readonly members?: readonly string[] | undefined;
	},
): Promise<UniverseDefinition> {
	const payload: UpdateUniverseRequest = {
		name: input.name,
		description: input.description || null,
		effective_date: input.effectiveDate || null,
		members: input.members ? [...input.members] : null,
	};
	return mapUniverse(
		await apiClient.put("/api/v1/universes/{universe_id}", {
			body: payload,
			params: { path: { universe_id: universeId } },
		}),
	);
}

export function deleteUniverse(universeId: string): Promise<boolean> {
	return apiClient.delete("/api/v1/universes/{universe_id}", {
		params: { path: { universe_id: universeId } },
	});
}

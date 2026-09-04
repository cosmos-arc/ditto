import { HttpResponse, http, type RequestHandler } from "msw";
import type { components } from "@/types/generated/api";
import { mockUniverseDefinitions, mockUniverseMembers } from "../fixtures/universes";

type UniverseResponse = components["schemas"]["UniverseResponse"];
type CreateUniverseRequest = components["schemas"]["CreateUniverseRequest"];
type UpdateUniverseRequest = components["schemas"]["UpdateUniverseRequest"];

let definitions: UniverseResponse[] = mockUniverseDefinitions.map((row) => ({ ...row }));
let members: Record<string, number[]> = Object.fromEntries(
	Object.entries(mockUniverseMembers).map(([id, values]) => [id, [...values]]),
);

export function resetMockUniverses() {
	definitions = mockUniverseDefinitions.map((row) => ({ ...row }));
	members = Object.fromEntries(Object.entries(mockUniverseMembers).map(([id, values]) => [id, [...values]]));
}

function notFound() {
	return HttpResponse.json({ detail: "universe not found", error_code: "UNIVERSE_NOT_FOUND" }, { status: 404 });
}

export const universeHandlers: RequestHandler[] = [
	http.get("/api/v1/universes", ({ request }) => {
		const type = new URL(request.url).searchParams.get("universe_type");
		return HttpResponse.json({ data: type ? definitions.filter((row) => row.universe_type === type) : definitions });
	}),
	http.post("/api/v1/universes", async ({ request }) => {
		const body = (await request.json()) as CreateUniverseRequest;
		if (definitions.some((row) => row.universe_id === body.universe_id)) {
			return HttpResponse.json(
				{ detail: "universe already exists", error_code: "UNIVERSE_ALREADY_EXISTS" },
				{ status: 409 },
			);
		}
		const created: UniverseResponse = {
			universe_id: body.universe_id,
			name: body.name,
			universe_type: "custom",
			description: body.description ?? null,
			source_ref: null,
		};
		definitions = [...definitions, created];
		members[created.universe_id] = [];
		return HttpResponse.json({ data: created }, { status: 201 });
	}),
	http.get("/api/v1/universes/:universeId", ({ params }) => {
		const row = definitions.find((item) => item.universe_id === params.universeId);
		return row ? HttpResponse.json({ data: row }) : notFound();
	}),
	http.put("/api/v1/universes/:universeId", async ({ params, request }) => {
		const index = definitions.findIndex((item) => item.universe_id === params.universeId);
		if (index < 0) return notFound();
		if (definitions[index]?.universe_type !== "custom") {
			return HttpResponse.json(
				{ detail: "preset universe is immutable", error_code: "UNIVERSE_PRESET_IMMUTABLE" },
				{ status: 409 },
			);
		}
		const body = (await request.json()) as UpdateUniverseRequest;
		const updated: UniverseResponse = {
			...definitions[index],
			name: body.name,
			description: body.description ?? null,
		};
		definitions = definitions.map((row, rowIndex) => (rowIndex === index ? updated : row));
		if (body.members && body.effective_date) members[updated.universe_id] = body.members.map(Number);
		return HttpResponse.json({ data: updated });
	}),
	http.delete("/api/v1/universes/:universeId", ({ params }) => {
		const row = definitions.find((item) => item.universe_id === params.universeId);
		if (!row) return notFound();
		if (row.universe_type !== "custom") {
			return HttpResponse.json(
				{ detail: "preset universe is immutable", error_code: "UNIVERSE_PRESET_IMMUTABLE" },
				{ status: 409 },
			);
		}
		definitions = definitions.filter((item) => item.universe_id !== params.universeId);
		delete members[row.universe_id];
		return HttpResponse.json({ data: true });
	}),
	http.get("/api/v1/universes/:universeId/members", ({ params, request }) => {
		const asOf = new URL(request.url).searchParams.get("asof");
		if (!asOf) {
			return HttpResponse.json({ detail: "asof is required", error_code: "UNIVERSE_ASOF_REQUIRED" }, { status: 422 });
		}
		if (!definitions.some((row) => row.universe_id === params.universeId)) return notFound();
		return HttpResponse.json({
			data: (members[String(params.universeId)] ?? []).map((instrumentId) => ({ instrument_id: instrumentId })),
		});
	}),
];

import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type CapitalProfile = components["schemas"]["CapitalProfileResponse"];
export type MoneyflowRow = components["schemas"]["MoneyflowRow"];
export type TopListRow = components["schemas"]["TopListRow"];
export type TopInstRow = components["schemas"]["TopInstRow"];

export type CapitalProfileRange = {
	readonly startDate: string;
	readonly endDate: string;
	readonly allowExperimental: boolean;
};

export function fetchCapitalProfile(instrumentId: number, range: CapitalProfileRange): Promise<CapitalProfile> {
	return apiClient.post("/api/v1/capital/profile", {
		body: {
			allow_experimental_data: range.allowExperimental,
			end_date: range.endDate,
			instrument_id: instrumentId,
			start_date: range.startDate,
		},
	});
}

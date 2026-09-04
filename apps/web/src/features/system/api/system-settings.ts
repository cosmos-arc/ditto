import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

type AgentCapabilityResponse = components["schemas"]["AgentCapabilityResponse"];

export type SystemRuntimeStatus = {
	readonly environment: string;
	readonly features: readonly { readonly enabled: boolean; readonly name: string }[];
	readonly observability: { readonly level: string; readonly structured: boolean };
	readonly status: string;
	readonly version: string;
};

export type SystemAgentCapability = {
	readonly availableProfiles: readonly string[];
	readonly checkedAt: string;
	readonly defaultProfile: string | null;
	readonly degradationReason: string | null;
	readonly enabled: boolean;
	readonly provider: string | null;
	readonly runtimeState: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

function requiredString(record: Record<string, unknown>, key: string): string {
	const value = record[key];
	if (typeof value !== "string" || value.length === 0) throw new Error(`status.${key} is unavailable`);
	return value;
}

export async function fetchSystemRuntimeStatus(): Promise<SystemRuntimeStatus> {
	const response = await apiClient.get<unknown>("/v1/status");
	if (!isRecord(response) || !isRecord(response.features) || !isRecord(response.observability)) {
		throw new Error("status response is incomplete");
	}

	const features = Object.entries(response.features).map(([name, enabled]) => {
		if (typeof enabled !== "boolean") throw new Error(`status.features.${name} is invalid`);
		return { enabled, name };
	});
	const structured = response.observability.structured;
	if (typeof structured !== "boolean") throw new Error("status.observability.structured is invalid");

	return {
		environment: requiredString(response, "environment"),
		features,
		observability: {
			level: requiredString(response.observability, "level"),
			structured,
		},
		status: requiredString(response, "status"),
		version: requiredString(response, "version"),
	};
}

export async function fetchSystemAgentCapability(): Promise<SystemAgentCapability> {
	const response = await apiClient.get<AgentCapabilityResponse>("/v1/agent/capabilities");
	return {
		availableProfiles: response.available_profiles,
		checkedAt: response.checked_at,
		defaultProfile: response.default_profile,
		degradationReason: response.degradation_reason,
		enabled: response.enabled,
		provider: response.provider,
		runtimeState: response.runtime_state,
	};
}

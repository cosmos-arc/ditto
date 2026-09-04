import { useQuery } from "@tanstack/react-query";
import { fetchSystemCatalogAssets } from "../api/system-overview";
import { fetchSystemAgentCapability, fetchSystemRuntimeStatus } from "../api/system-settings";

const SETTINGS_STALE_TIME_MS = 60_000;

export const systemSettingsKeys = {
	all: ["system", "settings"] as const,
	agent: () => [...systemSettingsKeys.all, "agent-capability"] as const,
	assets: () => [...systemSettingsKeys.all, "catalog-assets"] as const,
	runtime: () => [...systemSettingsKeys.all, "runtime-status"] as const,
};

export function useSystemSettings() {
	return {
		agent: useQuery({
			queryKey: systemSettingsKeys.agent(),
			queryFn: fetchSystemAgentCapability,
			staleTime: SETTINGS_STALE_TIME_MS,
		}),
		assets: useQuery({
			queryKey: systemSettingsKeys.assets(),
			queryFn: fetchSystemCatalogAssets,
			staleTime: SETTINGS_STALE_TIME_MS,
		}),
		runtime: useQuery({
			queryKey: systemSettingsKeys.runtime(),
			queryFn: fetchSystemRuntimeStatus,
			staleTime: SETTINGS_STALE_TIME_MS,
		}),
	};
}

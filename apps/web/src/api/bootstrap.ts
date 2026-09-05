import { readWebBuildMetadata, type WebBuildMetadata } from "./build-metadata";
import { type CompatibilityResult, evaluateCompatibility, parseSystemStatus } from "./compatibility";
import { type ApiClient, getApiClient } from "./transport";

export async function verifyBackendCompatibility(options: {
	readonly release: boolean;
	readonly client?: Pick<ApiClient, "get">;
	readonly build?: WebBuildMetadata;
	readonly onWarning?: (message: string) => void;
}): Promise<CompatibilityResult> {
	const build = options.build ?? readWebBuildMetadata();
	const client = options.client ?? getApiClient();
	const payload = await client.get("/api/v1/status");
	const result = evaluateCompatibility(parseSystemStatus(payload), build, { release: options.release });
	for (const warning of result.warnings) options.onWarning?.(warning);
	return result;
}

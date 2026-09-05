import { recordValue } from "./validation";

export type RuntimeMode = "live" | "mock";

export type RuntimeConfig = {
	readonly schemaVersion: 1;
	readonly runtime: RuntimeMode;
	readonly apiOrigin: string;
};

export class RuntimeConfigError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "RuntimeConfigError";
	}
}

type ParseRuntimeConfigOptions = {
	readonly production: boolean;
};

type LoadRuntimeConfigOptions = ParseRuntimeConfigOptions & {
	readonly fetcher?: (request: Request) => Promise<Response>;
	readonly configUrl?: string;
};

const CONFIG_KEYS = new Set(["schemaVersion", "runtime", "apiOrigin"]);
let activeRuntimeConfig: RuntimeConfig | undefined;

function normalizeApiOrigin(value: unknown): string {
	if (typeof value !== "string") throw new RuntimeConfigError("runtime apiOrigin must be a string");
	if (value === "" || value === "/") return "";

	let url: URL;
	try {
		url = new URL(value);
	} catch {
		throw new RuntimeConfigError("runtime apiOrigin must be same-origin or an absolute loopback URL");
	}
	const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);
	if (
		url.protocol !== "http:" ||
		!loopbackHosts.has(url.hostname) ||
		url.username !== "" ||
		url.password !== "" ||
		(url.pathname !== "" && url.pathname !== "/") ||
		url.search !== "" ||
		url.hash !== ""
	) {
		throw new RuntimeConfigError(
			"runtime apiOrigin must be a credential-free HTTP loopback origin with no path, query, or fragment",
		);
	}
	return url.origin;
}

export function parseRuntimeConfig(value: unknown, options: ParseRuntimeConfigOptions): RuntimeConfig {
	let record: Record<string, unknown>;
	try {
		record = recordValue(value, "runtimeConfig");
	} catch (error) {
		throw new RuntimeConfigError(error instanceof Error ? error.message : "runtime config must be an object");
	}
	const keys = Object.keys(record);
	const unexpected = keys.filter((key) => !CONFIG_KEYS.has(key));
	const missing = [...CONFIG_KEYS].filter((key) => !Object.hasOwn(record, key));
	if (unexpected.length > 0 || missing.length > 0) {
		throw new RuntimeConfigError(
			`runtime config keys must be exactly schemaVersion, runtime, apiOrigin; unexpected=${unexpected.join(",") || "none"}; missing=${missing.join(",") || "none"}`,
		);
	}
	if (record["schemaVersion"] !== 1) throw new RuntimeConfigError("runtime schemaVersion must be 1");
	if (record["runtime"] !== "live" && record["runtime"] !== "mock") {
		throw new RuntimeConfigError("runtime must be exactly live or mock");
	}
	if (options.production && record["runtime"] === "mock") {
		throw new RuntimeConfigError("mock runtime is forbidden in production builds");
	}
	return Object.freeze({
		schemaVersion: 1,
		runtime: record["runtime"],
		apiOrigin: normalizeApiOrigin(record["apiOrigin"]),
	});
}

function absoluteConfigUrl(path: string): string {
	const origin = typeof location === "undefined" ? "http://localhost:3000" : location.origin;
	return new URL(path, `${origin}/`).href;
}

async function requestRuntimeConfig(options: LoadRuntimeConfigOptions, signal: AbortSignal): Promise<RuntimeConfig> {
	const request = new Request(absoluteConfigUrl(options.configUrl ?? "/ditto-runtime-config.json"), {
		signal,
		cache: "no-store",
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	});
	const response = await (options.fetcher ?? fetch)(request);
	if (!response.ok) throw new RuntimeConfigError(`runtime config request failed with HTTP ${response.status}`);
	let payload: unknown;
	try {
		payload = await response.json();
	} catch {
		throw new RuntimeConfigError("runtime config response is not valid JSON");
	}
	return parseRuntimeConfig(payload, options);
}

export async function loadRuntimeConfig(options: LoadRuntimeConfigOptions): Promise<RuntimeConfig> {
	const controller = new AbortController();
	let timer: ReturnType<typeof setTimeout> | undefined;
	const deadline = new Promise<never>((_resolve, reject) => {
		timer = setTimeout(() => {
			reject(new RuntimeConfigError("runtime config request timed out"));
			controller.abort();
		}, 10_000);
	});
	try {
		return await Promise.race([requestRuntimeConfig(options, controller.signal), deadline]);
	} finally {
		clearTimeout(timer);
	}
}

export function installRuntimeConfig(value: unknown, options: ParseRuntimeConfigOptions): RuntimeConfig {
	activeRuntimeConfig = parseRuntimeConfig(value, options);
	return activeRuntimeConfig;
}

export async function initializeRuntimeConfig(options: LoadRuntimeConfigOptions): Promise<RuntimeConfig> {
	activeRuntimeConfig = await loadRuntimeConfig(options);
	return activeRuntimeConfig;
}

export function readRuntimeConfig(): RuntimeConfig {
	if (!activeRuntimeConfig) throw new RuntimeConfigError("runtime config has not been initialized");
	return activeRuntimeConfig;
}

export function isMockRuntime(): boolean {
	if (import.meta.env.MODE === "test") {
		const override = import.meta.env["VITE_USE_MOCK"];
		if (override === "true" || override === "false") return override === "true";
	}
	return readRuntimeConfig().runtime === "mock";
}

export function resolveApiBaseUrl(config = readRuntimeConfig()): string {
	if (config.apiOrigin) return config.apiOrigin;
	return typeof location === "undefined" ? "http://localhost:3000" : location.origin;
}

export function resetRuntimeConfigForTests(): void {
	if (import.meta.env.MODE !== "test") throw new RuntimeConfigError("runtime config reset is test-only");
	activeRuntimeConfig = undefined;
}

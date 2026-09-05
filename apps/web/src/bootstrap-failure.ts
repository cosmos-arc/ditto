export type BootstrapStage = "runtime_config" | "mock_runtime" | "backend_compatibility" | "application_render";

export type BootstrapFailureCode =
	| "RUNTIME_CONFIG_INVALID"
	| "MOCK_RUNTIME_FAILED"
	| "BACKEND_TIMEOUT"
	| "BACKEND_UNREACHABLE"
	| "API_CONTRACT_INCOMPATIBLE"
	| "RELEASE_COHORT_INCOMPATIBLE"
	| "BACKEND_COMPATIBILITY_FAILED"
	| "APPLICATION_RENDER_FAILED";

export type BootstrapDiagnostic = Readonly<{
	readonly schema: "ditto.bootstrap-diagnostic";
	readonly schemaVersion: 1;
	readonly stage: BootstrapStage;
	readonly code: BootstrapFailureCode;
}>;

export class BootstrapStageFailure extends Error {
	readonly stage: BootstrapStage;
	readonly cause: unknown;

	constructor(stage: BootstrapStage, cause: unknown) {
		super(`Ditto bootstrap failed during ${stage}`);
		this.name = "BootstrapStageFailure";
		this.stage = stage;
		this.cause = cause;
	}
}

function errorName(error: unknown): string {
	return error instanceof Error ? error.name : "";
}

function compatibilityCode(error: unknown): BootstrapFailureCode {
	if (errorName(error) === "ApiTimeoutError") return "BACKEND_TIMEOUT";
	if (errorName(error) === "CompatibilityError") {
		return error instanceof Error && error.message.startsWith("API contract version is incompatible:")
			? "API_CONTRACT_INCOMPATIBLE"
			: "RELEASE_COHORT_INCOMPATIBLE";
	}
	if (errorName(error) === "TypeError") return "BACKEND_UNREACHABLE";
	return "BACKEND_COMPATIBILITY_FAILED";
}

export function bootstrapFailure(stage: BootstrapStage, error: unknown): BootstrapDiagnostic {
	const code: BootstrapFailureCode =
		stage === "runtime_config"
			? "RUNTIME_CONFIG_INVALID"
			: stage === "mock_runtime"
				? "MOCK_RUNTIME_FAILED"
				: stage === "backend_compatibility"
					? compatibilityCode(error)
					: "APPLICATION_RENDER_FAILED";
	return Object.freeze({
		schema: "ditto.bootstrap-diagnostic",
		schemaVersion: 1,
		stage,
		code,
	});
}

export function diagnosticFromBootstrapFailure(error: unknown): BootstrapDiagnostic {
	return error instanceof BootstrapStageFailure
		? bootstrapFailure(error.stage, error.cause)
		: bootstrapFailure("application_render", error);
}

export function renderBootstrapFailure(root: HTMLElement | null, diagnostic: BootstrapDiagnostic): void {
	if (!root) return;
	const message = document.createElement("p");
	message.setAttribute("role", "alert");
	message.setAttribute("data-ditto-error-code", diagnostic.code);
	message.setAttribute("data-ditto-bootstrap-diagnostic", JSON.stringify(diagnostic));
	message.textContent = "Ditto 启动已阻断：运行配置或后端兼容性验证失败。";
	root.replaceChildren(message);
}

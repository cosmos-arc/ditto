import { describe, expect, it } from "vitest";
import { bootstrapFailure, renderBootstrapFailure } from "./bootstrap-failure";

describe("bootstrap fail-closed diagnostics", () => {
	it.each([
		[
			"backend_compatibility",
			Object.assign(new Error("API request exceeded the 10000 ms timeout"), { name: "ApiTimeoutError" }),
			"BACKEND_TIMEOUT",
		],
		["backend_compatibility", new TypeError("Failed to fetch https://token@example.invalid"), "BACKEND_UNREACHABLE"],
		[
			"backend_compatibility",
			Object.assign(new Error("API contract version is incompatible: Web=v1, backend=v2"), {
				name: "CompatibilityError",
			}),
			"API_CONTRACT_INCOMPATIBLE",
		],
	] as const)("classifies %s failures without exposing raw exception text", (stage, cause, code) => {
		const diagnostic = bootstrapFailure(stage, cause);

		expect(diagnostic).toEqual({
			schema: "ditto.bootstrap-diagnostic",
			schemaVersion: 1,
			stage,
			code,
		});
		expect(JSON.stringify(diagnostic)).not.toContain(cause.message);
	});

	it("renders one stable alert with a machine-readable, redacted diagnostic", () => {
		document.body.innerHTML = '<main id="root">sensitive previous content</main>';
		const reportError = vi.fn();
		Object.defineProperty(globalThis, "reportError", { configurable: true, value: reportError });

		renderBootstrapFailure(
			document.getElementById("root"),
			bootstrapFailure(
				"runtime_config",
				Object.assign(new Error("secret=do-not-render"), { name: "RuntimeConfigError" }),
			),
		);

		const alert = document.querySelector('[role="alert"]');
		expect(alert).toHaveTextContent("Ditto 启动已阻断：运行配置或后端兼容性验证失败。");
		expect(alert).toHaveAttribute("data-ditto-error-code", "RUNTIME_CONFIG_INVALID");
		expect(alert).toHaveAttribute(
			"data-ditto-bootstrap-diagnostic",
			JSON.stringify({
				schema: "ditto.bootstrap-diagnostic",
				schemaVersion: 1,
				stage: "runtime_config",
				code: "RUNTIME_CONFIG_INVALID",
			}),
		);
		expect(document.body).not.toHaveTextContent("secret=do-not-render");
		expect(reportError).not.toHaveBeenCalled();
	});
});

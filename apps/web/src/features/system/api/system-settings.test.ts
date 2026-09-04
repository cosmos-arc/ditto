import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchSystemAgentCapability, fetchSystemRuntimeStatus } from "./system-settings";

describe("system settings API adapters", () => {
	it("maps only server-reported runtime and Agent capability fields", async () => {
		server.use(
			http.get("/api/v1/status", () =>
				HttpResponse.json({
					status: "running",
					version: "1.4.0",
					environment: "production",
					features: { backtest: true, trading: false },
					observability: { level: "INFO", structured: true },
				}),
			),
			http.get("/api/v1/agent/capabilities", () =>
				HttpResponse.json({
					data: {
						enabled: true,
						runtime_state: "available",
						provider: "runtime-provider",
						available_profiles: ["balanced"],
						default_profile: "balanced",
						degradation_reason: null,
						checked_at: "2026-08-30T07:40:00Z",
					},
				}),
			),
		);

		const [runtime, agent] = await Promise.all([fetchSystemRuntimeStatus(), fetchSystemAgentCapability()]);

		expect(runtime).toMatchObject({ environment: "production", status: "running", version: "1.4.0" });
		expect(runtime.features).toEqual([
			{ enabled: true, name: "backtest" },
			{ enabled: false, name: "trading" },
		]);
		expect(agent).toMatchObject({ provider: "runtime-provider", runtimeState: "available" });
	});

	it("fails closed when the untyped system status response is incomplete", async () => {
		server.use(http.get("/api/v1/status", () => HttpResponse.json({ status: "running" })));

		await expect(fetchSystemRuntimeStatus()).rejects.toThrow("status response is incomplete");
	});
});

import { describe, it, expect, beforeEach } from "vitest";
import { server } from "@/mocks/server";
import { platformHandlers } from "./platform";
import { mockPlatformHealth, mockProviders } from "../fixtures/platform";

beforeEach(() => {
	server.use(...platformHandlers);
});

describe("platformHandlers", () => {
	it("GET /api/platform/health 返回健康数据", async () => {
		const res = await fetch("/api/platform/health");
		const data = (await res.json()) as typeof mockPlatformHealth;

		expect(res.status).toBe(200);
		expect(data.freshness).toBe(98.5);
		expect(data.completeness).toBe(99.2);
		expect(data.accuracy).toBe(97.8);
		expect(data.jobsStatus.running).toBe(3);
	});

	it("GET /api/platform/providers 返回数据提供者列表", async () => {
		const res = await fetch("/api/platform/providers");
		const data = (await res.json()) as { providers: typeof mockProviders };

		expect(res.status).toBe(200);
		expect(data.providers).toHaveLength(3);
		expect(data.providers[0]?.name).toBe("tushare");
		expect(data.providers[0]?.status).toBe("healthy");
	});

	it("GET /api/platform/providers 返回类型安全数据", async () => {
		const res = await fetch("/api/platform/providers");
		const data = (await res.json()) as { providers: typeof mockProviders };

		for (const provider of data.providers) {
			expect(provider).toHaveProperty("name");
			expect(provider).toHaveProperty("status");
			expect(provider).toHaveProperty("latency");
			expect(provider).toHaveProperty("endpoints");
			expect(typeof provider.latency).toBe("number");
			expect(Array.isArray(provider.endpoints)).toBe(true);
		}
	});

	it("GET /api/platform/pipelines 返回管道列表", async () => {
		const res = await fetch("/api/platform/pipelines");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.items).toHaveLength(3);
		expect(data.total).toBe(3);
	});

	it("GET /api/platform/alerts 返回告警列表", async () => {
		const res = await fetch("/api/platform/alerts");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.items.length).toBeGreaterThan(0);
		const criticalAlert = data.items.find(
			(a: { severity: string }) => a.severity === "critical",
		);
		expect(criticalAlert).toBeDefined();
	});

	it("GET /api/platform/resources 返回资源使用情况", async () => {
		const res = await fetch("/api/platform/resources");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.resources.length).toBeGreaterThan(0);
	});
});

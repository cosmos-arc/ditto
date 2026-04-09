import { describe, it, expect, beforeEach } from "vitest";
import { server } from "@/mocks/server";
import { homeHandlers } from "./home";
import { mockHomePulse, mockDecisionBanner } from "../fixtures/home";

beforeEach(() => {
	server.use(...homeHandlers);
});

describe("homeHandlers", () => {
	it("GET /api/home/pulse 返回脉动数据", async () => {
		const res = await fetch("/api/home/pulse");
		const data = (await res.json()) as typeof mockHomePulse;

		expect(res.status).toBe(200);
		expect(data.session).toBe("continuous");
		expect(data.pendingActions).toBe(5);
		expect(data.pnlToday).toBe(12580.5);
	});

	it("GET /api/home/decision-banner 返回决策横幅", async () => {
		const res = await fetch("/api/home/decision-banner");
		const data = (await res.json()) as typeof mockDecisionBanner;

		expect(res.status).toBe(200);
		expect(data.marketRegime).toBe("risk_on");
		expect(data.totalEquity).toBe(1580000);
		expect(typeof data.suggestion).toBe("string");
		expect(data.suggestion.length).toBeGreaterThan(0);
	});

	it("GET /api/home/pending-actions 返回待处理事项", async () => {
		const res = await fetch("/api/home/pending-actions");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.actions).toHaveLength(5);
		expect(data.actions[0]?.priority).toBe("critical");
	});

	it("GET /api/home/alerts 返回告警列表", async () => {
		const res = await fetch("/api/home/alerts");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.alerts.length).toBeGreaterThan(0);
	});

	it("GET /api/home/signals/recent 返回近期信号", async () => {
		const res = await fetch("/api/home/signals/recent");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.signals).toHaveLength(3);
		expect(["BUY", "SELL", "HOLD"]).toContain(data.signals[0]?.action);
	});

	it("GET /api/home/agent-findings 返回 Agent 发现", async () => {
		const res = await fetch("/api/home/agent-findings");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.findings).toHaveLength(3);
		expect(["insight", "warning", "info"]).toContain(data.findings[0]?.icon);
	});

	it("GET /api/home/data-health 返回数据健康状态", async () => {
		const res = await fetch("/api/home/data-health");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.providers.length).toBeGreaterThan(0);
	});

	it("GET /api/market/indices 返回市场指数", async () => {
		const res = await fetch("/api/market/indices");
		const data = await res.json();

		expect(res.status).toBe(200);
		expect(data.indices).toHaveLength(6);
		expect(data.indices[0]?.name).toBe("上证指数");
		expect(data.indices[0]?.dir).toBe("up");
	});
});

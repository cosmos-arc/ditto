import { describe, expect, it } from "vitest";
import { liveDailyDecisionV3 } from "@/mocks/handlers/portfolio";
import { mapDailyDecisionV3ToHomeProjection } from "./home-projection";

describe("Daily Decision V3 home projection", () => {
	it("maps auditable trading facts without inventing unsupported market or agent data", () => {
		const projection = mapDailyDecisionV3ToHomeProjection(liveDailyDecisionV3);

		expect(projection.pulse).toMatchObject({
			date: "2026-07-03",
			pendingActions: 1,
			pnlToday: 197,
			pnlPercent: 0.197,
			runningJobs: null,
		});
		expect(projection.decisionBanner).toMatchObject({
			totalEquity: 100_000,
			dailyPnl: 197,
			dailyPnlPercent: 0.197,
			leverage: 0.4,
			maxDrawdown: null,
			ivix: null,
			northboundFlow: null,
			equitySparkline: [],
		});
		expect(projection.pendingActions.actions[0]).toMatchObject({
			id: "intent-510300",
			domain: "trading",
			priority: "critical",
		});
		expect(projection.pendingActions.actions[0]?.meta).toContain("RISK_WARNING");
		expect(projection.agentFindings.findings).toEqual([]);
		expect(projection.marketPulse.metrics).toEqual([
			{
				label: "市场行情",
				value: "不可用",
				change: "Daily Decision V3 未提供行情投影",
			},
		]);
		expect(projection.dataHealth.providers).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ label: "决策数据", status: "healthy", statusText: "ready / passed" }),
				expect.objectContaining({ label: "PIT 证据", status: "healthy" }),
				expect.objectContaining({ label: "执行对账", status: "healthy", statusText: "matched" }),
			]),
		);
	});

	it("fails closed when provenance and reconciliation are incomplete", () => {
		const projection = mapDailyDecisionV3ToHomeProjection({
			...liveDailyDecisionV3,
			readiness: "blocked",
			blocking_reasons: ["PIT_PROVENANCE_INCOMPLETE"],
			reconciliation: {
				...liveDailyDecisionV3.reconciliation,
				status: "mismatch",
				differences: ["positions differ"],
			},
			provenance: {
				...liveDailyDecisionV3.provenance,
				source_snapshot_ids: [],
			},
		});

		expect(projection.pulse.riskLevel).toBe("阻断");
		expect(projection.alerts.alerts).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ severity: "critical", title: "PIT_PROVENANCE_INCOMPLETE" }),
				expect.objectContaining({ severity: "critical", title: "执行对账不一致" }),
			]),
		);
		expect(projection.dataHealth.providers).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ label: "PIT 证据", status: "error" }),
				expect.objectContaining({ label: "执行对账", status: "error" }),
			]),
		);
	});

	it("keeps missing decision facts explicit and filters unsupported signal directions", () => {
		const action = liveDailyDecisionV3.v2.actions[0];
		expect(action).toBeDefined();
		const projection = mapDailyDecisionV3ToHomeProjection({
			...liveDailyDecisionV3,
			readiness: "ready",
			reconciliation: {
				...liveDailyDecisionV3.reconciliation,
				status: "mismatch",
				differences: [],
			},
			provenance: {
				decision_time: null,
				knowledge_cutoff: null,
				publication_cutoff: null,
				source_snapshot_ids: [],
				generated_at: null,
			},
			v2: {
				...liveDailyDecisionV3.v2,
				identity: {
					...liveDailyDecisionV3.v2.identity,
					intended_trade_date: null,
					signal_date: null,
				},
				data: {
					...liveDailyDecisionV3.v2.data,
					freshness: "blocked",
					dq_state: "failed",
				},
				account_positions: {
					...liveDailyDecisionV3.v2.account_positions,
					total_value: null,
					exposure: null,
				},
				execution_review: {
					...liveDailyDecisionV3.v2.execution_review,
					pnl: null,
				},
				actions: [
					{
						...action!,
						direction: "WAIT",
						intent_status: null,
						risk_flags: [],
						suggested_quantity: null,
					},
				],
			},
		});

		expect(projection.pulse).toMatchObject({
			date: "日期未提供",
			pnlToday: null,
			pnlPercent: null,
			riskLevel: "就绪",
		});
		expect(projection.decisionBanner).toMatchObject({
			totalEquity: null,
			leverage: null,
			suggestion: "Daily Decision V3 已就绪；执行仍需人工确认。",
		});
		expect(projection.pendingActions.actions[0]).toMatchObject({
			priority: "high",
			title: "#510300 WAIT 建议待人工复核",
			time: "时间未提供",
		});
		expect(projection.pendingActions.actions[0]?.meta).toContain("建议数量 未提供；无额外风险标记");
		expect(projection.recentSignals.signals).toEqual([]);
		expect(projection.alerts.alerts).toEqual([expect.objectContaining({ desc: "mismatch", time: "时间未提供" })]);
		expect(projection.dataHealth.providers).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ label: "决策数据", status: "degraded" }),
				expect.objectContaining({ label: "PIT 证据", status: "error" }),
			]),
		);
	});
});

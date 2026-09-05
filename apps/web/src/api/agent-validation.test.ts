import { describe, expect, it } from "vitest";
import {
	assertAgentApproval,
	assertAgentApprovalDecision,
	assertAgentApprovalList,
	assertAgentRun,
	assertAgentRunList,
	isTerminalAgentSsePayload,
	parseAgentSsePayload,
} from "./agent-validation";

describe("Agent runtime validation", () => {
	it("accepts an identity-bound approval and rejects a malformed action hash", () => {
		const approval = {
			approval_id: "approval-1",
			run_id: "run-1",
			action_type: "publish",
			target_identity: "strategy-1",
			action_payload: {},
			action_hash: "a".repeat(64),
			status: "pending",
			requested_at: "2026-09-04T00:00:00Z",
			expires_at: "2026-09-05T00:00:00Z",
			operator_id: null,
			reason: null,
			decided_at: null,
		};
		expect(() => assertAgentApproval(approval)).not.toThrow();
		expect(() => assertAgentApproval({ ...approval, action_hash: "weak" })).toThrow(/action_hash/u);
	});

	it("validates the durable approval decision receipt without requiring subject fields", () => {
		const receipt = {
			approval_id: "approval-1",
			run_id: "run-1",
			action_hash: "a".repeat(64),
			status: "approved",
			operator_id: "operator-1",
			reason: null,
			decided_at: "2026-09-04T00:00:00Z",
		};
		expect(() => assertAgentApprovalDecision(receipt)).not.toThrow();
		expect(() => assertAgentApprovalDecision({ ...receipt, status: "pending" })).toThrow(/status/u);
		expect(() => assertAgentApprovalDecision({ ...receipt, action_hash: "weak" })).toThrow(/action_hash/u);
		expect(() => assertAgentApprovalDecision({ ...receipt, reason: "reviewed evidence" })).not.toThrow();
	});

	it("rejects non-list run and approval envelopes before mapping untrusted entries", () => {
		expect(() => assertAgentRunList({ data: [] })).toThrow(/expected an array/u);
		expect(() => assertAgentApprovalList("pending")).toThrow(/expected an array/u);
	});

	it("validates every authority-bearing field on a run envelope", () => {
		const run = {
			run_id: "run-1",
			session_id: "session-1",
			status: "running",
			objective_hash: "a".repeat(64),
			authority_hash: "b".repeat(64),
			manifest_hash: "c".repeat(64),
			revision: 1,
			event_cursor: 2,
			tool_records: [],
			evidence_refs: [],
			artifact_refs: [],
		};
		expect(() => assertAgentRun(run)).not.toThrow();
		expect(() => assertAgentRunList([run])).not.toThrow();
		expect(() => assertAgentRun({ ...run, revision: -1 })).toThrow(/revision/u);
	});

	it("requires SSE identity, cursor, discriminator and hashes to agree", () => {
		const payload = {
			schema_version: 1,
			event_id: 7,
			run_id: "run-1",
			run_sequence: 7,
			event_type: "run_completed",
			payload_hash: "b".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
			prev_hash: "c".repeat(64),
			event_hash: "d".repeat(64),
		};
		expect(parseAgentSsePayload(payload, { id: 7, eventType: "run_completed" })).toEqual(payload);
		expect(() => parseAgentSsePayload({ ...payload, event_id: 8 }, { id: 7, eventType: "run_completed" })).toThrow(
			/event_id/u,
		);
		expect(() => parseAgentSsePayload(payload, { id: 7, eventType: "run_failed" })).toThrow(/event_type/u);
		expect(() =>
			parseAgentSsePayload(
				{ ...payload, prev_hash: null },
				{ id: 7, eventType: "run_completed", target: { kind: "runs", identity: "run-1" } },
			),
		).toThrow(/prev_hash/u);
		expect(() =>
			parseAgentSsePayload(payload, {
				id: 7,
				eventType: "run_completed",
				target: { kind: "runs", identity: "run-other" },
			}),
		).toThrow(/stream identity mismatch/u);
	});

	it("accepts only schema version 1 for Agent SSE payloads", () => {
		const payload = {
			schema_version: 2,
			event_id: 7,
			run_id: "run-1",
			run_sequence: 7,
			event_type: "run_completed",
			payload_hash: "b".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
			prev_hash: "c".repeat(64),
			event_hash: "d".repeat(64),
		};

		expect(() => parseAgentSsePayload(payload, { id: 7, eventType: "run_completed" })).toThrow(
			/schema_version.*expected 1/u,
		);
	});

	it("rejects undeclared fields and invalid RFC 3339 timestamps", () => {
		const payload = {
			schema_version: 1,
			event_id: 1,
			run_id: "run-1",
			run_sequence: 1,
			event_type: "run_queued",
			payload_hash: "b".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
			prev_hash: null,
			event_hash: "d".repeat(64),
		};

		expect(() =>
			parseAgentSsePayload({ ...payload, secret: "unexpected" }, { id: 1, eventType: "run_queued" }),
		).toThrow(/not declared/u);
		expect(() =>
			parseAgentSsePayload({ ...payload, occurred_at: "tomorrow" }, { id: 1, eventType: "run_queued" }),
		).toThrow(/occurred_at/u);
	});

	it("validates campaign SSE identity and rejects events without a supported identity", () => {
		const campaign = {
			schema_version: 1,
			event_id: 8,
			campaign_id: "campaign-1",
			durable_event_id: "campaign-1:8",
			previous_status: "authorized",
			status: "running",
			event_type: "candidate_dispatched",
			payload_hash: "e".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
		};
		expect(
			parseAgentSsePayload(campaign, {
				id: 8,
				eventType: "candidate_dispatched",
				target: { kind: "campaigns", identity: "campaign-1" },
			}),
		).toEqual(campaign);
		expect(() =>
			parseAgentSsePayload(campaign, {
				id: 8,
				eventType: "candidate_dispatched",
				target: { kind: "runs", identity: "campaign-1" },
			}),
		).toThrow(/stream identity mismatch/u);
		expect(() =>
			parseAgentSsePayload(
				{
					schema_version: 1,
					event_id: 9,
					event_type: "unknown",
					payload_hash: "f".repeat(64),
					occurred_at: "2026-09-04T00:00:00Z",
				},
				{ id: 9, eventType: "unknown" },
			),
		).toThrow(/expected run_id or campaign_id/u);
	});

	it("accepts the authoritative Campaign statuses and rejects the nonexistent approved status", () => {
		const campaignEvent = (status: string, eventType: string, eventId: number, previousStatus: string | null) => ({
			schema_version: 1,
			event_id: eventId,
			campaign_id: "campaign-1",
			durable_event_id: `campaign-event-${eventId}`,
			previous_status: previousStatus,
			status,
			event_type: eventType,
			payload_hash: "e".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
		});

		for (const [status, eventType, eventId, previousStatus] of [
			["draft", "campaign_created", 1, null],
			["authorized", "campaign_authorized", 2, "draft"],
			["running", "candidate_dispatched", 3, "authorized"],
			["paused", "campaign_paused", 4, "running"],
			["paused_budget", "campaign_paused_budget", 5, "running"],
			["cancel_requested", "campaign_cancel_requested", 6, "running"],
			["cancelled", "campaign_cancelled", 7, "cancel_requested"],
			["completed", "campaign_completed", 8, "running"],
			["completed_with_failures", "campaign_completed", 9, "running"],
			["failed", "campaign_completed", 10, "running"],
		] as const) {
			expect(() =>
				parseAgentSsePayload(campaignEvent(status, eventType, eventId, previousStatus), { id: eventId, eventType }),
			).not.toThrow();
		}
		expect(() =>
			parseAgentSsePayload(campaignEvent("approved", "candidate_dispatched", 8, "running"), {
				id: 8,
				eventType: "candidate_dispatched",
			}),
		).toThrow(/status/u);
	});

	it("requires Campaign previous_status and terminal event/status coherence", () => {
		const terminal = {
			schema_version: 1,
			event_id: 2,
			campaign_id: "campaign-1",
			durable_event_id: "campaign-event-2",
			previous_status: "running",
			status: "completed",
			event_type: "campaign_completed",
			payload_hash: "e".repeat(64),
			occurred_at: "2026-09-04T00:00:00Z",
		};

		expect(() => parseAgentSsePayload(terminal, { id: 2, eventType: "campaign_completed" })).not.toThrow();
		expect(() =>
			parseAgentSsePayload({ ...terminal, previous_status: undefined }, { id: 2, eventType: "campaign_completed" }),
		).toThrow(/previous_status/u);
		expect(() =>
			parseAgentSsePayload({ ...terminal, status: "running" }, { id: 2, eventType: "campaign_completed" }),
		).toThrow(/terminal/u);
		const lateReceipt = {
			...terminal,
			event_id: 3,
			durable_event_id: "campaign-event-3",
			previous_status: "completed",
			event_type: "candidate_dispatched",
		};
		expect(() => parseAgentSsePayload(lateReceipt, { id: 3, eventType: "candidate_dispatched" })).not.toThrow();
		expect(
			isTerminalAgentSsePayload(parseAgentSsePayload(lateReceipt, { id: 3, eventType: "candidate_dispatched" })),
		).toBe(false);
		expect(isTerminalAgentSsePayload(parseAgentSsePayload(terminal, { id: 2, eventType: "campaign_completed" }))).toBe(
			true,
		);
	});
});

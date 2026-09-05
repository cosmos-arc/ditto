import type { components } from "@/api/generated/schema";
import { arrayValue, enumValue, hashValue, integerValue, recordValue, stringValue } from "@/api/validation";
import { operationEventContracts } from "./generated/operation-contracts";

type AgentApprovalResponse = components["schemas"]["AgentApprovalResponse"];
type AgentApprovalDecisionResponse = components["schemas"]["AgentApprovalDecisionResponse"];
type AgentRunResponse = components["schemas"]["AgentRunResponse"];

const APPROVAL_STATUSES = ["pending", "approved", "rejected", "expired"] as const;
const RUN_STATUSES = ["queued", "running", "waiting_approval", "paused", "completed", "failed", "cancelled"] as const;
const RUN_EVENT_CONTRACT = operationEventContracts["get /api/v1/agent/runs/{run_id}/events"];
const CAMPAIGN_EVENT_CONTRACT = operationEventContracts["get /api/v1/agent/campaigns/{campaign_id}/events"];
const AGENT_SSE_SCHEMA_VERSION: typeof CAMPAIGN_EVENT_CONTRACT.schemaVersion = RUN_EVENT_CONTRACT.schemaVersion;
const RUN_EVENT_TYPES = RUN_EVENT_CONTRACT.eventTypes;
const RUN_TERMINAL_EVENT_TYPES = RUN_EVENT_CONTRACT.terminal.values;
const CAMPAIGN_STATUSES = CAMPAIGN_EVENT_CONTRACT.statusValues;
const CAMPAIGN_EVENT_TYPES = CAMPAIGN_EVENT_CONTRACT.eventTypes;
const CAMPAIGN_TERMINAL_EVENT_TYPES = CAMPAIGN_EVENT_CONTRACT.terminal.values;
const CAMPAIGN_TERMINAL_STATUSES = ["cancelled", "completed", "completed_with_failures", "failed"] as const;

export function assertAgentApproval(value: unknown): asserts value is AgentApprovalResponse {
	const boundary = "agentApproval";
	const record = recordValue(value, boundary);
	stringValue(record, "approval_id", boundary);
	stringValue(record, "run_id", boundary);
	stringValue(record, "action_type", boundary);
	stringValue(record, "target_identity", boundary);
	recordValue(record["action_payload"], boundary, "action_payload");
	hashValue(record, "action_hash", boundary);
	enumValue(record, "status", APPROVAL_STATUSES, boundary);
	stringValue(record, "requested_at", boundary);
	stringValue(record, "expires_at", boundary);
}

export function assertAgentApprovalDecision(value: unknown): asserts value is AgentApprovalDecisionResponse {
	const boundary = "agentApprovalDecision";
	const record = recordValue(value, boundary);
	stringValue(record, "approval_id", boundary);
	stringValue(record, "run_id", boundary);
	hashValue(record, "action_hash", boundary);
	enumValue(record, "status", ["approved", "rejected"] as const, boundary);
	stringValue(record, "operator_id", boundary);
	if (record["reason"] !== null) stringValue(record, "reason", boundary);
	stringValue(record, "decided_at", boundary);
}

export function assertAgentRun(value: unknown): asserts value is AgentRunResponse {
	const boundary = "agentRun";
	const record = recordValue(value, boundary);
	stringValue(record, "run_id", boundary);
	stringValue(record, "session_id", boundary);
	enumValue(record, "status", RUN_STATUSES, boundary);
	hashValue(record, "objective_hash", boundary);
	hashValue(record, "authority_hash", boundary);
	hashValue(record, "manifest_hash", boundary);
	integerValue(record, "revision", boundary, 0);
	integerValue(record, "event_cursor", boundary, 0);
	arrayValue(record, "tool_records", boundary);
	arrayValue(record, "evidence_refs", boundary);
	arrayValue(record, "artifact_refs", boundary);
}

export function assertAgentRunList(value: unknown): asserts value is readonly AgentRunResponse[] {
	if (!Array.isArray(value)) throw new Error("agentRunList: expected an array");
	for (const item of value) assertAgentRun(item);
}

export function assertAgentApprovalList(value: unknown): asserts value is readonly AgentApprovalResponse[] {
	if (!Array.isArray(value)) throw new Error("agentApprovalList: expected an array");
	for (const item of value) assertAgentApproval(item);
}

export type AgentRunSsePayload = Readonly<components["schemas"]["AgentRunSseEvent"]>;

export type AgentCampaignSsePayload = Readonly<components["schemas"]["AgentCampaignSseEvent"]>;

export type AgentSsePayload = AgentRunSsePayload | AgentCampaignSsePayload;

function includesContractValue<const Values extends readonly string[]>(
	values: Values,
	value: string,
): value is Values[number] {
	return values.some((candidate) => candidate === value);
}

export function isTerminalAgentSsePayload(payload: AgentSsePayload): boolean {
	if ("run_id" in payload) {
		return includesContractValue(RUN_TERMINAL_EVENT_TYPES, payload.event_type);
	}
	return includesContractValue(CAMPAIGN_TERMINAL_EVENT_TYPES, payload.event_type);
}

function assertExactContractFields(record: Readonly<Record<string, unknown>>, fields: readonly string[]): void {
	const expected = new Set(fields);
	for (const field of Object.keys(record)) {
		if (!expected.has(field)) throw new Error(`agentSse.${field}: field is not declared by the event contract`);
	}
	for (const field of fields) {
		if (!Object.hasOwn(record, field)) throw new Error(`agentSse.${field}: required contract field is missing`);
	}
}

function rfc3339Value(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string {
	const value = stringValue(record, field, boundary);
	const match =
		/^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/u.exec(
			value,
		);
	if (!match) throw new Error(`${boundary}.${field}: expected an RFC 3339 timestamp with an explicit offset`);
	const year = Number(match[1]);
	const month = Number(match[2]);
	const day = Number(match[3]);
	const calendarDate = new Date(Date.UTC(year, month - 1, day));
	if (
		month < 1 ||
		month > 12 ||
		calendarDate.getUTCFullYear() !== year ||
		calendarDate.getUTCMonth() !== month - 1 ||
		calendarDate.getUTCDate() !== day ||
		!Number.isFinite(Date.parse(value))
	) {
		throw new Error(`${boundary}.${field}: expected a valid RFC 3339 timestamp`);
	}
	return value;
}

export function parseAgentSsePayload(
	value: unknown,
	expected: {
		readonly id: number;
		readonly eventType: string;
		readonly target?: { readonly kind: "runs" | "campaigns"; readonly identity: string };
	},
): AgentSsePayload {
	const boundary = "agentSse";
	const record = recordValue(value, boundary);
	const schemaVersion = integerValue(record, "schema_version", boundary, 1);
	if (schemaVersion !== AGENT_SSE_SCHEMA_VERSION) {
		throw new Error(`agentSse.schema_version: expected ${AGENT_SSE_SCHEMA_VERSION}, received ${schemaVersion}`);
	}
	const eventId = integerValue(record, "event_id", boundary, 1);
	if (eventId !== expected.id) throw new Error(`agentSse.event_id: expected ${expected.id}, received ${eventId}`);
	const eventType = stringValue(record, "event_type", boundary);
	if (eventType !== expected.eventType) {
		throw new Error(`agentSse.event_type: expected ${expected.eventType}, received ${eventType}`);
	}
	hashValue(record, "payload_hash", boundary);
	rfc3339Value(record, "occurred_at", boundary);
	const hasRunIdentity = Object.hasOwn(record, "run_id");
	const hasCampaignIdentity = Object.hasOwn(record, "campaign_id");
	if (hasRunIdentity === hasCampaignIdentity) {
		throw new Error("agentSse identity: expected run_id or campaign_id, exclusively");
	}
	if (hasRunIdentity) {
		assertExactContractFields(record, RUN_EVENT_CONTRACT.fields);
		const runId = stringValue(record, "run_id", boundary);
		const runSequence = integerValue(record, "run_sequence", boundary, 1);
		enumValue(record, "event_type", RUN_EVENT_TYPES, boundary);
		if (record["prev_hash"] !== null) {
			hashValue(record, "prev_hash", boundary);
		} else if (runSequence !== 1) {
			throw new Error("agentSse.prev_hash: expected a predecessor hash after run sequence 1");
		}
		if (runSequence === 1 && record["prev_hash"] !== null) {
			throw new Error("agentSse.prev_hash: expected null for run sequence 1");
		}
		hashValue(record, "event_hash", boundary);
		if (expected.target && (expected.target.kind !== "runs" || expected.target.identity !== runId)) {
			throw new Error("agentSse.run_id: stream identity mismatch");
		}
	} else if (Object.hasOwn(record, "campaign_id")) {
		assertExactContractFields(record, CAMPAIGN_EVENT_CONTRACT.fields);
		const campaignId = stringValue(record, "campaign_id", boundary);
		stringValue(record, "durable_event_id", boundary);
		const campaignEventType = enumValue(record, "event_type", CAMPAIGN_EVENT_TYPES, boundary);
		const previousStatus =
			record["previous_status"] === null ? null : enumValue(record, "previous_status", CAMPAIGN_STATUSES, boundary);
		const status = enumValue(record, "status", CAMPAIGN_STATUSES, boundary);
		if ((eventId === 1) !== (previousStatus === null)) {
			throw new Error("agentSse.previous_status: expected null exactly for Campaign event 1");
		}
		const terminalStatus = includesContractValue(CAMPAIGN_TERMINAL_STATUSES, status);
		const terminalEvent = includesContractValue(CAMPAIGN_TERMINAL_EVENT_TYPES, campaignEventType);
		if (terminalEvent && !terminalStatus) {
			throw new Error("agentSse terminal: Campaign terminal events require a terminal status");
		}
		if (campaignEventType === "campaign_cancelled" && status !== "cancelled") {
			throw new Error("agentSse terminal: campaign_cancelled requires cancelled status");
		}
		if (campaignEventType === "campaign_completed" && status === "cancelled") {
			throw new Error("agentSse terminal: campaign_completed cannot use cancelled status");
		}
		if (expected.target && (expected.target.kind !== "campaigns" || expected.target.identity !== campaignId)) {
			throw new Error("agentSse.campaign_id: stream identity mismatch");
		}
	}
	return record as AgentSsePayload;
}

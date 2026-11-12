import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type PlanDTO = components["schemas"]["NextDayPlanResponse"];
type SummaryDTO = components["schemas"]["NextDayPlanSummaryResponse"];
type RecordBody = components["schemas"]["CreateNextDayPlanBody"];

export type NextDayPlanCandidateNote = {
	readonly instrumentId: number;
	readonly reason: string;
};

export type NextDayPlan = {
	readonly planId: string;
	readonly observationDate: string;
	readonly candidateNotes: readonly NextDayPlanCandidateNote[];
	readonly nextDayPlan: string;
	readonly createdAt: string;
	readonly sourceJudgmentId: string | null;
};

export type NextDayPlanSummary = {
	readonly planId: string;
	readonly observationDate: string;
	readonly createdAt: string;
	readonly candidateCount: number;
	readonly nextDayPlan: string;
	readonly sourceJudgmentId: string | null;
};

function toPlan(value: PlanDTO): NextDayPlan {
	return {
		planId: value.plan_id,
		observationDate: value.observation_date,
		candidateNotes: value.candidate_notes.map((note) => ({
			instrumentId: note.instrument_id,
			reason: note.reason,
		})),
		nextDayPlan: value.next_day_plan,
		createdAt: value.created_at,
		sourceJudgmentId: value.source_judgment_id ?? null,
	};
}

export async function recordNextDayPlan(body: {
	readonly observationDate: string;
	readonly candidateNotes: readonly NextDayPlanCandidateNote[];
	readonly nextDayPlan: string;
	readonly sourceJudgmentId?: string;
}): Promise<NextDayPlan> {
	const result = await apiClient.post("/api/v1/market/next-day-plans", {
		body: {
			observation_date: body.observationDate,
			candidate_notes: body.candidateNotes.map((note) => ({
				instrument_id: note.instrumentId,
				reason: note.reason,
			})),
			next_day_plan: body.nextDayPlan,
			...(body.sourceJudgmentId !== undefined ? { source_judgment_id: body.sourceJudgmentId } : {}),
		} satisfies RecordBody,
	});
	if (!result.plan_id.startsWith("next-day-plan:sha256:")) {
		throw new Error("次日计划响应身份无效");
	}
	return toPlan(result);
}

export async function listNextDayPlans(observationDate?: string): Promise<NextDayPlanSummary[]> {
	const result = await apiClient.get("/api/v1/market/next-day-plans", {
		params: observationDate ? { query: { observation_date: observationDate } } : {},
	});
	return result.map((item: SummaryDTO) => ({
		planId: item.plan_id,
		observationDate: item.observation_date,
		createdAt: item.created_at,
		candidateCount: item.candidate_count,
		nextDayPlan: item.next_day_plan,
		sourceJudgmentId: item.source_judgment_id ?? null,
	}));
}

export async function fetchNextDayPlan(planId: string): Promise<NextDayPlan> {
	const result = await apiClient.get("/api/v1/market/next-day-plans/{plan_id}", {
		params: { path: { plan_id: planId } },
	});
	if (result.plan_id !== planId) throw new Error("次日计划响应身份不匹配");
	return toPlan(result);
}

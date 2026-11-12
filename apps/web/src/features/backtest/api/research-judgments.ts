import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type JudgmentDTO = components["schemas"]["ResearchJudgmentResponse"];
type SummaryDTO = components["schemas"]["ResearchJudgmentSummaryResponse"];
type RecordBody = components["schemas"]["CreateResearchJudgmentBody"];

export type ResearchJudgment = {
	readonly judgmentId: string;
	readonly runIds: readonly string[];
	readonly judgment: string;
	readonly createdAt: string;
	readonly strategyId: string | null;
	readonly strategyVersion: number | null;
};

export type ResearchJudgmentSummary = {
	readonly judgmentId: string;
	readonly runIds: readonly string[];
	readonly createdAt: string;
	readonly judgment: string;
	readonly strategyId: string | null;
	readonly strategyVersion: number | null;
};

function toJudgment(value: JudgmentDTO): ResearchJudgment {
	return {
		judgmentId: value.judgment_id,
		runIds: value.run_ids,
		judgment: value.judgment,
		createdAt: value.created_at,
		strategyId: value.strategy_id ?? null,
		strategyVersion: value.strategy_version ?? null,
	};
}

export async function recordResearchJudgment(body: {
	readonly runIds: readonly string[];
	readonly judgment: string;
	readonly strategyId?: string;
	readonly strategyVersion?: number;
}): Promise<ResearchJudgment> {
	const result = await apiClient.post("/api/v1/research/judgments", {
		body: {
			run_ids: [...body.runIds],
			judgment: body.judgment,
			...(body.strategyId !== undefined && body.strategyVersion !== undefined
				? { strategy_id: body.strategyId, strategy_version: body.strategyVersion }
				: {}),
		} satisfies RecordBody,
	});
	if (!result.judgment_id.startsWith("research-judgment:sha256:")) {
		throw new Error("研究判断响应身份无效");
	}
	return toJudgment(result);
}

export async function listResearchJudgments(): Promise<ResearchJudgmentSummary[]> {
	const result = await apiClient.get("/api/v1/research/judgments");
	return result.map((item: SummaryDTO) => ({
		judgmentId: item.judgment_id,
		runIds: item.run_ids,
		createdAt: item.created_at,
		judgment: item.judgment,
		strategyId: item.strategy_id ?? null,
		strategyVersion: item.strategy_version ?? null,
	}));
}

export async function fetchResearchJudgment(judgmentId: string): Promise<ResearchJudgment> {
	const result = await apiClient.get("/api/v1/research/judgments/{judgment_id}", {
		params: { path: { judgment_id: judgmentId } },
	});
	if (result.judgment_id !== judgmentId) throw new Error("研究判断响应身份不匹配");
	return toJudgment(result);
}

import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

/** 交接用例读取面：持久化的 SelectionRun→Research Case 证据重开。 */
export type ResearchCaseSummary = components["schemas"]["ResearchCaseSummaryResponse"];
export type ResearchCaseDetail = components["schemas"]["ResearchCaseResponse"];
export type ResearchCaseRun = components["schemas"]["SelectionRunResponse"];

export const researchCaseKeys = {
	list: ["research", "research-cases"] as const,
	detail: (caseId: string) => ["research", "research-case", caseId] as const,
	run: (runId: string) => ["research", "research-case-run", runId] as const,
};

export function fetchResearchCaseSummaries(limit = 20): Promise<readonly ResearchCaseSummary[]> {
	return apiClient.get("/api/v1/selections/research-cases", { params: { query: { limit } } });
}

export function fetchResearchCaseDetail(caseId: string): Promise<ResearchCaseDetail> {
	return apiClient.get("/api/v1/selections/research-cases/{case_id}", {
		params: { path: { case_id: caseId } },
	});
}

/** 候选名单的名字/排名解释来自来源运行的固定证据（append-only 读取）。 */
export function fetchResearchCaseRun(runId: string): Promise<ResearchCaseRun> {
	return apiClient.get("/api/v1/selections/runs/{run_id}", {
		params: { path: { run_id: runId } },
	});
}

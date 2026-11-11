import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

/** 模板交接提案读取面（/selections/runs/...：研究域端点，只读不落库）。 */
export type StrategyTemplateDraftProposal = components["schemas"]["StrategyTemplateDraftProposalResponse"];
export type HandoffConversion = components["schemas"]["HandoffConversionResponse"];
export type HandoffGap = components["schemas"]["HandoffGapResponse"];

export const strategyHandoffKeys = {
	proposal: (runId: string, templateId: string) => ["strategy-handoff", "proposal", runId, templateId] as const,
};

/** 从一条固定 SelectionRun（可带 Research Case 目标）形成模板草稿提案。 */
export function proposeStrategyTemplateDraft(
	runId: string,
	templateId: string,
	researchCaseId?: string,
): Promise<StrategyTemplateDraftProposal> {
	return apiClient.post("/api/v1/selections/runs/{run_id}/strategy-template-drafts", {
		params: { path: { run_id: runId } },
		body: {
			template_id: templateId,
			...(researchCaseId ? { research_case_id: researchCaseId } : {}),
		},
	});
}

import type { ReactElement } from "react";
import {
	ResearchCaseDetailPage,
	ResearchCaseStrategyHandoff,
	type StrategyHandoffCreateResult,
	type StrategyHandoffCreateTarget,
} from "@/features/research";
import { createStrategy, useStrategyTemplates } from "@/features/strategy";

/**
 * Strategy handoff workflow: compose the research-owned handoff panel with the
 * strategy feature's template catalog and real create command. The proposal
 * spec_json is submitted as-is (only strategy_id/name follow the edited form),
 * so the saved version keeps exactly the server-proposed configuration.
 */
async function createHandoffStrategy(
	target: StrategyHandoffCreateTarget,
	idempotencyKey: string,
): Promise<StrategyHandoffCreateResult> {
	const response = await createStrategy(
		{
			strategy_id: target.strategyId,
			name: target.name,
			spec_json: { ...target.specJson },
			tags: [...target.tags],
		},
		idempotencyKey,
	);
	return { strategyId: response.strategy_id, version: response.version };
}

/** Route-ready research case detail with the template handoff workspace. */
export function ResearchCaseDetailWithHandoff({ caseId }: { readonly caseId: string }): ReactElement {
	const catalog = useStrategyTemplates();
	return (
		<ResearchCaseDetailPage
			caseId={caseId}
			strategyHandoffSlot={(value) => {
				const options = (catalog.data ?? [])
					.filter((entry) => entry.asset_class === value.asset_kind)
					.map((entry) => ({
						templateId: entry.template_id,
						displayName: entry.display_name,
						description: entry.description,
					}));
				return (
					<ResearchCaseStrategyHandoff caseDetail={value} templates={options} createStrategy={createHandoffStrategy} />
				);
			}}
		/>
	);
}

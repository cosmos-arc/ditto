import type { ReactNode } from "react";
import { type DailyDecisionV3ViewModel, PortfolioOverviewPage, RiskPage } from "@/features/portfolio";
import { DecisionBriefing } from "./decision-briefing";

function renderDecisionBriefing(decision: DailyDecisionV3ViewModel): ReactNode {
	return <DecisionBriefing decision={decision} />;
}

export function PortfolioOverviewWithDecisionBriefing() {
	return <PortfolioOverviewPage renderDecisionBriefing={renderDecisionBriefing} />;
}

export function PortfolioRiskWithDecisionBriefing() {
	return <RiskPage renderDecisionBriefing={renderDecisionBriefing} />;
}

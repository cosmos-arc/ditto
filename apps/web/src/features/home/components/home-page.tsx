import { CommandCenterLayout } from "@/features/shell";
import { PulseSection } from "./pulse-section";
import { BannerSection } from "./banner-section";
import { PriorityQueueSection } from "./priority-queue-section";
import { ResearchProgressSection } from "./research-progress-section";
import { AgentFindingsSection } from "./agent-findings-section";
import { MarketPulseSection } from "./market-pulse-section";
import { GlobalAlertsSection } from "./global-alerts-section";
import { DataHealthSection } from "./data-health-section";

/**
 * HomePage — Command Center layout.
 * Matches prototype: pulse strip (full width) + main/sidebar.
 *
 * Main area:
 *   - main-primary: Decision Banner + Priority Queue panel
 *   - shell-secondary: Research Progress + Agent Findings (side by side)
 *
 * Sidebar (context rail):
 *   - Market Pulse (metrics)
 *   - Global Alerts (alert rows with dots)
 *   - Data Health (health gauge + items)
 */
export function HomePage() {
	return (
		<CommandCenterLayout
			pulse={<PulseSection />}
			main={
				<div className="flex min-h-0 flex-col gap-[calc(var(--density-gutter)+var(--spacing-2))] p-(--density-panel-padding)">
					{/* main-primary: Decision Banner + Priority Queue */}
					<div className="flex max-h-[66%] flex-none flex-col gap-[var(--section-gap)] overflow-hidden">
						<BannerSection />
						<PriorityQueueSection />
					</div>

					{/* shell-secondary: Research + Findings side by side */}
					<div className="grid min-h-0 flex-1 grid-cols-2 gap-[var(--density-gutter)] overflow-hidden">
						<ResearchProgressSection />
						<AgentFindingsSection />
					</div>
				</div>
			}
			sidebar={
				<div data-slot="sidebar-rail" className="flex flex-col overflow-y-auto overflow-x-hidden border-l border-(--color-border-subtle)">
					<MarketPulseSection />
					<div className="border-t border-(--color-border-subtle)">
						<GlobalAlertsSection />
					</div>
					<div className="border-t border-(--color-border-subtle)">
						<DataHealthSection />
					</div>
				</div>
			}
		/>
	);
}

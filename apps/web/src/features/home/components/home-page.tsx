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
 * Layout measurements from prototype (page-home.html):
 *   shell-main: flex column, padding 16px, gap 24px
 *   main-primary: measured 507px track at 1536x900, gap 12px
 *   shell-secondary: grid 1fr/1fr, flex 1
 */
export function HomePage() {
	return (
		<CommandCenterLayout
			pulse={<PulseSection />}
			main={
				<div data-slot="home-main" className="flex h-full min-h-0 flex-col gap-6 p-(--density-panel-padding)">
					{/* main-primary: Decision Banner + Priority Queue */}
					<div data-slot="home-primary" className="flex min-h-0 basis-[507px] flex-none flex-col gap-3 overflow-hidden">
						<BannerSection />
						<PriorityQueueSection />
						<div aria-hidden="true" className="h-[142px] flex-none" />
					</div>

					{/* shell-secondary: Research + Findings side by side */}
					<div data-slot="home-secondary" className="grid min-h-0 flex-1 grid-cols-2 gap-(--density-gutter) overflow-hidden">
						<ResearchProgressSection />
						<AgentFindingsSection />
					</div>
				</div>
			}
			sidebar={
				<div
					data-slot="sidebar-rail"
					className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden border-l border-(--color-border-subtle)"
				>
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

import { CommandCenterLayout } from "@/features/shell";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";
import { SidebarToggle } from "@/features/shell/components/sidebar-toggle";
import { PulseSection } from "./pulse-section";
import { BannerSection } from "./banner-section";
import { PriorityQueueSection } from "./priority-queue-section";
import { ResearchProgressSection } from "./research-progress-section";
import { AgentFindingsSection } from "./agent-findings-section";
import { WorkspacePlaceholder } from "./workspace-placeholder";
import { MarketPulseSection } from "./market-pulse-section";
import { GlobalAlertsSection } from "./global-alerts-section";
import { DataHealthSection } from "./data-health-section";
import { HomeCollapsedSidebar } from "./home-collapsed-sidebar";

/**
 * HomePage — Command Center layout.
 * Matches prototype: pulse strip (full width) + main/sidebar.
 *
 * Layout measurements from prototype (page-home.html):
 *   shell-main: flex column, padding 16px, gap 24px
 *   main-primary: flex 0 0 auto, max-height 66%, gap var(--density-section-gap)
 *   shell-secondary: grid 1fr/1fr, flex 1
 */
export function HomePage() {
	const { sidebarCollapsed, toggleSidebarCollapsed } = useUIPreferences();

	return (
		<CommandCenterLayout
			pulse={<PulseSection />}
			main={
				<div
					data-slot="home-main"
					className="flex h-full min-h-0 flex-col gap-[calc(var(--density-gutter)+var(--space-8))] p-[var(--density-gutter)]"
				>
					{/* main-primary: Decision Banner + Priority Queue + Workspace Placeholder */}
					<div
						data-slot="home-primary"
						className="flex min-h-0 max-h-[66%] flex-none flex-col gap-(--density-section-gap) overflow-hidden"
					>
						<BannerSection />
						<PriorityQueueSection />
						<WorkspacePlaceholder />
					</div>

					{/* shell-secondary: Research + Findings side by side */}
					<div
						data-slot="home-secondary"
						className="grid min-h-0 flex-1 grid-cols-2 gap-[var(--density-gutter)] overflow-hidden"
					>
						<ResearchProgressSection />
						<AgentFindingsSection />
					</div>
				</div>
			}
			sidebar={
				sidebarCollapsed ? (
					<HomeCollapsedSidebar onExpand={toggleSidebarCollapsed} />
				) : (
					<div
						data-slot="sidebar-rail"
						className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden border-l border-(--color-border-subtle)"
					>
						<MarketPulseSection />
						<GlobalAlertsSection />
						<DataHealthSection />
						<SidebarToggle />
					</div>
				)
			}
			sidebarCollapsed={sidebarCollapsed}
		/>
	);
}

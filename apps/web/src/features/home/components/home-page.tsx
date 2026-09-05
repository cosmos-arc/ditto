import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CommandCenterLayout, SidebarToggle, useUIPreferences } from "@/features/shell";
import type { PendingAction } from "@/types";
import type { LoadMarketContext } from "../hooks";
import { AgentFindingsSection } from "./agent-findings-section";
import { BannerSection } from "./banner-section";
import { DataHealthSection } from "./data-health-section";
import { GlobalAlertsSection } from "./global-alerts-section";
import { HomeCollapsedSidebar } from "./home-collapsed-sidebar";
import {
	HomeDecisionEvidenceDrawer,
	HomeOrderHandoffDialog,
	HomeSignalEvidenceDrawer,
	HomeWorkspaceSettingsSheet,
} from "./home-overlays";
import { MarketPulseSection } from "./market-pulse-section";
import { PriorityQueueSection } from "./priority-queue-section";
import { PulseSection } from "./pulse-section";
import { ResearchProgressSection } from "./research-progress-section";

/**
 * HomePage — Command Center layout.
 * Matches prototype: pulse strip (full width) + main/sidebar.
 *
 * Layout measurements from prototype (page-home.html):
 *   shell-main: flex column, padding 16px, gap 24px
 *   main-primary: flex 0 0 auto, content-sized, gap var(--density-section-gap)
 *   shell-secondary: grid 1fr/1fr, flex 1
 */
export function HomePage({ loadMarketContext }: { readonly loadMarketContext?: LoadMarketContext | undefined }) {
	const { sidebarCollapsed, toggleSidebarCollapsed } = useUIPreferences();
	const [selectedAction, setSelectedAction] = useState<PendingAction | null>(null);
	const [signalEvidenceOpen, setSignalEvidenceOpen] = useState(false);
	const [orderHandoffOpen, setOrderHandoffOpen] = useState(false);
	const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
	const [decisionEvidenceOpen, setDecisionEvidenceOpen] = useState(false);

	const selectAction = (action: PendingAction) => {
		setSelectedAction(action);
		setSignalEvidenceOpen(true);
	};

	const prepareOrderHandoff = () => {
		setSignalEvidenceOpen(false);
		setOrderHandoffOpen(true);
	};

	return (
		<>
			<CommandCenterLayout
				pulse={<PulseSection />}
				main={
					<div
						data-slot="home-main"
						className="relative flex h-full min-h-0 flex-col gap-(--density-section-gap) overflow-hidden px-(--density-gutter) pt-[43px] pb-(--density-gutter)"
					>
						<div
							aria-hidden="true"
							className="absolute top-4 right-(--density-gutter) left-(--density-gutter) border-t border-(--color-border-subtle)"
						/>
						<div className="absolute top-2 right-(--density-gutter) flex items-center gap-2">
							<Button
								type="button"
								variant="ghost"
								size="sm"
								aria-label="决策证据"
								title="决策证据"
								className="max-[1279px]:w-7 max-[1279px]:border-transparent max-[1279px]:bg-transparent max-[1279px]:px-0"
								onClick={() => setDecisionEvidenceOpen(true)}
							>
								<svg
									aria-hidden="true"
									className="hidden opacity-10 max-[1279px]:block"
									viewBox="0 0 20 20"
									fill="none"
								>
									<path d="M5 3.5h10v13H5zM7.5 7h5M7.5 10h5M7.5 13h3" stroke="currentColor" strokeWidth="1.4" />
								</svg>
								<span className="max-[1279px]:sr-only">决策证据</span>
							</Button>
							<Button
								type="button"
								variant="outline"
								size="sm"
								aria-label="工作台设置"
								title="工作台设置"
								className="max-[1279px]:w-7 max-[1279px]:border-transparent max-[1279px]:bg-transparent max-[1279px]:px-0"
								onClick={() => setWorkspaceSettingsOpen(true)}
							>
								<svg
									aria-hidden="true"
									className="hidden opacity-10 max-[1279px]:block"
									viewBox="0 0 20 20"
									fill="none"
								>
									<circle cx="10" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.4" />
									<path
										d="M10 3v2M10 15v2M3 10h2M15 10h2M5.1 5.1l1.4 1.4M13.5 13.5l1.4 1.4M14.9 5.1l-1.4 1.4M6.5 13.5l-1.4 1.4"
										stroke="currentColor"
										strokeWidth="1.4"
										strokeLinecap="round"
									/>
								</svg>
								<span className="max-[1279px]:sr-only">工作台设置</span>
							</Button>
						</div>
						{/* main-primary: Decision Banner + Priority Queue + Workspace Placeholder */}
						<div
							data-slot="home-primary"
							className="flex min-h-0 flex-none flex-col gap-(--density-section-gap) overflow-hidden"
						>
							<BannerSection />
							<PriorityQueueSection onSelectAction={selectAction} />
						</div>

						{/* shell-secondary: Research + Findings side by side */}
						<div
							data-slot="home-secondary"
							className="grid h-[508px] min-h-0 flex-none grid-cols-2 gap-[var(--density-gutter)] overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
						>
							<ResearchProgressSection />
							<AgentFindingsSection loadMarketContext={loadMarketContext} />
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
							<MarketPulseSection loadMarketContext={loadMarketContext} />
							<GlobalAlertsSection />
							<DataHealthSection />
							<SidebarToggle />
						</div>
					)
				}
				sidebarCollapsed={sidebarCollapsed}
			/>
			<HomeSignalEvidenceDrawer
				open={signalEvidenceOpen}
				onOpenChange={setSignalEvidenceOpen}
				action={selectedAction}
				onPrepareOrder={prepareOrderHandoff}
			/>
			<HomeOrderHandoffDialog open={orderHandoffOpen} onOpenChange={setOrderHandoffOpen} action={selectedAction} />
			<HomeWorkspaceSettingsSheet
				open={workspaceSettingsOpen}
				onOpenChange={setWorkspaceSettingsOpen}
				sidebarCollapsed={sidebarCollapsed}
				onToggleSidebar={toggleSidebarCollapsed}
			/>
			<HomeDecisionEvidenceDrawer open={decisionEvidenceOpen} onOpenChange={setDecisionEvidenceOpen} />
		</>
	);
}

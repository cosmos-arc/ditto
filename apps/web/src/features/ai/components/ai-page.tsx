import { CommandCenterLayout, StatusBar } from "@/features/shell";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";
import { SidebarToggle } from "@/features/shell/components/sidebar-toggle";
import { AiPulseStrip } from "./ai-pulse-strip";
import { AiMainContent } from "./ai-main-content";
import { AiContextSidebar } from "./ai-context-sidebar";
import { AiCollapsedSidebar } from "./ai-collapsed-sidebar";

export function AiPage() {
	const { sidebarCollapsed, toggleSidebarCollapsed } = useUIPreferences();

	return (
		<>
			<CommandCenterLayout
				className="pb-(--height-status-bar)"
				pulse={<AiPulseStrip />}
				main={<AiMainContent />}
				sidebar={
					sidebarCollapsed ? (
						<AiCollapsedSidebar onExpand={toggleSidebarCollapsed} />
					) : (
						<div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden border-l border-(--color-border-subtle)">
							<AiContextSidebar />
							<SidebarToggle />
						</div>
					)
				}
				sidebarCollapsed={sidebarCollapsed}
			/>
			<StatusBar />
		</>
	);
}

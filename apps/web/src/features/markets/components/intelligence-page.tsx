import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";
import { SidebarToggle } from "@/features/shell/components/sidebar-toggle";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { IntelligenceFlowView } from "./intelligence-flow-view";
import { IntelligenceMacroView } from "./intelligence-macro-view";
import { IntelligenceFundamentalsView } from "./intelligence-fundamentals-view";
import { IntelligenceCollapsedSidebar } from "./intelligence-collapsed-sidebar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export function IntelligencePage() {
	const { sidebarCollapsed, toggleSidebarCollapsed } = useUIPreferences();

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={
					<div className="flex items-center gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
						<span className="text-xs font-medium text-(--color-foreground-tertiary)">市场智能</span>
						<span className="text-xs text-(--color-foreground-muted)">|</span>
						<span className="text-xs text-(--color-foreground-secondary)">实时资金流向 + 宏观指标追踪</span>
					</div>
				}
				main={
					<div className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)">
						<Tabs defaultValue="flow" className="flex flex-col gap-(--section-gap)">
							<TabsList>
								<TabsTrigger value="flow">资金流向</TabsTrigger>
								<TabsTrigger value="macro">宏观指标</TabsTrigger>
								<TabsTrigger value="fundamentals">基本面</TabsTrigger>
							</TabsList>
							<TabsContent value="flow">
								<IntelligenceFlowView />
							</TabsContent>
							<TabsContent value="macro">
								<IntelligenceMacroView />
							</TabsContent>
							<TabsContent value="fundamentals">
								<IntelligenceFundamentalsView />
							</TabsContent>
						</Tabs>
					</div>
				}
				activity={
					sidebarCollapsed ? (
						<IntelligenceCollapsedSidebar onExpand={toggleSidebarCollapsed} />
					) : (
						<div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden border-l border-(--color-border-subtle)">
							<Panel data-info-level="l1" data-info-unit="ai-interpretation">
								<PanelHeader title="AI 解读" />
								<PanelBody className="p-3">
									<div className="space-y-3 text-sm text-(--color-foreground-secondary)">
										<p>科技板块资金流入加速，北向资金偏好成长方向。PMI 回升至 50.4 表明制造业企稳。</p>
										<p className="text-xs text-(--color-foreground-tertiary)">由 AI 自动生成 · 5 分钟前更新</p>
									</div>
								</PanelBody>
							</Panel>
							<SidebarToggle />
						</div>
					)
				}
				analysis={
					<div data-info-level="l2" data-info-unit="analysis-panel" className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
						<span className="text-xs text-(--color-foreground-tertiary)">市场分析 · 待实现</span>
					</div>
				}
				activityCollapsed={sidebarCollapsed}
			/>
			<StatusBar />
		</>
	);
}

import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { IntelligenceFlowView } from "./intelligence-flow-view";
import { IntelligenceMacroView } from "./intelligence-macro-view";
import { IntelligenceFundamentalsView } from "./intelligence-fundamentals-view";

export function IntelligencePage() {
	return (
		<AnalyticalLayout
			main={
				<div className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)">
					<IntelligenceFlowView />
					<div className="grid grid-cols-2 gap-(--density-gutter)">
						<IntelligenceMacroView />
						<IntelligenceFundamentalsView />
					</div>
				</div>
			}
			activity={
				<Panel>
					<PanelHeader title="AI 解读" />
					<PanelBody className="p-3">
						<div className="space-y-3 text-sm text-(--color-foreground-secondary)">
							<p>科技板块资金流入加速，北向资金偏好成长方向。PMI 回升至 50.4 表明制造业企稳。</p>
							<p className="text-xs text-(--color-foreground-tertiary)">由 AI 自动生成 · 5 分钟前更新</p>
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}

import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { ResearchPulseStrip } from "./research-pulse-strip";
import { FactorTable } from "./factor-table";
import { RecentRuns } from "./recent-runs";
import { ExperimentQueue } from "./experiment-queue";

export function ResearchPage() {
	return (
		<AnalyticalLayout
			strip={<ResearchPulseStrip />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<FactorTable />
				</div>
			}
			activity={
				<div className="flex flex-col gap-[var(--density-gutter)]">
					<Panel className="flex-1">
						<PanelHeader
							title="最近运行"
							actions={
								<button type="button" className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-(--radius-sm) px-1.5 py-0.5">
									查看全部 →
								</button>
							}
						/>
						<PanelBody className="p-3">
							<RecentRuns />
						</PanelBody>
					</Panel>
					<Panel className="flex-1">
						<PanelHeader
							title="实验队列"
							actions={
								<button type="button" className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-(--radius-sm) px-1.5 py-0.5">
									查看全部 →
								</button>
							}
						/>
						<PanelBody className="p-3">
							<ExperimentQueue />
						</PanelBody>
					</Panel>
				</div>
			}
			analysis={
				<Panel>
					<PanelHeader title="IC 趋势" />
					<PanelBody className="flex items-center justify-center p-6">
						<div className="text-center text-xs text-(--color-foreground-tertiary)">
							<p>因子 IC 趋势和因子相关性分析</p>
							<p className="mt-1">图表组件待实现</p>
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}

import { PrototypeOnlyEmpty } from "@/components/domain/prototype-only-empty";
import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { shouldUsePrototypeMocks } from "@/features/trading/api/runtime";
import { ResearchPulseStrip } from "./research-pulse-strip";
import { FactorTable } from "./factor-table";
import { RecentRuns } from "./recent-runs";
import { ExperimentQueue } from "./experiment-queue";
import { AnalysisBand } from "./analysis-band";

export function ResearchPage() {
	if (!shouldUsePrototypeMocks()) {
		return <PrototypeOnlyEmpty domain="Research" />;
	}

	return (
		<AnalyticalLayout
			strip={<div data-info-level="l1" data-info-unit="research-pulse-strip"><ResearchPulseStrip /></div>}
			main={
				<div data-info-level="l1" data-info-unit="factor-table" className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<FactorTable />
				</div>
			}
			activity={
				<div className="flex flex-col gap-(--density-gutter)">
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
							<div data-info-level="l1" data-info-unit="recent-runs">
								<RecentRuns />
							</div>
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
							<div data-info-level="l1" data-info-unit="experiment-queue">
								<ExperimentQueue />
							</div>
						</PanelBody>
					</Panel>
				</div>
			}
			analysis={
				<div data-info-level="l2" data-info-unit="analysis-band">
					<Panel>
						<AnalysisBand />
					</Panel>
				</div>
			}
		/>
	);
}

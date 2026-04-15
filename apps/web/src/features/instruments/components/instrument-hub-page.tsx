import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout, StatusBar } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";
import { InstrumentChartView } from "./instrument-chart-view";

export function InstrumentHubPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const instrumentId = id ?? "";

	return (
		<>
		<Tabs defaultValue="overview" className="h-full">
			<ObjectHubLayout
				className="pb-(--height-status-bar)"
				meta={
					<div data-info-level="l1" data-info-unit="instrument-meta">
						<InstrumentMetaStrip id={instrumentId} />
					</div>
				}
				tabs={
					<div data-info-level="l1" data-info-unit="instrument-tabs">
						<TabsList>
							<TabsTrigger value="overview">概览</TabsTrigger>
							<TabsTrigger value="chart">行情</TabsTrigger>
							<TabsTrigger value="fundamentals">基本面</TabsTrigger>
						</TabsList>
					</div>
				}
				main={
					<>
						<TabsContent value="overview">
							<div data-info-level="l1" data-info-unit="instrument-overview">
								<InstrumentOverview id={instrumentId} />
							</div>
						</TabsContent>
						<TabsContent value="chart">
							<div data-info-level="l1" data-info-unit="instrument-chart">
								<InstrumentChartView id={instrumentId} />
							</div>
						</TabsContent>
						<TabsContent value="fundamentals">
							<div data-info-level="l1" data-info-unit="instrument-fundamentals">
								<InstrumentOverview id={instrumentId} />
							</div>
						</TabsContent>
					</>
				}
				bottom={
					<div className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
						<span className="text-xs text-(--color-foreground-tertiary)">价格走势 · 待实现</span>
					</div>
				}
			/>
		</Tabs>
		<StatusBar />
		</>
	);
}

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
				meta={<InstrumentMetaStrip id={instrumentId} />}
				tabs={
					<TabsList>
						<TabsTrigger value="overview">概览</TabsTrigger>
						<TabsTrigger value="chart">行情</TabsTrigger>
						<TabsTrigger value="fundamentals">基本面</TabsTrigger>
					</TabsList>
				}
				main={
					<>
						<TabsContent value="overview">
							<InstrumentOverview id={instrumentId} />
						</TabsContent>
						<TabsContent value="chart">
							<InstrumentChartView id={instrumentId} />
						</TabsContent>
						<TabsContent value="fundamentals">
							<InstrumentOverview id={instrumentId} />
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

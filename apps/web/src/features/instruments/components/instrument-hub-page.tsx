import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";

export function InstrumentHubPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const instrumentId = id ?? "";

	return (
		<Tabs defaultValue="overview">
			<ObjectHubLayout
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
							<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
								行情图表 — 待实现
							</div>
						</TabsContent>
						<TabsContent value="fundamentals">
							<InstrumentOverview id={instrumentId} />
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}

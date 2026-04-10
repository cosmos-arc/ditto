import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { StrategyDetailMeta } from "./strategy-detail-meta";
import { StrategyVersionsView } from "./strategy-versions-view";
import { StrategyOverview } from "./strategy-overview";
import { StrategyFactorsView } from "./strategy-factors-view";

export function StrategyDetailPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const strategyId = id ?? "";

	return (
		<Tabs defaultValue="overview">
			<ObjectHubLayout
				meta={<StrategyDetailMeta id={strategyId} />}
				tabs={
					<TabsList>
						<TabsTrigger value="overview">概览</TabsTrigger>
						<TabsTrigger value="versions">版本</TabsTrigger>
						<TabsTrigger value="factors">因子</TabsTrigger>
					</TabsList>
				}
				main={
					<>
						<TabsContent value="overview">
							<StrategyOverview id={strategyId} />
						</TabsContent>
						<TabsContent value="versions">
							<StrategyVersionsView id={strategyId} />
						</TabsContent>
						<TabsContent value="factors">
							<StrategyFactorsView id={strategyId} />
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}

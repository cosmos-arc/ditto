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
				meta={
					<div data-info-level="l1" data-info-unit="strategy-meta">
						<StrategyDetailMeta id={strategyId} />
					</div>
				}
				tabs={
					<div data-info-level="l1" data-info-unit="strategy-detail-tabs">
						<TabsList>
							<TabsTrigger value="overview">概览</TabsTrigger>
							<TabsTrigger value="versions">版本</TabsTrigger>
							<TabsTrigger value="factors">因子</TabsTrigger>
						</TabsList>
					</div>
				}
				main={
					<>
						<TabsContent value="overview">
							<div data-info-level="l1" data-info-unit="strategy-overview">
								<StrategyOverview id={strategyId} />
							</div>
						</TabsContent>
						<TabsContent value="versions">
							<div data-info-level="l1" data-info-unit="strategy-versions">
								<StrategyVersionsView id={strategyId} />
							</div>
						</TabsContent>
						<TabsContent value="factors">
							<div data-info-level="l1" data-info-unit="strategy-factors">
								<StrategyFactorsView id={strategyId} />
							</div>
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}

import { useParams } from "@tanstack/react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ObjectHubLayout } from "@/features/shell";
import { FactorAnalysisView } from "./factor-analysis-view";
import { FactorDetailHeader } from "./factor-detail-header";
import { FactorOverview } from "./factor-overview";

export function FactorPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const factorId = id ?? "";

	return (
		<Tabs defaultValue="overview">
			<ObjectHubLayout
				meta={
					<div data-info-level="l1" data-info-unit="factor-meta">
						<FactorDetailHeader id={factorId} />
					</div>
				}
				tabs={
					<div data-info-level="l1" data-info-unit="factor-tabs">
						<TabsList>
							<TabsTrigger value="overview">概览</TabsTrigger>
							<TabsTrigger value="analysis">分析</TabsTrigger>
						</TabsList>
					</div>
				}
				main={
					<>
						<TabsContent value="overview">
							<div data-info-level="l1" data-info-unit="factor-overview">
								<FactorOverview id={factorId} />
							</div>
						</TabsContent>
						<TabsContent value="analysis">
							<div data-info-level="l1" data-info-unit="factor-analysis">
								<FactorAnalysisView id={factorId} />
							</div>
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}

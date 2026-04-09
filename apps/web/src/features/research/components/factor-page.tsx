import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { FactorDetailHeader } from "./factor-detail-header";
import { FactorAnalysisView } from "./factor-analysis-view";

export function FactorPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const factorId = id ?? "";

	return (
		<Tabs defaultValue="overview">
			<ObjectHubLayout
				meta={<FactorDetailHeader id={factorId} />}
				tabs={
					<TabsList>
						<TabsTrigger value="overview">概览</TabsTrigger>
						<TabsTrigger value="analysis">分析</TabsTrigger>
					</TabsList>
				}
				main={
					<>
						<TabsContent value="overview">
							<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
								因子概览 — 待实现
							</div>
						</TabsContent>
						<TabsContent value="analysis">
							<FactorAnalysisView id={factorId} />
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}

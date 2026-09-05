import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ObjectHubLayout, ShellHeaderExtension } from "@/features/shell";
import { useStrategy } from "../hooks";
import type { StrategyGovernanceActionsRenderer } from "./governance-actions";
import { StrategyDetailMeta } from "./strategy-detail-meta";
import { type StrategyDetailOverlay, StrategyDetailOverlays } from "./strategy-detail-overlays";
import { StrategyFactorsView } from "./strategy-factors-view";
import { StrategyOverview } from "./strategy-overview";
import { StrategyVersionsView } from "./strategy-versions-view";

type DetailTab = "overview" | "versions" | "factors";

interface StrategyDetailPageProps {
	readonly renderGovernanceActions: StrategyGovernanceActionsRenderer;
}

export function StrategyDetailPage({ renderGovernanceActions }: StrategyDetailPageProps) {
	const { id } = useParams({ strict: false }) as { id: string };
	const strategyId = id ?? "";
	const detail = useStrategy(strategyId);
	const [tab, setTab] = useState<DetailTab>("overview");
	const [overlay, setOverlay] = useState<StrategyDetailOverlay | null>(null);

	return (
		<section aria-label="策略详情工作区" className="h-full min-h-0">
			<ShellHeaderExtension>
				<div className="ml-auto flex items-center gap-1.5">
					<Button asChild size="sm">
						<Link to="/research/strategies/$id/studio" params={{ id: strategyId }}>
							编辑策略
						</Link>
					</Button>
					<Button size="sm" variant="outline" onClick={() => setOverlay("backtest")} disabled={!detail.data}>
						提交回测
					</Button>
					<Button size="sm" variant="outline" onClick={() => setOverlay("copy")} disabled={!detail.data}>
						复制策略
					</Button>
					<Button size="sm" variant="outline" onClick={() => setOverlay("rollback")} disabled={!detail.data}>
						版本回滚
					</Button>
					<Button size="sm" variant="destructive" onClick={() => setOverlay("deprecate")} disabled={!detail.data}>
						弃用策略
					</Button>
				</div>
			</ShellHeaderExtension>
			<Tabs value={tab} onValueChange={(value) => setTab(value as DetailTab)} className="h-full min-h-0 gap-0">
				<ObjectHubLayout
					className="grid-rows-[36px_45px_1fr_36px]"
					meta={
						<div data-info-level="l1" data-info-unit="strategy-meta" data-testid="strategy-detail-meta">
							<StrategyDetailMeta id={strategyId} />
						</div>
					}
					tabs={
						<nav
							aria-label="策略详情导航"
							data-info-level="l1"
							data-info-unit="strategy-detail-tabs"
							data-testid="strategy-detail-tabs"
							className="h-[45px] border-y border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<TabsList variant="line" className="h-full">
								<TabsTrigger value="overview">概览</TabsTrigger>
								<TabsTrigger value="versions">版本</TabsTrigger>
								<TabsTrigger value="factors">因子</TabsTrigger>
							</TabsList>
						</nav>
					}
					main={
						<>
							<TabsContent value="overview" className="m-0 h-full min-h-0 overflow-auto">
								<div data-info-level="l1" data-info-unit="strategy-overview" data-testid="strategy-detail-main">
									<StrategyOverview id={strategyId} />
								</div>
							</TabsContent>
							<TabsContent value="versions" className="m-0 h-full min-h-0 overflow-auto">
								<div data-info-level="l1" data-info-unit="strategy-versions">
									<StrategyVersionsView id={strategyId} renderGovernanceActions={renderGovernanceActions} />
								</div>
							</TabsContent>
							<TabsContent value="factors" className="m-0 h-full min-h-0 overflow-auto">
								<div data-info-level="l1" data-info-unit="strategy-factors">
									<StrategyFactorsView id={strategyId} />
								</div>
							</TabsContent>
						</>
					}
					bottom={
						<div
							data-testid="strategy-detail-bottom"
							className="flex h-9 items-center gap-5 border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 text-[11px] text-(--color-foreground-tertiary)"
						>
							<span>
								Universe{" "}
								<strong className="font-data font-medium text-(--color-foreground-secondary)">
									{detail.data?.spec.universe ?? "—"}
								</strong>
							</span>
							<span>
								当前版本{" "}
								<strong className="font-data font-medium text-(--color-foreground-secondary)">
									v{detail.data?.version ?? "—"}
								</strong>
							</span>
							<span>
								绩效证据 <strong className="font-medium text-(--color-foreground-secondary)">未评估</strong>
							</span>
							<span className="ml-auto">定义与治理来自服务端；回测证据需实验制品</span>
						</div>
					}
				/>
			</Tabs>
			<StrategyDetailOverlays
				open={overlay}
				onClose={() => setOverlay(null)}
				onOpenVersions={() => setTab("versions")}
				strategyId={strategyId}
				detail={detail.data}
				detailLoading={detail.isLoading}
			/>
		</section>
	);
}

import { Link, useParams } from "@tanstack/react-router";
import { type ReactNode, useRef, useState } from "react";
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
	readonly renderBacktestForm?: (strategyId: string, version: number) => ReactNode;
	readonly renderGovernanceActions: StrategyGovernanceActionsRenderer;
	/** 研究判断回程上下文（#748）：来自比较视图「进入验证」链接时不为空。 */
	readonly fromJudgment?: string;
}

export function StrategyDetailPage({
	renderGovernanceActions,
	renderBacktestForm,
	fromJudgment = "",
}: StrategyDetailPageProps) {
	const { id } = useParams({ strict: false }) as { id: string };
	const strategyId = id ?? "";
	const detail = useStrategy(strategyId);
	const [tab, setTab] = useState<DetailTab>("overview");
	const [overlay, setOverlay] = useState<StrategyDetailOverlay | null>(null);
	const backtestButton = useRef<HTMLButtonElement>(null);

	return (
		<section aria-label="策略详情工作区" className="h-full min-h-0">
			{fromJudgment.trim() && (
				<div
					data-testid="strategy-judgment-return"
					className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-(--color-border-subtle) bg-(--color-interaction-hover-subtle-bg) px-3 py-2 text-xs leading-5"
				>
					<span className="font-medium text-(--color-foreground)">研究判断验证入口</span>
					<span className="break-all font-mono text-(--color-foreground-tertiary)">{fromJudgment}</span>
					{/* 回程入口：判断来自比较视图（会话集合在目录页重开）。
					    来源缺失（直接进入策略页）时不虚构返回目标。 */}
					<a
						href="/research/backtests"
						className="font-medium text-(--color-accent) underline underline-offset-2 hover:text-(--brand-accent-hover) focus-visible:outline-2 focus-visible:outline-offset-2"
					>
						返回研究判断
					</a>
				</div>
			)}
			<ShellHeaderExtension>
				<div className="ml-auto flex items-center gap-1.5">
					<Button asChild size="sm">
						<Link to="/research/strategies/$id/studio" params={{ id: strategyId }}>
							编辑策略
						</Link>
					</Button>
					<Button
						ref={backtestButton}
						size="sm"
						variant="outline"
						onClick={() => setOverlay("backtest")}
						disabled={!detail.data}
					>
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
							<span className="ml-auto">定义与治理来自服务端；研究回测不代表已获交易资格</span>
						</div>
					}
				/>
			</Tabs>
			<StrategyDetailOverlays
				onBacktestCloseAutoFocus={() => backtestButton.current?.focus()}
				backtestForm={detail.data ? renderBacktestForm?.(strategyId, detail.data.version) : null}
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

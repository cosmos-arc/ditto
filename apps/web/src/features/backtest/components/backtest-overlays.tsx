import { useQueries } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";
import { fetchBacktestRun } from "../api/backtests";
import { comparisonLifetime, useBacktestComparison } from "../hooks/use-backtest-comparison";
import { backtestKeys } from "../hooks/use-backtest-resources";
import type { BacktestRun } from "../types";
import { BacktestMultiRunCompare } from "./backtest-multi-run-compare";

export type BacktestOverlayId = "export" | "enable-signal" | "ai-analysis" | "compare";

export const backtestActions = [
	{ id: "export", label: "导出报告" },
	{ id: "enable-signal", label: "提交信号治理" },
	{ id: "ai-analysis", label: "AI 解读" },
	{ id: "compare-toggle", label: "加入对比" },
	{ id: "compare", label: "对比视图" },
] as const;

const copy = {
	export: { title: "导出回测报告", description: "导出本次运行、已发布报告、逐日规则与状态、冻结来源。", kind: "sheet" },
	"enable-signal": {
		title: "启用信号确认",
		description: "回测不能直接启用交易信号，只能进入策略治理。",
		kind: "alert-dialog",
	},
	"ai-analysis": { title: "AI 解读", description: "Agent 只基于当前回测证据回答，不成为统计裁判。", kind: "drawer" },
} as const;

export function BacktestOverlays({
	active,
	agentActions,
	exportError,
	exportPending,
	onClose,
	onExport,
	period,
	runId,
	strategyIdentity,
}: {
	readonly active: BacktestOverlayId | null;
	readonly agentActions: ReactNode;
	readonly exportError: string;
	readonly exportPending: boolean;
	readonly onClose: () => void;
	readonly onExport: () => void;
	readonly period: string;
	readonly runId: string;
	readonly strategyIdentity: string;
}) {
	if (!active) return null;
	if (active === "compare") return <BacktestCompareOverlay open onClose={onClose} />;
	const details = copy[active];
	const actions =
		active === "export" ? (
			<Button type="button" onClick={onExport} disabled={exportPending}>
				{exportPending ? "正在读取导出证据…" : "下载 JSON"}
			</Button>
		) : active === "enable-signal" ? (
			<a
				className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
				href="/research/reviews"
			>
				进入策略审查
			</a>
		) : undefined;

	return (
		<PageActionOverlay {...details} open onClose={onClose} actions={actions}>
			{active === "export" && exportError ? <p role="alert">导出失败：{exportError} 请重试下载。</p> : null}
			<OverlayFactList
				facts={[
					["Run", runId],
					["Strategy", strategyIdentity],
					["Period", period],
					["Evidence mode", "published resources only"],
				]}
			/>
			{active === "ai-analysis" && agentActions}
			{active === "enable-signal" && (
				<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs text-(--color-risk-warning-fg)">
					不会从此 overlay 发布策略、修改权重或创建 Paper 订单。
				</p>
			)}
		</PageActionOverlay>
	);
}

export function BacktestCompareOverlay({ onClose, open }: { readonly onClose: () => void; readonly open: boolean }) {
	const { runIds, error, setIncluded } = useBacktestComparison();
	const queries = useQueries({
		queries: runIds.map((runId) => ({
			queryKey: backtestKeys.run(runId),
			queryFn: () => fetchBacktestRun(runId),
			enabled: open,
		})),
	});
	const runs = queries.flatMap((query): BacktestRun[] => (query.data && !query.isError ? [query.data] : []));
	return (
		<PageActionOverlay
			open={open}
			kind="drawer"
			title="回测对比"
			description="按服务端 run identity 叠加各 run 已发布净值与关键指标，不重算绩效。"
			onClose={onClose}
			contentClassName="sm:w-[min(72rem,calc(100vw-2rem))] sm:max-w-[min(72rem,calc(100vw-2rem))]"
		>
			{/* 不透明画布底（surface-0）：cockpit/表格/事实清单的弱色组合按页面侧
			    同底（surface-app）审计，overlay 面上会跌穿 AA；这里显式落回同底。 */}
			<div className="flex flex-col gap-3 rounded-(--radius-md) bg-(--color-surface-0) p-3">
				<OverlayFactList
					facts={[
						["已选择", `${runIds.length} 个 run`],
						["Run identities", runIds.join(" · ") || "尚未选择"],
						["对比口径", "先核对资产池/币种/时间样本/收益定义/费用；同口径才 nav₀ 归一叠加"],
					]}
				/>
				<p className="text-xs text-(--color-foreground-tertiary)">{comparisonLifetime}</p>
				{error && <p role="alert">{error}</p>}
				<ul aria-label="对比集合" className="space-y-2">
					{runIds.map((runId, index) => {
						const query = queries[index];
						return (
							<li key={runId} className="flex flex-wrap items-center gap-2 text-xs">
								<a href={`/research/backtests/${encodeURIComponent(runId)}`} className="break-all underline">
									{runId}
								</a>
								{query?.isError ? (
									<>
										<span role="alert">读取失败：{query.error.message}；保留在集合中。</span>
										<Button
											size="xs"
											variant="outline"
											onClick={() => void query.refetch()}
											aria-label={`重试 ${runId}`}
										>
											重试
										</Button>
									</>
								) : query?.isPending ? (
									<span>正在加载…</span>
								) : query?.isFetching ? (
									<span>正在刷新…</span>
								) : null}
								<Button
									size="xs"
									variant="outline"
									aria-label={`移出对比 ${runId}`}
									onClick={() => setIncluded(runId, false)}
								>
									移出
								</Button>
							</li>
						);
					})}
				</ul>
				{runIds.length < 2 ? (
					<p className="text-xs text-(--color-foreground-tertiary)">
						至少需要两个真实 run 才能形成对比；可在目录或详情页加入运行。
					</p>
				) : runs.length !== runIds.length ? (
					<p className="text-xs">等待所选运行全部读取成功后展示对比；失败项可重试或移出。</p>
				) : (
					<BacktestMultiRunCompare runs={runs} />
				)}
			</div>
		</PageActionOverlay>
	);
}

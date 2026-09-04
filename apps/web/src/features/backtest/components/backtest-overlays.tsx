import type { ReactNode } from "react";
import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";

export type BacktestOverlayId = "export" | "enable-signal" | "ai-analysis" | "compare-toast" | "compare";

export const backtestActions = [
	{ id: "export", label: "导出报告" },
	{ id: "enable-signal", label: "提交信号治理" },
	{ id: "ai-analysis", label: "AI 解读" },
	{ id: "compare-toast", label: "加入对比" },
	{ id: "compare", label: "对比视图" },
] as const;

const copy = {
	export: { title: "导出回测报告", description: "导出已发布 report 与精确 run identity。", kind: "sheet" },
	"enable-signal": {
		title: "启用信号确认",
		description: "回测不能直接启用交易信号，只能进入策略治理。",
		kind: "alert-dialog",
	},
	"ai-analysis": { title: "AI 解读", description: "Agent 只基于当前回测证据回答，不成为统计裁判。", kind: "drawer" },
	"compare-toast": { title: "已加入对比", description: "当前 run 已加入本次浏览会话的对比集合。", kind: "toast" },
	compare: { title: "回测对比", description: "当前仅有一个已验证 run；不会生成虚构基准运行。", kind: "modal" },
} as const;

export function BacktestOverlays({
	active,
	agentActions,
	onClose,
	onExport,
	period,
	runId,
	strategyIdentity,
}: {
	readonly active: BacktestOverlayId | null;
	readonly agentActions: ReactNode;
	readonly onClose: () => void;
	readonly onExport: () => void;
	readonly period: string;
	readonly runId: string;
	readonly strategyIdentity: string;
}) {
	if (!active) return null;
	const details = copy[active];
	const actions =
		active === "export" ? (
			<Button type="button" onClick={onExport}>
				下载 JSON
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

export function BacktestCompareOverlay({
	onClose,
	open,
	runIds,
}: {
	readonly onClose: () => void;
	readonly open: boolean;
	readonly runIds: readonly string[];
}) {
	return (
		<PageActionOverlay
			open={open}
			kind="drawer"
			title="回测对比"
			description="按服务端 run identity 比较目录状态，不重算绩效。"
			onClose={onClose}
		>
			<OverlayFactList
				facts={[
					["已选择", `${runIds.length} 个 run`],
					["Run identities", runIds.join(" · ") || "尚未选择"],
					["统计对比", "进入各自已发布 report"],
				]}
			/>
			{runIds.length < 2 && (
				<p className="text-xs text-(--color-foreground-tertiary)">至少需要两个真实 run 才能形成对比。</p>
			)}
		</PageActionOverlay>
	);
}

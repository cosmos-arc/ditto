import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";

export type InstrumentOverlayId =
	| "chart-toolbar"
	| "news-detail"
	| "announcement-detail"
	| "add-watchlist"
	| "send-research"
	| "halt-detail";

export const instrumentActions = [
	{ id: "chart-toolbar", label: "图表工具" },
	{ id: "news-detail", label: "新闻详情" },
	{ id: "announcement-detail", label: "公告详情" },
	{ id: "add-watchlist", label: "加入自选" },
	{ id: "send-research", label: "发送研究" },
	{ id: "halt-detail", label: "停牌状态" },
] as const;

const copy = {
	"chart-toolbar": {
		title: "图表工具",
		description: "图表操作受当前 exact date-range bars 合同约束。",
		kind: "inline",
	},
	"news-detail": { title: "新闻详情", description: "当前稳定接口未提供新闻证据。", kind: "drawer" },
	"announcement-detail": { title: "公告详情", description: "当前稳定接口未提供公告文档与发布时间。", kind: "drawer" },
	"add-watchlist": { title: "加入自选", description: "将标的 identity 保存到当前浏览器。", kind: "sheet" },
	"send-research": {
		title: "发送到研究",
		description: "携带 exact SelectionRun 与技术证据快照前往 Research Agent，不创建实验。",
		kind: "sheet",
	},
	"halt-detail": { title: "停牌详情", description: "只使用 metadata active 状态，不推断实时交易状态。", kind: "modal" },
} as const;

export function InstrumentPageOverlays({
	active,
	instrumentId,
	onAddWatchlist,
	onClose,
	selectionRunId,
	technicalSnapshotId,
}: {
	readonly active: InstrumentOverlayId | null;
	readonly instrumentId: string;
	readonly onAddWatchlist: () => void;
	readonly onClose: () => void;
	readonly selectionRunId?: string;
	readonly technicalSnapshotId?: string | null;
}) {
	if (!active) return null;
	const details = copy[active];
	const researchParams = new URLSearchParams({
		tab: "runs",
		contextType: "instrument",
		contextId: technicalSnapshotId ?? "",
		objective: "分析该技术证据并起草可回测策略假设",
	});
	const canOpenResearch = Boolean(selectionRunId && technicalSnapshotId);
	const actions =
		active === "add-watchlist" ? (
			<Button type="button" onClick={onAddWatchlist}>
				确认加入本机自选
			</Button>
		) : active === "send-research" && canOpenResearch ? (
			<a
				className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
				href={`/research/agent?${researchParams.toString()}`}
			>
				打开 Research Agent
			</a>
		) : undefined;

	return (
		<PageActionOverlay {...details} open onClose={onClose} actions={actions}>
			<OverlayFactList
				facts={[
					["Instrument ID", instrumentId || "未报告"],
					["SelectionRun identity", selectionRunId ?? "未报告"],
					["Bar granularity", "daily"],
					["Snapshot identity", technicalSnapshotId ?? "未报告"],
					["写入范围", active === "add-watchlist" ? "localStorage" : "无"],
				]}
			/>
			{active === "send-research" && !canOpenResearch && (
				<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs leading-5 text-(--color-risk-warning-fg)">
					缺少 exact SelectionRun 或技术证据快照，Research Agent 入口已阻断。请从 Selection Workspace
					进入并等待技术证据加载完成。
				</p>
			)}
			{active !== "add-watchlist" && active !== "send-research" && (
				<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs leading-5 text-(--color-risk-warning-fg)">
					缺少公共证据时保持阻断，不复用原型静态新闻、公告、停牌原因或技术指标。
				</p>
			)}
		</PageActionOverlay>
	);
}

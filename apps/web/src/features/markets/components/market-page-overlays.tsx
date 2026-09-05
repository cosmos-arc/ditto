import type { ReactNode } from "react";
import {
	OverlayFactList,
	PageActionOverlay,
	type PageActionOverlayKind,
} from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";

interface OverlayCopy {
	readonly description: string;
	readonly kind: PageActionOverlayKind;
	readonly title: string;
}

function BoundaryNotice({ children }: { readonly children: ReactNode }) {
	return (
		<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs leading-5 text-(--color-risk-warning-fg)">
			{children}
		</p>
	);
}

export type MarketsOverviewOverlayId =
	| "market-depth"
	| "index-components"
	| "filter-panel"
	| "event-detail"
	| "pin-viewpoint";

export const marketsOverviewActions = [
	{ id: "market-depth", label: "市场深度" },
	{ id: "index-components", label: "指数成分" },
	{ id: "filter-panel", label: "市场筛选" },
	{ id: "event-detail", label: "事件详情" },
	{ id: "pin-viewpoint", label: "固定视角" },
] as const;

const marketsOverviewCopy: Record<MarketsOverviewOverlayId, OverlayCopy> = {
	"market-depth": {
		title: "市场深度",
		description: "基于当前 Catalog 身份覆盖展示可验证范围。",
		kind: "drawer",
	},
	"index-components": {
		title: "指数成分股",
		description: "当前公开合同未提供指数权重，只展示可追溯的标的身份。",
		kind: "sheet",
	},
	"filter-panel": {
		title: "市场筛选",
		description: "筛选只作用于已加载的 metadata，不推断行情或资金流。",
		kind: "drawer",
	},
	"event-detail": {
		title: "事件详情",
		description: "宏观事件明细不在当前稳定 API 合同内。",
		kind: "drawer",
	},
	"pin-viewpoint": {
		title: "视角已固定",
		description: "当前 metadata 覆盖已固定在本次浏览会话中；刷新页面后恢复默认。",
		kind: "inline",
	},
};

export function MarketsOverviewOverlay({
	active,
	assetSummary,
	exchangeSummary,
	onClose,
	total,
}: {
	readonly active: MarketsOverviewOverlayId | null;
	readonly assetSummary: string;
	readonly exchangeSummary: string;
	readonly onClose: () => void;
	readonly total: number;
}) {
	if (!active) return null;
	const copy = marketsOverviewCopy[active];
	return (
		<PageActionOverlay {...copy} open onClose={onClose}>
			<OverlayFactList
				facts={[
					["标的身份", String(total)],
					["资产类别", assetSummary || "未报告"],
					["交易所", exchangeSummary || "未报告"],
					["价格快照", "未查询"],
				]}
			/>
			{active !== "pin-viewpoint" && (
				<BoundaryNotice>
					缺少 immutable 行情 snapshot 时，不展示价格、涨跌、资金流、指数权重或事件影响结论。
				</BoundaryNotice>
			)}
		</PageActionOverlay>
	);
}

export type IntelligenceOverlayId =
	| "intelligence-detail"
	| "custom-filter"
	| "bookmark-success"
	| "delete-confirm"
	| "send-to-copilot";

export const intelligenceActions = [
	{ id: "intelligence-detail", label: "情报详情" },
	{ id: "custom-filter", label: "筛选说明" },
	{ id: "bookmark-success", label: "收藏视角" },
	{ id: "delete-confirm", label: "清除收藏" },
	{ id: "send-to-copilot", label: "发送 Copilot" },
] as const;

const intelligenceCopy: Record<IntelligenceOverlayId, OverlayCopy> = {
	"intelligence-detail": { title: "情报详情", description: "当前宏观查询的时间边界与证据状态。", kind: "drawer" },
	"custom-filter": {
		title: "自定义筛选",
		description: "筛选由页面日期范围和 experimental opt-in 共同约束。",
		kind: "sheet",
	},
	"bookmark-success": {
		title: "视角已收藏",
		description: "只在当前浏览会话保存日期范围，不写入服务端。",
		kind: "toast",
	},
	"delete-confirm": { title: "清除收藏", description: "清除当前浏览会话中的宏观视角。", kind: "alert-dialog" },
	"send-to-copilot": {
		title: "发送到 Copilot",
		description: "创建 Agent 任务前必须具备不可变 evidence identity。",
		kind: "drawer",
	},
};

export function IntelligenceOverlay({
	active,
	allowExperimental,
	endDate,
	indicatorCount,
	onClearBookmark,
	onClose,
	startDate,
}: {
	readonly active: IntelligenceOverlayId | null;
	readonly allowExperimental: boolean;
	readonly endDate: string;
	readonly indicatorCount: number;
	readonly onClearBookmark: () => void;
	readonly onClose: () => void;
	readonly startDate: string;
}) {
	if (!active) return null;
	const copy = intelligenceCopy[active];
	return (
		<PageActionOverlay
			{...copy}
			open
			onClose={onClose}
			actions={
				active === "delete-confirm" ? (
					<>
						<Button type="button" variant="outline" onClick={onClose}>
							取消
						</Button>
						<Button type="button" variant="destructive" onClick={onClearBookmark}>
							确认清除
						</Button>
					</>
				) : undefined
			}
		>
			<OverlayFactList
				facts={[
					["开始日期", startDate],
					["截至日期", endDate],
					["Experimental", allowExperimental ? "显式启用" : "关闭"],
					["已加载指标", String(indicatorCount)],
					["Snapshot identity", "未报告"],
				]}
			/>
			{active === "send-to-copilot" && (
				<BoundaryNotice>
					当前接口未报告 snapshot identity，因此 Copilot 提交保持阻断；页面不会把日期范围冒充证据身份。
				</BoundaryNotice>
			)}
		</PageActionOverlay>
	);
}

export type CalendarOverlayId = "event-detail" | "reminder" | "intelligence";

export const calendarActions = [
	{ id: "event-detail", label: "覆盖详情" },
	{ id: "reminder", label: "设置检查提醒" },
	{ id: "intelligence", label: "前往 Intelligence" },
] as const;

const calendarCopy: Record<CalendarOverlayId, OverlayCopy> = {
	"event-detail": { title: "日历覆盖详情", description: "当前接口只提供交易日历覆盖与质量缺口。", kind: "drawer" },
	reminder: { title: "日历检查提醒", description: "提醒只保存在当前浏览会话，不会创建系统通知。", kind: "sheet" },
	intelligence: {
		title: "前往 Intelligence",
		description: "宏观指标查询在 Intelligence 中以显式日期范围运行。",
		kind: "modal",
	},
};

export function CalendarOverlay({
	active,
	onClose,
}: {
	readonly active: CalendarOverlayId | null;
	readonly onClose: () => void;
}) {
	if (!active) return null;
	const copy = calendarCopy[active];
	return (
		<PageActionOverlay
			{...copy}
			open
			onClose={onClose}
			actions={
				active === "intelligence" ? (
					<a
						className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
						href="/markets"
					>
						打开 Intelligence
					</a>
				) : undefined
			}
		>
			<OverlayFactList
				facts={[
					["数据集", "calendar"],
					["消费者配置", "research_daily"],
					["事件明细", "未公开"],
				]}
			/>
			<BoundaryNotice>不会用原型中的宏观事件名称、发布时间或预期值替代真实 API 数据。</BoundaryNotice>
		</PageActionOverlay>
	);
}

export type ASharesOverlayId = "northbound-detail" | "sector-detail" | "filter-panel" | "ai-analysis";

export const aSharesActions = [
	{ id: "northbound-detail", label: "北向资金" },
	{ id: "sector-detail", label: "行业详情" },
	{ id: "filter-panel", label: "筛选说明" },
	{ id: "ai-analysis", label: "AI 解读" },
] as const;

const aSharesCopy: Record<ASharesOverlayId, OverlayCopy> = {
	"northbound-detail": { title: "北向资金详情", description: "当前稳定合同未提供北向资金快照。", kind: "drawer" },
	"sector-detail": { title: "行业详情", description: "当前 metadata 合同未提供行业分类或行业行情。", kind: "sheet" },
	"filter-panel": { title: "A 股筛选边界", description: "当前范围固定为活跃 stock metadata。", kind: "drawer" },
	"ai-analysis": { title: "AI 解读", description: "没有不可变行情 snapshot 时不生成市场结论。", kind: "drawer" },
};

export function ASharesOverlay({
	active,
	onClose,
}: {
	readonly active: ASharesOverlayId | null;
	readonly onClose: () => void;
}) {
	if (!active) return null;
	const copy = aSharesCopy[active];
	return (
		<PageActionOverlay {...copy} open onClose={onClose}>
			<OverlayFactList
				facts={[
					["资产类别", "stock"],
					["活跃状态", "true"],
					["行情 snapshot", "未查询"],
					["知识截止", "未报告"],
				]}
			/>
			<BoundaryNotice>该动作保持可解释阻断；可先进入 Data Products 建立认证快照，再返回此页分析。</BoundaryNotice>
		</PageActionOverlay>
	);
}

export type WatchlistOverlayId = "add-instrument" | "bulk-delete";

export function WatchlistOverlay({
	active,
	addForm,
	count,
	onClear,
	onClose,
}: {
	readonly active: WatchlistOverlayId | null;
	readonly addForm: ReactNode;
	readonly count: number;
	readonly onClear: () => void;
	readonly onClose: () => void;
}) {
	if (!active) return null;
	const isAdd = active === "add-instrument";
	return (
		<PageActionOverlay
			open
			kind={isAdd ? "drawer" : "alert-dialog"}
			title={isAdd ? "添加标的" : "批量删除自选"}
			description={isAdd ? "从真实 metadata 目录加入本地 Watchlist。" : `将从本机清单移除 ${count} 个标的。`}
			onClose={onClose}
			actions={
				!isAdd ? (
					<>
						<Button type="button" variant="outline" onClick={onClose}>
							取消
						</Button>
						<Button type="button" variant="destructive" disabled={count === 0} onClick={onClear}>
							确认清空
						</Button>
					</>
				) : undefined
			}
		>
			{isAdd ? (
				addForm
			) : (
				<BoundaryNotice>此操作只影响浏览器 localStorage，不会删除服务端标的或行情数据。</BoundaryNotice>
			)}
		</PageActionOverlay>
	);
}

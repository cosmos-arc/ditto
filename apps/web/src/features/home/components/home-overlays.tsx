import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { PendingAction } from "@/types";
import { useDecisionBanner } from "../hooks";

interface ControlledOverlayProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}

interface HomeSignalEvidenceDrawerProps extends ControlledOverlayProps {
	readonly action: PendingAction | null;
	readonly onPrepareOrder: () => void;
}

export function HomeSignalEvidenceDrawer({
	open,
	onOpenChange,
	action,
	onPrepareOrder,
}: HomeSignalEvidenceDrawerProps) {
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>信号证据</SheetTitle>
					<SheetDescription>来自今日优先事项的只读证据；形成订单前仍需在交易域人工复核。</SheetDescription>
				</SheetHeader>

				{action ? (
					<div className="mt-6 flex flex-1 flex-col gap-5 text-sm">
						<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4">
							<p className="font-medium text-(--color-foreground)">{action.title}</p>
							<p className="mt-2 leading-6 text-(--color-foreground-secondary)">{action.meta}</p>
							<div className="mt-3 flex flex-wrap gap-2">
								{action.badges.map((badge) => (
									<span
										key={`${action.id}-${badge.type}-${badge.label}`}
										className="rounded-(--radius-sm) bg-(--color-interaction-hover-subtle-bg) px-2 py-1 text-xs text-(--color-foreground-secondary)"
									>
										{badge.label}
									</span>
								))}
							</div>
						</section>

						<dl className="grid grid-cols-[96px_1fr] gap-x-3 gap-y-2 text-xs">
							<dt className="text-(--color-foreground-tertiary)">来源域</dt>
							<dd className="text-(--color-foreground-secondary)">{action.domain}</dd>
							<dt className="text-(--color-foreground-tertiary)">生成时间</dt>
							<dd className="font-data text-(--color-foreground-secondary)">{action.time}</dd>
							<dt className="text-(--color-foreground-tertiary)">当前状态</dt>
							<dd className="text-(--color-system-degraded-fg)">等待人工复核</dd>
						</dl>
					</div>
				) : (
					<p className="mt-6 text-sm text-(--color-foreground-tertiary)">未选择待复核信号。</p>
				)}

				<SheetFooter className="mt-6 border-t border-(--color-border-subtle) pt-4">
					<Button type="button" onClick={onPrepareOrder} disabled={!action}>
						形成订单前检查
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

interface HomeOrderHandoffDialogProps extends ControlledOverlayProps {
	readonly action: PendingAction | null;
}

export function HomeOrderHandoffDialog({ open, onOpenChange, action }: HomeOrderHandoffDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent aria-describedby="home-order-handoff-description">
				<DialogHeader>
					<DialogTitle>订单交接确认</DialogTitle>
					<DialogDescription id="home-order-handoff-description">
						Home 只负责聚合待办，不会在 Home 自动创建 Paper 订单或成交。
					</DialogDescription>
				</DialogHeader>
				<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4 text-sm">
					<p className="font-medium text-(--color-foreground)">{action?.title ?? "未选择信号"}</p>
					<p className="mt-2 text-(--color-foreground-secondary)">
						进入交易域后请复核信号、风控门禁、T+1 可卖数量与订单参数，再明确提交。
					</p>
				</div>
				<DialogFooter>
					<Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
						留在 Home
					</Button>
					<Button asChild>
						<a href="/portfolio/review">进入信号收件箱复核</a>
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

interface HomeWorkspaceSettingsSheetProps extends ControlledOverlayProps {
	readonly sidebarCollapsed: boolean;
	readonly onToggleSidebar: () => void;
}

export function HomeWorkspaceSettingsSheet({
	open,
	onOpenChange,
	sidebarCollapsed,
	onToggleSidebar,
}: HomeWorkspaceSettingsSheetProps) {
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full p-6 sm:max-w-md">
				<SheetHeader>
					<SheetTitle>工作台设置</SheetTitle>
					<SheetDescription>调整已接入的本地界面偏好；设置会在当前浏览器中保存。</SheetDescription>
				</SheetHeader>
				<div className="mt-6 flex items-center justify-between rounded-(--radius-md) border border-(--color-border-subtle) p-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">右侧信息栏</p>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">市场、告警和数据健康概览</p>
					</div>
					<Button type="button" variant="outline" size="sm" onClick={onToggleSidebar}>
						{sidebarCollapsed ? "展开右侧栏" : "折叠右侧栏"}
					</Button>
				</div>
			</SheetContent>
		</Sheet>
	);
}

export function HomeDecisionEvidenceDrawer({ open, onOpenChange }: ControlledOverlayProps) {
	const { data, isLoading } = useDecisionBanner();

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>AI 决策证据</SheetTitle>
					<SheetDescription>只读证据摘要 · 本次查看未调用模型</SheetDescription>
				</SheetHeader>

				{isLoading ? (
					<p className="mt-6 text-sm text-(--color-foreground-tertiary)">正在读取 Daily Decision 证据…</p>
				) : data ? (
					<div className="mt-6 flex flex-col gap-4">
						<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4">
							<p className="text-xs text-(--color-foreground-tertiary)">系统建议</p>
							<p className="mt-2 text-sm leading-6 text-(--color-foreground)">{data.suggestion}</p>
						</section>
						<dl className="grid grid-cols-[112px_1fr] gap-x-3 gap-y-3 text-sm">
							<dt className="text-(--color-foreground-tertiary)">市场环境</dt>
							<dd className="text-(--color-foreground-secondary)">{data.regimeType}</dd>
							<dt className="text-(--color-foreground-tertiary)">杠杆率</dt>
							<dd className="font-data text-(--color-foreground-secondary)">
								{data.leverage == null ? "不可用" : `${data.leverage}x`}
							</dd>
							<dt className="text-(--color-foreground-tertiary)">风险利用率</dt>
							<dd className="font-data text-(--color-foreground-secondary)">
								{data.riskUtilization == null ? "不可用" : `${data.riskUtilization}%`}
							</dd>
							<dt className="text-(--color-foreground-tertiary)">权益</dt>
							<dd className="font-data text-(--color-foreground-secondary)">
								{data.totalEquity == null ? "不可用" : `¥${data.totalEquity.toLocaleString("zh-CN")}`}
							</dd>
						</dl>
					</div>
				) : (
					<p className="mt-6 text-sm text-(--color-foreground-tertiary)">Daily Decision 证据不可用。</p>
				)}
			</SheetContent>
		</Sheet>
	);
}

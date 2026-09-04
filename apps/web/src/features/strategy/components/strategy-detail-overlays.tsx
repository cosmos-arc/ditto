import { Link } from "@tanstack/react-router";
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
import type { StrategyDetail } from "@/types/strategy";
import { useStrategyGovernance } from "../hooks/use-strategy-governance";
import { DecisionDialog } from "./governance-dialogs";
import { StrategyListOverlays } from "./strategy-list-overlays";

export type StrategyDetailOverlay = "backtest" | "copy" | "deprecate" | "rollback";

interface StrategyDetailOverlaysProps {
	readonly detail: StrategyDetail | undefined;
	readonly detailLoading: boolean;
	readonly onClose: () => void;
	readonly onOpenVersions: () => void;
	readonly open: StrategyDetailOverlay | null;
	readonly strategyId: string;
}

export function StrategyDetailOverlays({
	detail,
	detailLoading,
	onClose,
	onOpenVersions,
	open,
	strategyId,
}: StrategyDetailOverlaysProps) {
	const governance = useStrategyGovernance(strategyId);

	return (
		<>
			<Sheet open={open === "backtest"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label="提交回测" className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>提交回测</SheetTitle>
						<SheetDescription>回测由实验 planning 固定完整身份并先执行只读 Preflight。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 p-5">
						<div className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3 text-xs">
							<span className="text-(--color-foreground-tertiary)">Strategy ID</span>
							<code className="font-data text-(--color-foreground)">{strategyId}</code>
							<span className="text-(--color-foreground-tertiary)">版本</span>
							<code className="font-data text-(--color-foreground)">v{detail?.version ?? "—"}</code>
							<span className="text-(--color-foreground-tertiary)">Spec</span>
							<span className="text-(--color-foreground-secondary)">服务端策略定义</span>
						</div>
						<div className="rounded-(--radius-md) border border-(--color-led-warning) bg-(--color-led-warning-bg) p-3 text-xs leading-5 text-(--color-foreground-secondary)">
							本页不会直接创建回测。实验创建器将要求 snapshot、时间范围、registry hash 与资源预算，Preflight
							通过后才能启动。
						</div>
						<SheetFooter className="mt-auto">
							<Button asChild className="w-full">
								<Link to="/research/experiments/new">打开实验创建器</Link>
							</Button>
						</SheetFooter>
					</div>
				</SheetContent>
			</Sheet>

			<StrategyListOverlays
				open={open === "copy" ? "clone" : null}
				onClose={onClose}
				selected={detail ?? null}
				detail={detail}
				detailLoading={detailLoading}
			/>

			<DecisionDialog
				open={open === "deprecate"}
				onOpenChange={(isOpen) => !isOpen && onClose()}
				title="弃用版本"
				description={`将 ${strategyId}@${detail?.version ?? "—"} 标记为 deprecated；保留全部版本与审计记录。`}
				confirmLabel="确认弃用"
				isPending={governance.deprecate.isPending}
				onConfirm={(actor, reason) => {
					if (!detail) return;
					governance.deprecate.mutate({ version: detail.version, actor, reason }, { onSuccess: onClose });
				}}
			/>

			<Dialog open={open === "rollback"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<DialogContent aria-label="版本回滚">
					<DialogHeader>
						<DialogTitle>版本回滚</DialogTitle>
						<DialogDescription>策略版本不可覆盖；回滚必须通过受控版本治理更新 active pointer。</DialogDescription>
					</DialogHeader>
					<div className="space-y-2 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3 text-xs leading-5 text-(--color-foreground-secondary)">
						<p>1. 选择一个服务端历史版本并查看 immutable canonical spec。</p>
						<p>2. 只有符合生命周期约束的版本才提供重新激活。</p>
						<p>3. 提交时必须携带最新 pointer revision、影响摘要和精确确认句。</p>
					</div>
					<DialogFooter>
						<Button
							onClick={() => {
								onOpenVersions();
								onClose();
							}}
						>
							查看版本治理
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
	);
}

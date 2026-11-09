import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { StrategyDetail } from "@/types/strategy";
import { useStrategyGovernance } from "../hooks/use-strategy-governance";
import { DecisionDialog } from "./governance-dialogs";
import { StrategyListOverlays } from "./strategy-list-overlays";

export type StrategyDetailOverlay = "backtest" | "copy" | "deprecate" | "rollback";

interface StrategyDetailOverlaysProps {
	readonly backtestForm?: ReactNode;
	readonly onBacktestCloseAutoFocus?: () => void;
	readonly detail: StrategyDetail | undefined;
	readonly detailLoading: boolean;
	readonly onClose: () => void;
	readonly onOpenVersions: () => void;
	readonly open: StrategyDetailOverlay | null;
	readonly strategyId: string;
}

export function StrategyDetailOverlays({
	backtestForm,
	onBacktestCloseAutoFocus,
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
				<SheetContent
					side="right"
					aria-label="提交回测"
					className="p-0"
					onCloseAutoFocus={(event) => {
						if (!onBacktestCloseAutoFocus) return;
						event.preventDefault();
						onBacktestCloseAutoFocus();
					}}
				>
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>提交回测</SheetTitle>
						<SheetDescription>选择策略版本、日期和资金，提交普通研究回测。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
						{backtestForm ?? <p>回测表单暂不可用，请从回测列表创建。</p>}
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

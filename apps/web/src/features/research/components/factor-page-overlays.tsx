import { Link } from "@tanstack/react-router";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { AgentContextActions } from "@/features/agent";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { FactorDiagnosticsView } from "./factor-diagnostics-view";

export type FactorPageOverlay = "add-backtest" | "add-experiment" | "ai-analysis" | "diagnostic-detail";

interface FactorPageOverlaysProps {
	readonly factorId: string;
	readonly open: FactorPageOverlay | null;
	readonly onClose: () => void;
	readonly scope: FactorDiagnosticsScope | null;
}

function factorContextId(factorId: string, scope: FactorDiagnosticsScope): string {
	return `${factorId}:${scope.snapshotId}:${scope.startDate}:${scope.endDate}:${scope.registryHash}`;
}

export function FactorPageOverlays({ factorId, open, onClose, scope }: FactorPageOverlaysProps) {
	const handoff = open === "add-backtest" || open === "add-experiment" ? open : null;
	const isBacktest = handoff === "add-backtest";

	return (
		<>
			<Sheet open={handoff !== null} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label={isBacktest ? "加入回测" : "加入实验"} className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>{isBacktest ? "加入回测" : "加入实验"}</SheetTitle>
						<SheetDescription>携带因子标识前往目标工作区，由目标流程绑定数据范围并确认创建。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 p-5 text-sm text-(--color-foreground-secondary)">
						<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-4">
							<p className="text-xs text-(--color-foreground-tertiary)">候选因子</p>
							<p className="mt-1 font-data text-(--color-foreground)">{factorId}</p>
						</div>
						<p>{isBacktest ? "尚未创建回测，也未绑定组合或时间窗口。" : "尚未创建实验，也未写入研究状态。"}</p>
						<Button asChild className="mt-auto w-full">
							<Link to={isBacktest ? "/research/backtests" : "/research/experiments/new"}>
								{isBacktest ? "前往回测列表" : "进入实验配置"}
							</Link>
						</Button>
					</div>
				</SheetContent>
			</Sheet>

			<Drawer open={open === "ai-analysis"} onClose={onClose} title="AI 解读">
				<div className="flex flex-col gap-4 pb-5">
					<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-4">
						<p className="font-medium text-(--color-foreground)">证据优先</p>
						<p className="mt-2 text-xs">
							这里不会生成未经服务端证据支持的结论。请求会携带当前不可变诊断身份，交由治理型 Agent 复核。
						</p>
					</div>
					{scope ? (
						<AgentContextActions
							contextType="factor-diagnostics"
							contextId={factorContextId(factorId, scope)}
							evidenceObjective="复核当前不可变因子诊断的证据、时间边界与异常"
						/>
					) : (
						<p className="text-xs text-(--color-foreground-tertiary)">
							先绑定 snapshot、时间窗口与 registry hash，才能请求证据分析。
						</p>
					)}
				</div>
			</Drawer>

			<Dialog open={open === "diagnostic-detail" && scope !== null} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<DialogContent
					aria-label="诊断详情"
					className="max-h-[min(88vh,860px)] max-w-[min(92vw,960px)] grid-rows-[auto_1fr] overflow-hidden p-0"
				>
					<DialogHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<DialogTitle>诊断详情</DialogTitle>
						<DialogDescription>与主视图共享同一不可变诊断制品，不发起降级查询。</DialogDescription>
					</DialogHeader>
					<div className="min-h-0 overflow-y-auto">
						{scope && <FactorDiagnosticsView factorId={factorId} scope={scope} />}
					</div>
				</DialogContent>
			</Dialog>
		</>
	);
}

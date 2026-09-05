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
import type { SpecValidation, StrategyAuthorPreview, StrategyDetail, StrategySpec } from "@/types/strategy";
import { useStrategyGovernance } from "../hooks/use-strategy-governance";
import { DecisionDialog } from "./governance-dialogs";
import { StrategyAuthorPreviewSheet } from "./strategy-author-preview-sheet";

export type StrategyStudioOverlay = "save" | "dry-run" | "backtest" | "factor-preview" | "author-preview" | "deprecate";

interface StrategyStudioOverlaysProps {
	readonly detail: StrategyDetail | undefined;
	readonly isSaving: boolean;
	readonly onClose: () => void;
	readonly onConfirmSave: () => void;
	readonly onOperation: (message: string) => void;
	readonly open: StrategyStudioOverlay | null;
	readonly strategyId: string;
	readonly validation: SpecValidation | null;
	readonly validationIsStale: boolean;
	readonly workingSpec: StrategySpec | null;
	readonly authorPreview: StrategyAuthorPreview | null;
	readonly authorPreviewError: string | null;
	readonly authorPreviewIsPending: boolean;
	readonly authorPreviewIsStale: boolean;
}

function IdentityGrid({
	strategyId,
	detail,
}: {
	readonly strategyId: string;
	readonly detail?: StrategyDetail | undefined;
}) {
	return (
		<dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3 text-xs">
			<dt className="text-(--color-foreground-tertiary)">策略版本</dt>
			<dd className="font-data text-(--color-foreground)">
				{strategyId}@{detail?.version ?? "—"}
			</dd>
			<dt className="text-(--color-foreground-tertiary)">Universe</dt>
			<dd className="font-data text-(--color-foreground-secondary)">{detail?.spec.universe ?? "—"}</dd>
			<dt className="text-(--color-foreground-tertiary)">当前状态</dt>
			<dd className="text-(--color-foreground-secondary)">{detail?.lifecycleState ?? "—"}</dd>
		</dl>
	);
}

export function StrategyStudioOverlays({
	detail,
	isSaving,
	onClose,
	onConfirmSave,
	onOperation,
	open,
	strategyId,
	validation,
	validationIsStale,
	workingSpec,
	authorPreview,
	authorPreviewError,
	authorPreviewIsPending,
	authorPreviewIsStale,
}: StrategyStudioOverlaysProps) {
	const governance = useStrategyGovernance(strategyId);
	const canonicalHash = validation && !validationIsStale ? validation.canonicalHash : null;

	return (
		<>
			<StrategyAuthorPreviewSheet
				open={open === "author-preview"}
				onClose={onClose}
				preview={authorPreview}
				isPending={authorPreviewIsPending}
				isStale={authorPreviewIsStale}
				error={authorPreviewError}
			/>
			<Dialog open={open === "save"} onOpenChange={(isOpen) => !isOpen && !isSaving && onClose()}>
				<DialogContent aria-label="保存新版本">
					<DialogHeader>
						<DialogTitle>保存新版本</DialogTitle>
						<DialogDescription>
							当前 working copy 将以 base v{detail?.version ?? "—"} 创建 append-only draft，不覆盖历史版本。
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-3 text-xs">
						<IdentityGrid strategyId={strategyId} detail={detail} />
						<div className="flex items-center justify-between rounded-(--radius-md) border border-(--color-border-subtle) px-3 py-2">
							<span className="text-(--color-foreground-tertiary)">candidate canonical hash</span>
							<code className="font-data text-(--color-foreground)">{canonicalHash ?? "校验已过期"}</code>
						</div>
					</div>
					<DialogFooter>
						<Button variant="outline" onClick={onClose} disabled={isSaving}>
							继续编辑
						</Button>
						<Button onClick={onConfirmSave} disabled={!canonicalHash || isSaving}>
							{isSaving ? "保存中…" : "确认保存新版本"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			<Sheet open={open === "dry-run"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label="Dry Run 规划" className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>Dry Run 规划</SheetTitle>
						<SheetDescription>当前后端没有独立 Strategy Dry Run 命令；本页只核对可交接身份。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 p-5">
						<IdentityGrid strategyId={strategyId} detail={detail} />
						<div className="rounded-(--radius-md) border border-(--color-led-warning) bg-(--color-led-warning-bg) p-3 text-xs leading-5 text-(--color-foreground-secondary)">
							<strong className="block text-(--color-foreground)">未运行</strong>
							需要实验固定 snapshot、时间范围、registry hash、资源预算与成本模型，并通过只读 Preflight。
						</div>
						<p className="font-data text-xs text-(--color-foreground-tertiary)">
							candidate {canonicalHash ?? "尚未通过当前 working copy 校验"}
						</p>
						<SheetFooter className="mt-auto">
							<Button variant="outline" onClick={onClose}>
								关闭
							</Button>
						</SheetFooter>
					</div>
				</SheetContent>
			</Sheet>

			<Sheet open={open === "backtest"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label="提交回测规划" className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>提交回测规划</SheetTitle>
						<SheetDescription>携带精确策略版本进入实验规划；此处不会直接创建实验或回测。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 p-5">
						<IdentityGrid strategyId={strategyId} detail={detail} />
						<div className="rounded-(--radius-md) border border-(--color-led-warning) bg-(--color-led-warning-bg) p-3 text-xs leading-5 text-(--color-foreground-secondary)">
							实验创建器仍会要求 snapshot、时间范围、registry hash、资源预算与完整成本假设，并执行只读 Preflight。
						</div>
						<p className="font-data text-xs text-(--color-foreground-tertiary)">
							candidate {canonicalHash ?? "尚未通过当前 working copy 校验"}
						</p>
						<SheetFooter className="mt-auto">
							<Button variant="outline" onClick={onClose}>
								关闭
							</Button>
							<Button asChild>
								<Link to="/research/experiments/new">打开实验创建器</Link>
							</Button>
						</SheetFooter>
					</div>
				</SheetContent>
			</Sheet>

			<Sheet open={open === "factor-preview"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label="因子预览" className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>因子预览</SheetTitle>
						<SheetDescription>当前 working copy 的表达式与权重；不混入原型绩效或分布样例。</SheetDescription>
					</SheetHeader>
					<div className="flex flex-1 flex-col gap-4 p-5">
						<div className="overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle)">
							<table className="w-full text-left text-xs" aria-label="working copy 因子">
								<thead className="bg-(--color-surface-2) text-(--color-foreground-tertiary)">
									<tr>
										<th className="px-3 py-2 font-medium">表达式</th>
										<th className="px-3 py-2 text-right font-medium">权重</th>
									</tr>
								</thead>
								<tbody>
									{workingSpec?.signalExpressions.map((expression, index) => (
										<tr key={expression} className="border-t border-(--color-border-subtle)">
											<td className="px-3 py-2 font-data text-(--color-foreground)">{expression}</td>
											<td className="px-3 py-2 text-right font-data text-(--color-foreground-secondary)">
												{workingSpec.signalWeights[index] ?? 0}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
						<div className="rounded-(--radius-md) border border-dashed border-(--color-border) p-3 text-xs leading-5 text-(--color-foreground-secondary)">
							<strong className="block text-(--color-foreground)">分布未评估</strong>
							需要绑定 diagnostics snapshot、时间窗口与 registry hash 后才能预览处理后分布。
						</div>
						<SheetFooter className="mt-auto">
							<Button variant="outline" onClick={onClose}>
								关闭
							</Button>
						</SheetFooter>
					</div>
				</SheetContent>
			</Sheet>

			<DecisionDialog
				open={open === "deprecate"}
				onOpenChange={(isOpen) => !isOpen && onClose()}
				title="弃用版本"
				description={`将 ${strategyId}@${detail?.version ?? "—"} 标记为 deprecated；保留全部版本、实验与审计记录。`}
				confirmLabel="确认弃用"
				isPending={governance.deprecate.isPending}
				onConfirm={(actor, reason) => {
					if (!detail) return;
					governance.deprecate.mutate(
						{ version: detail.version, actor, reason },
						{
							onSuccess: () => {
								onOperation(`已弃用 ${strategyId}@${detail.version}`);
								onClose();
							},
						},
					);
				}}
			/>
		</>
	);
}

import { useState, type FormEvent } from "react";
import { useSignalDetail } from "../hooks/use-signal-detail";
import { useRecordFill } from "../hooks/use-record-fill";
import { useUpdateIntentStatus } from "../hooks/use-update-intent-status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { ApiError } from "@/lib/api-client";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { RecordFillRequest } from "../api/fills";
import type { IntentStatus } from "../api/intents";
import type { SignalExecutionIntent } from "@/types";

type RiskCheckStatus = "pass" | "warn" | "fail";

const STATUS_STYLE: Record<RiskCheckStatus, string> = {
	pass: "text-(--color-led-success)",
	warn: "text-(--color-led-warning)",
	fail: "text-(--color-led-error)",
};

const STATUS_ICON: Record<RiskCheckStatus, string> = {
	pass: "✓",
	warn: "⚠",
	fail: "✗",
};

interface SignalDetailPanelProps {
	readonly signalId: string;
}

interface FillFormState {
	readonly quantity: string;
	readonly fillPrice: string;
	readonly fee: string;
	readonly slippage: string;
	readonly notes: string;
}

const EMPTY_FILL_FORM: FillFormState = {
	quantity: "",
	fillPrice: "",
	fee: "0",
	slippage: "0",
	notes: "",
};

const INTENT_STATUS_OPTIONS = [
	{ value: "pending", label: "待复核" },
	{ value: "filled", label: "成交" },
	{ value: "partially_filled", label: "部分成交" },
	{ value: "cancelled", label: "取消" },
	{ value: "expired", label: "过期" },
] as const satisfies ReadonlyArray<{
	readonly value: IntentStatus;
	readonly label: string;
}>;

function createFillFormState(execution: SignalExecutionIntent): FillFormState {
	return {
		quantity: execution.quantity > 0 ? String(execution.quantity) : "",
		fillPrice: "",
		fee: "0",
		slippage: "0",
		notes: "manual paper fill",
	};
}

function parseFiniteNumber(value: string): number | null {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

function buildRecordFillRequest(
	execution: SignalExecutionIntent | undefined,
	form: FillFormState,
): { readonly payload: RecordFillRequest } | { readonly error: string } {
	if (!execution?.intentId) {
		return { error: "缺少 intent_id，无法录入成交" };
	}

	const quantity = parseFiniteNumber(form.quantity);
	if (quantity == null || quantity <= 0) {
		return { error: "成交数量必须大于 0" };
	}

	const fillPrice = parseFiniteNumber(form.fillPrice);
	if (fillPrice == null || fillPrice <= 0) {
		return { error: "成交价格必须大于 0" };
	}

	const fee = parseFiniteNumber(form.fee);
	if (fee == null || fee < 0) {
		return { error: "手续费必须大于等于 0" };
	}

	const slippage = parseFiniteNumber(form.slippage);
	if (slippage == null) {
		return { error: "滑点必须是有限数字" };
	}

	return {
		payload: {
			fill_id: `fill-${execution.intentId}-${execution.tradeDate}`,
			intent_id: execution.intentId,
			strategy_id: execution.strategyId,
			trade_date: execution.tradeDate,
			instrument_id: execution.instrumentId,
			direction: execution.direction,
			quantity,
			fill_price: fillPrice,
			fee,
			slippage,
			notes: form.notes,
		},
	};
}

function describeMutationError(error: unknown): string | null {
	if (!error) return null;
	if (error instanceof ApiError) {
		return error.errorCode ? `${error.message}（${error.errorCode}）` : error.message;
	}
	return "手工成交录入失败，请稍后重试";
}

function toIntentStatus(value: string): IntentStatus {
	return INTENT_STATUS_OPTIONS.find((option) => option.value === value)?.value ?? "filled";
}

function intentStatusLabel(status: IntentStatus): string {
	return INTENT_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status;
}

export function SignalDetailPanel({ signalId }: SignalDetailPanelProps) {
	const { data, isLoading, isError, refetch } = useSignalDetail(signalId);
	const recordFillMutation = useRecordFill();
	const updateIntentStatusMutation = useUpdateIntentStatus();
	const [fillSheetOpen, setFillSheetOpen] = useState(false);
	const [fillForm, setFillForm] = useState<FillFormState>(EMPTY_FILL_FORM);
	const [fillValidationError, setFillValidationError] = useState<string | null>(null);
	const [fillSuccessMessage, setFillSuccessMessage] = useState<string | null>(null);
	const [statusDialogOpen, setStatusDialogOpen] = useState(false);
	const [targetStatus, setTargetStatus] = useState<IntentStatus>("filled");
	const [statusValidationError, setStatusValidationError] = useState<string | null>(null);
	const [statusSuccessMessage, setStatusSuccessMessage] = useState<string | null>(null);

	if (isLoading) {
		return (
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<div className="p-3">
						<LoadingSkeleton variant="panel" rows={6} />
					</div>
				</PanelBody>
			</Panel>
		);
	}

	if (isError) {
		return (
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<DittoErrorBoundary
						fallbackProps={{
							title: "信号详情加载失败",
							onRetry: () => void refetch(),
						}}
					>
						<div />
					</DittoErrorBoundary>
				</PanelBody>
			</Panel>
		);
	}

	function openRecordFillSheet() {
		if (!data?.execution) {
			setFillValidationError("缺少 intent_id，无法录入成交");
			return;
		}

		recordFillMutation.reset();
		setFillSuccessMessage(null);
		setFillValidationError(null);
		setFillForm(createFillFormState(data.execution));
		setFillSheetOpen(true);
	}

	function openStatusDialog() {
		if (!data?.execution?.intentId) {
			setStatusValidationError("缺少 intent_id，无法更新状态");
			return;
		}

		updateIntentStatusMutation.reset();
		setStatusSuccessMessage(null);
		setStatusValidationError(null);
		setTargetStatus("filled");
		setStatusDialogOpen(true);
	}

	function submitRecordFill(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setFillValidationError(null);

		const result = buildRecordFillRequest(data?.execution, fillForm);
		if ("error" in result) {
			setFillValidationError(result.error);
			return;
		}

		recordFillMutation.mutate(result.payload, {
			onSuccess: () => {
				setFillSheetOpen(false);
				setFillSuccessMessage("手工成交已录入");
			},
		});
	}

	function submitIntentStatus() {
		if (!data?.execution?.intentId) {
			setStatusValidationError("缺少 intent_id，无法更新状态");
			return;
		}

		setStatusValidationError(null);
		updateIntentStatusMutation.mutate(
			{ intentId: data.execution.intentId, status: targetStatus },
			{
				onSuccess: () => {
					setStatusDialogOpen(false);
					setStatusSuccessMessage(`状态已更新为${intentStatusLabel(targetStatus)}`);
				},
			},
		);
	}

	function updateFillForm(field: keyof FillFormState, value: string) {
		setFillForm((current) => ({ ...current, [field]: value }));
	}

	function handleAction(actionType: string) {
		if (actionType === "record_fill") {
			openRecordFillSheet();
			return;
		}
		if (actionType === "update_status") {
			openStatusDialog();
		}
	}

	const fillErrorMessage = fillValidationError ?? describeMutationError(recordFillMutation.error);
	const statusErrorMessage =
		statusValidationError ?? describeMutationError(updateIntentStatusMutation.error);
	const isActionPending = recordFillMutation.isPending || updateIntentStatusMutation.isPending;

	return (
		<>
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<div className="flex flex-col gap-(--density-gutter) p-3">
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
								AI 解读
							</h4>
							<p className="text-(length:--text-sm) leading-relaxed text-(--color-foreground)">
								{data?.explanation}
							</p>
						</section>

						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
								风控检查
							</h4>
							<ul className="flex flex-col gap-1">
								{data?.riskChecks.map((check) => (
									<li
										key={check.name}
										className="flex items-start gap-2 text-(length:--text-sm)"
									>
										<span className={STATUS_STYLE[check.status as RiskCheckStatus]}>
											{STATUS_ICON[check.status as RiskCheckStatus]}
										</span>
										<div>
											<span className="font-medium text-(--color-foreground)">
												{check.name}
											</span>
											<span className="ml-1 text-(--color-foreground-tertiary)">
												{check.message}
											</span>
										</div>
									</li>
								))}
							</ul>
						</section>

						{data?.portfolioImpact && (
							<section>
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
									组合影响
								</h4>
								<div className="grid grid-cols-3 gap-2 text-(length:--text-sm)">
									<div>
										<span className="text-(--color-foreground-tertiary)">集中度变化</span>
										<div className="font-data text-(--color-foreground)">
											{(data.portfolioImpact.concentrationChange * 100).toFixed(1)}%
										</div>
									</div>
									<div>
										<span className="text-(--color-foreground-tertiary)">行业暴露</span>
										<div className="font-data text-(--color-foreground)">
											{(data.portfolioImpact.sectorExposure * 100).toFixed(1)}%
										</div>
									</div>
									<div>
										<span className="text-(--color-foreground-tertiary)">风险变化</span>
										<div className="font-data text-(--color-foreground)">
											{(data.portfolioImpact.riskChange * 100).toFixed(1)}%
										</div>
									</div>
								</div>
							</section>
						)}

						{fillSuccessMessage && (
							<p className="rounded-(--radius-sm) bg-(--color-system-healthy)/8 px-2 py-1 text-(length:--text-sm) text-(--color-system-healthy-fg)">
								{fillSuccessMessage}
							</p>
						)}
						{statusSuccessMessage && (
							<p className="rounded-(--radius-sm) bg-(--color-system-healthy)/8 px-2 py-1 text-(length:--text-sm) text-(--color-system-healthy-fg)">
								{statusSuccessMessage}
							</p>
						)}

						{data?.actions && data.actions.length > 0 && (
							<section className="flex flex-wrap gap-2">
								{data.actions.map((action) => (
									<button
										key={action.type}
										type="button"
										disabled={!action.enabled || isActionPending}
										className={[
											"rounded-(--radius-sm) px-3 py-1.5 text-(length:--text-sm) font-medium",
											"border border-(--color-border-subtle)",
											action.enabled
												? "bg-(--color-surface-panel-base) text-(--color-foreground) hover:bg-(--color-interaction-hover-subtle-bg)"
												: "text-(--color-foreground-tertiary) opacity-50",
										].join(" ")}
										onClick={() => handleAction(action.type)}
									>
										{action.label}
									</button>
								))}
							</section>
						)}
					</div>
				</PanelBody>
			</Panel>
			<Sheet open={fillSheetOpen} onOpenChange={setFillSheetOpen}>
				<SheetContent
					side="right"
					aria-label="订单确认"
					aria-describedby={undefined}
					className="w-(--width-drawer) max-w-(--width-drawer)"
				>
					<form className="flex h-full flex-col gap-4 p-4" onSubmit={submitRecordFill}>
						<SheetHeader>
							<SheetTitle>订单确认</SheetTitle>
							<SheetDescription>
								manual / paper 手工成交录入，不触发自动交易。
							</SheetDescription>
						</SheetHeader>
						<div className="grid grid-cols-2 gap-3 text-(length:--text-sm)">
							<div>
								<span className="text-(--color-foreground-tertiary)">intent_id</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.intentId ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-tertiary)">标的</span>
								<div className="font-data text-(--color-foreground)">#{data?.execution?.instrumentId ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-tertiary)">方向</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.direction ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-tertiary)">交易日</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.tradeDate ?? "—"}</div>
							</div>
						</div>
						<div className="flex flex-col gap-3">
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">成交数量</span>
								<input
									aria-label="成交数量"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									inputMode="numeric"
									value={fillForm.quantity}
									onChange={(event) => updateFillForm("quantity", event.target.value)}
								/>
							</label>
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">成交价格</span>
								<input
									aria-label="成交价格"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									inputMode="decimal"
									value={fillForm.fillPrice}
									onChange={(event) => updateFillForm("fillPrice", event.target.value)}
								/>
							</label>
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">手续费</span>
								<input
									aria-label="手续费"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									inputMode="decimal"
									value={fillForm.fee}
									onChange={(event) => updateFillForm("fee", event.target.value)}
								/>
							</label>
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">滑点</span>
								<input
									aria-label="滑点"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									inputMode="decimal"
									value={fillForm.slippage}
									onChange={(event) => updateFillForm("slippage", event.target.value)}
								/>
							</label>
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">备注</span>
								<textarea
									aria-label="备注"
									className="min-h-20 resize-none rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 text-(--color-foreground)"
									value={fillForm.notes}
									onChange={(event) => updateFillForm("notes", event.target.value)}
								/>
							</label>
						</div>
						{fillErrorMessage && (
							<p className="rounded-(--radius-sm) bg-(--color-status-led-error)/8 px-2 py-1.5 text-(length:--text-sm) text-(--color-status-led-error)">
								{fillErrorMessage}
							</p>
						)}
						<SheetFooter className="mt-auto">
							<button
								type="button"
								className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-(length:--text-sm) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
								onClick={() => setFillSheetOpen(false)}
							>
								取消
							</button>
							<button
								type="submit"
								disabled={recordFillMutation.isPending}
								className="rounded-(--radius-sm) bg-(--color-accent) px-3 py-1.5 text-(length:--text-sm) font-medium text-(--color-accent-foreground) disabled:opacity-50"
							>
								{recordFillMutation.isPending ? "提交中" : "提交手工成交"}
							</button>
						</SheetFooter>
					</form>
				</SheetContent>
			</Sheet>
			<Dialog open={statusDialogOpen} onOpenChange={setStatusDialogOpen}>
				<DialogContent aria-describedby={undefined}>
					<DialogHeader>
						<DialogTitle>高风险状态确认</DialogTitle>
						<DialogDescription>
							manual / paper 意图状态更新，仅记录状态机流转，不触发自动交易。
						</DialogDescription>
					</DialogHeader>
					<div className="flex flex-col gap-3 text-(length:--text-sm)">
						<p
							data-impact-summary
							className="rounded-(--radius-sm) bg-(--color-risk-warning)/8 px-2 py-1.5 text-(--color-foreground-secondary)"
						>
							将 intent {data?.execution?.intentId ?? "—"} 从 {data?.execution?.status ?? "—"} 更新为{" "}
							{intentStatusLabel(targetStatus)}。
						</p>
						<label className="flex flex-col gap-1">
							<span className="text-(--color-foreground-secondary)">目标状态</span>
							<select
								aria-label="目标状态"
								className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 text-(--color-foreground)"
								value={targetStatus}
								onChange={(event) => setTargetStatus(toIntentStatus(event.target.value))}
							>
								{INTENT_STATUS_OPTIONS.map((option) => (
									<option key={option.value} value={option.value}>
										{option.label}
									</option>
								))}
							</select>
						</label>
						<p
							data-recovery-hint
							className="text-xs text-(--color-foreground-tertiary)"
						>
							如需恢复，请再次通过后端状态机更新；无本地回滚或自动交易提交。
						</p>
						<span
							data-danger-marker="intent-status-transition"
							className="text-xs font-medium text-(--color-risk-warning-fg)"
						>
							状态机变更
						</span>
						{statusErrorMessage && (
							<p className="rounded-(--radius-sm) bg-(--color-status-led-error)/8 px-2 py-1.5 text-(--color-status-led-error)">
								{statusErrorMessage}
							</p>
						)}
					</div>
					<DialogFooter>
						<button
							type="button"
							data-cancel-control
							className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-(length:--text-sm) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
							onClick={() => setStatusDialogOpen(false)}
						>
							取消
						</button>
						<button
							type="button"
							data-confirm-control
							disabled={updateIntentStatusMutation.isPending}
							className="rounded-(--radius-sm) bg-(--color-risk-warning) px-3 py-1.5 text-(length:--text-sm) font-medium text-(--color-risk-warning-fg) disabled:opacity-50"
							onClick={submitIntentStatus}
						>
							{updateIntentStatusMutation.isPending ? "提交中" : "确认状态变更"}
						</button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
	);
}

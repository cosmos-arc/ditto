import { type FormEvent, useRef, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { SignalExecutionIntent } from "@/types";
import type { RecordFillRequest } from "../api/fills";
import { classifyMutationFailure } from "../api/mutation-result";
import { useRecordFill } from "../hooks/use-record-fill";
import { useSignalDetail } from "../hooks/use-signal-detail";

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
	readonly fillId: string;
	readonly tradeDate: string;
	readonly quantity: string;
	readonly fillPrice: string;
	readonly fee: string;
	readonly slippage: string;
	readonly notes: string;
}

const EMPTY_FILL_FORM: FillFormState = {
	fillId: "",
	tradeDate: "",
	quantity: "",
	fillPrice: "",
	fee: "0",
	slippage: "0",
	notes: "",
};

function createFillFormState(execution: SignalExecutionIntent): FillFormState {
	const defaultQuantity = execution.remainingQuantity ?? execution.quantity;
	return {
		fillId: `fill-${execution.intentId}-${globalThis.crypto.randomUUID()}`,
		tradeDate: execution.tradeDate,
		quantity: defaultQuantity > 0 ? String(defaultQuantity) : "",
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
	if (!form.fillId) {
		return { error: "缺少 fill_id，无法保证成交录入幂等" };
	}
	if (!/^\d{4}-\d{2}-\d{2}$/.test(form.tradeDate)) {
		return { error: "实际成交日必须使用 YYYY-MM-DD" };
	}

	const quantity = parseFiniteNumber(form.quantity);
	if (quantity == null || quantity <= 0) {
		return { error: "成交数量必须大于 0" };
	}
	if (execution.remainingQuantity != null && quantity > execution.remainingQuantity) {
		return { error: `成交数量不能超过剩余数量 ${execution.remainingQuantity.toLocaleString("en-US")}` };
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
			fill_id: form.fillId,
			intent_id: execution.intentId,
			strategy_id: execution.strategyId,
			trade_date: form.tradeDate,
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
	const failureKind = classifyMutationFailure(error);
	if (failureKind === "unknown") {
		return "提交结果未知；重试将复用同一 fill_id 与成交内容，避免重复录入。";
	}
	if (failureKind === "conflict" && error instanceof ApiError) return `成交冲突：${error.message}`;
	if (error instanceof ApiError) {
		return error.errorCode ? `${error.message}（${error.errorCode}）` : error.message;
	}
	return null;
}

export function SignalDetailPanel({ signalId }: SignalDetailPanelProps) {
	const { data, isLoading, isError, refetch } = useSignalDetail(signalId);
	const recordFillMutation = useRecordFill();
	const recordFillTriggerRef = useRef<HTMLButtonElement>(null);
	const [fillSheetOpen, setFillSheetOpen] = useState(false);
	const [fillForm, setFillForm] = useState<FillFormState>(EMPTY_FILL_FORM);
	const [reviewConfirmed, setReviewConfirmed] = useState(false);
	const [fillValidationError, setFillValidationError] = useState<string | null>(null);
	const [fillSuccessMessage, setFillSuccessMessage] = useState<string | null>(null);
	const [lastFillPayload, setLastFillPayload] = useState<RecordFillRequest | null>(null);
	const reviewReasons = data?.execution?.reviewReasons.filter((reason) => reason !== "READY_FOR_REVIEW") ?? [];

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
				<PanelBody className="p-3">
					<div
						role="alert"
						className="flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
					>
						<span>信号详情加载失败</span>
						<Button variant="outline" size="sm" onClick={() => void refetch()}>
							重试
						</Button>
					</div>
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
		setLastFillPayload(null);
		setFillSuccessMessage(null);
		setFillValidationError(null);
		setReviewConfirmed(false);
		setFillForm(createFillFormState(data.execution));
		setFillSheetOpen(true);
	}

	function executeRecordFill(payload: RecordFillRequest) {
		recordFillMutation.mutate(payload, {
			onSuccess: () => {
				setFillSheetOpen(false);
				setFillSuccessMessage("手工成交已录入");
			},
		});
	}

	function submitRecordFill(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setFillValidationError(null);

		const result = buildRecordFillRequest(data?.execution, fillForm);
		if ("error" in result) {
			setFillValidationError(result.error);
			return;
		}
		if (reviewReasons.length > 0 && !reviewConfirmed) {
			setFillValidationError("请先确认已复核后端返回的原因");
			return;
		}

		setLastFillPayload(result.payload);
		executeRecordFill(result.payload);
	}

	function updateFillForm(field: keyof FillFormState, value: string) {
		setFillForm((current) => ({ ...current, [field]: value }));
	}

	function handleAction(actionType: string) {
		if (actionType === "record_fill") {
			openRecordFillSheet();
		}
	}

	const fillErrorMessage = fillValidationError ?? describeMutationError(recordFillMutation.error);
	const isActionPending = recordFillMutation.isPending;
	const fillFailureKind = classifyMutationFailure(recordFillMutation.error);
	const isFillConflict = fillFailureKind === "conflict";
	const canRetryFill = recordFillMutation.isError && fillFailureKind === "unknown" && lastFillPayload !== null;
	const mustPreserveFillCommand = recordFillMutation.isPending || canRetryFill;

	function handleFillSheetOpenChange(nextOpen: boolean) {
		if (!nextOpen && mustPreserveFillCommand) return;
		setFillSheetOpen(nextOpen);
	}

	function closeFillAndRefresh() {
		setFillSheetOpen(false);
		void refetch();
	}

	return (
		<>
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<div className="flex flex-col gap-(--density-gutter) p-3">
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">决策依据</h4>
							<p className="text-(length:--text-sm) leading-relaxed text-(--color-foreground)">{data?.explanation}</p>
						</section>

						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">风控检查</h4>
							<ul className="flex flex-col gap-1">
								{data?.riskChecks.map((check) => (
									<li key={check.name} className="flex items-start gap-2 text-(length:--text-sm)">
										<span className={STATUS_STYLE[check.status as RiskCheckStatus]}>
											{STATUS_ICON[check.status as RiskCheckStatus]}
										</span>
										<div>
											<span className="font-medium text-(--color-foreground)">{check.name}</span>
											<span className="ml-1 text-(--color-foreground-tertiary)">{check.message}</span>
										</div>
									</li>
								))}
							</ul>
						</section>

						{data?.portfolioImpact && (
							<section>
								<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">组合影响</h4>
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
							<p
								role="status"
								aria-live="polite"
								className="rounded-(--radius-sm) bg-(--color-system-healthy)/8 px-2 py-1 text-(length:--text-sm) text-(--color-system-healthy-fg)"
							>
								{fillSuccessMessage}
							</p>
						)}
						{data?.actions && data.actions.length > 0 && (
							<section className="flex flex-wrap gap-2">
								{data.actions.map((action) => (
									<button
										key={action.type}
										ref={action.type === "record_fill" ? recordFillTriggerRef : undefined}
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
			<Sheet open={fillSheetOpen} onOpenChange={handleFillSheetOpenChange}>
				<SheetContent
					side="right"
					aria-label="订单确认"
					aria-describedby={undefined}
					onCloseAutoFocus={(event) => {
						event.preventDefault();
						recordFillTriggerRef.current?.focus();
					}}
					className="w-full overflow-y-auto sm:max-w-(--width-drawer)"
				>
					<form className="flex min-h-full flex-col gap-4 p-4" onSubmit={submitRecordFill}>
						<SheetHeader>
							<SheetTitle>订单确认</SheetTitle>
							<SheetDescription>
								manual / paper 手工成交录入；每次提交追加一笔，可分批重复录入，不触发自动交易。
							</SheetDescription>
						</SheetHeader>
						<div className="grid grid-cols-1 gap-3 text-(length:--text-sm) sm:grid-cols-2">
							<div>
								<span className="text-(--color-foreground-secondary)">intent_id</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.intentId ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-secondary)">标的</span>
								<div className="font-data text-(--color-foreground)">#{data?.execution?.instrumentId ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-secondary)">方向</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.direction ?? "—"}</div>
							</div>
							<div>
								<span className="text-(--color-foreground-secondary)">建议交易日</span>
								<div className="font-data text-(--color-foreground)">{data?.execution?.tradeDate ?? "—"}</div>
							</div>
						</div>
						<section
							aria-label="成交进度"
							className="grid grid-cols-3 gap-2 rounded-(--radius-sm) bg-(--color-surface-2) px-3 py-2 font-data text-(length:--text-sm) text-(--color-foreground-secondary)"
						>
							<span>建议 {(data?.execution?.quantity ?? 0).toLocaleString("en-US")}</span>
							<span>已成交 {data?.execution?.filledQuantity?.toLocaleString("en-US") ?? "—"}</span>
							<span>剩余 {data?.execution?.remainingQuantity?.toLocaleString("en-US") ?? "—"}</span>
						</section>
						<div className="flex flex-col gap-3">
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">实际成交日</span>
								<input
									type="date"
									aria-label="实际成交日"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									disabled={mustPreserveFillCommand}
									value={fillForm.tradeDate}
									onChange={(event) => updateFillForm("tradeDate", event.target.value)}
								/>
							</label>
							<label className="flex flex-col gap-1 text-(length:--text-sm)">
								<span className="text-(--color-foreground-secondary)">成交数量</span>
								<input
									aria-label="成交数量"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
									disabled={mustPreserveFillCommand}
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
									disabled={mustPreserveFillCommand}
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
									disabled={mustPreserveFillCommand}
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
									disabled={mustPreserveFillCommand}
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
									disabled={mustPreserveFillCommand}
									value={fillForm.notes}
									onChange={(event) => updateFillForm("notes", event.target.value)}
								/>
							</label>
						</div>
						{reviewReasons.length > 0 && (
							<section
								aria-labelledby="fill-review-reasons-title"
								className="rounded-(--radius-sm) border border-(--color-risk-warning)/35 bg-(--color-risk-warning)/8 p-3 text-(length:--text-sm)"
							>
								<h3 id="fill-review-reasons-title" className="font-medium text-(--color-risk-warning-fg)">
									提交前需复核
								</h3>
								<p className="mt-1 text-(--color-foreground-secondary)">后端将本次决策标记为 review，请逐项确认：</p>
								<ul className="my-2 list-disc pl-5 font-data text-(--color-foreground)">
									{reviewReasons.map((reason) => (
										<li key={reason}>{reason}</li>
									))}
								</ul>
								<label className="flex cursor-pointer items-start gap-2 text-(--color-foreground)">
									<input
										type="checkbox"
										className="mt-0.5"
										checked={reviewConfirmed}
										disabled={mustPreserveFillCommand}
										onChange={(event) => setReviewConfirmed(event.target.checked)}
									/>
									<span>我已复核以上原因</span>
								</label>
							</section>
						)}
						{fillErrorMessage && (
							<p
								role="alert"
								className="rounded-(--radius-sm) bg-(--color-status-led-error)/8 px-2 py-1.5 text-(length:--text-sm) text-(--color-status-led-error)"
							>
								{fillErrorMessage}
							</p>
						)}
						<SheetFooter className="mt-auto">
							<button
								type="button"
								className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-(length:--text-sm) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
								disabled={mustPreserveFillCommand}
								onClick={() => handleFillSheetOpenChange(false)}
							>
								取消
							</button>
							{isFillConflict && (
								<button
									type="button"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-(length:--text-sm) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
									onClick={closeFillAndRefresh}
								>
									关闭并刷新流水
								</button>
							)}
							{canRetryFill ? (
								<button
									type="button"
									className="rounded-(--radius-sm) bg-(--color-accent) px-3 py-1.5 text-(length:--text-sm) font-medium text-(--color-accent-foreground)"
									onClick={() => executeRecordFill(lastFillPayload)}
								>
									使用同一标识重试
								</button>
							) : !isFillConflict ? (
								<button
									type="submit"
									disabled={recordFillMutation.isPending}
									className="rounded-(--radius-sm) bg-(--color-accent) px-3 py-1.5 text-(length:--text-sm) font-medium text-(--color-accent-foreground) disabled:opacity-50"
								>
									{recordFillMutation.isPending ? "提交中" : "提交手工成交"}
								</button>
							) : null}
						</SheetFooter>
					</form>
				</SheetContent>
			</Sheet>
		</>
	);
}

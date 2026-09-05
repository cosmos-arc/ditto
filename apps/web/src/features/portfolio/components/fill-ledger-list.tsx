import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { Button } from "@/components/ui/button";
import type { FillLedgerEntry, FillLedgerIssue } from "@/types";
import { useFillLedger } from "../hooks";
import type { FillCorrectionKind } from "./fill-correction-form";
import { FillCorrectionSheet } from "./fill-correction-sheet";
import { FillLedgerRow } from "./fill-ledger-row";

interface FillLedgerListProps {
	readonly enabled?: boolean;
}

type ActiveCorrection = {
	readonly fill: FillLedgerEntry;
	readonly kind: FillCorrectionKind;
	readonly trigger: HTMLButtonElement;
};

const ISSUE_LABEL = {
	effective_with_adjustment: "有效成交与更正事件同时存在",
	missing_effective_and_adjustment: "原始成交缺少有效状态或更正事件",
	replacement_missing_raw: "替换成交缺少原始证据",
	replacement_not_resolved: "替换成交未进入有效链",
	replacement_cycle: "替换链形成循环",
	orphan_adjustment: "更正事件缺少原始成交",
	ghost_effective: "有效成交缺少原始流水",
	replacement_identity_mismatch: "替换成交身份与原始成交不一致",
} as const;

function FillLedgerConsistencyAlert({ issues }: { readonly issues: readonly FillLedgerIssue[] }) {
	if (issues.length === 0) return null;
	return (
		<div
			role="alert"
			aria-label="成交证据一致性告警"
			className="mb-2 rounded-(--radius-sm) border border-(--color-risk-warning)/35 bg-(--color-risk-warning)/8 px-3 py-2 text-xs text-(--color-risk-warning-fg)"
		>
			<p className="font-medium">发现 {issues.length} 项成交证据一致性问题，涉及证据已锁定，修复后再更正。</p>
			<ul className="mt-1 flex list-none flex-col gap-1 p-0">
				{issues.map((issue) => (
					<li
						key={`${issue.code}-${issue.fillId}-${issue.relatedFillId ?? "none"}-${issue.adjustmentId ?? "none"}`}
						className="flex min-w-0 flex-wrap gap-x-2 text-(--color-foreground-secondary)"
					>
						<span>{ISSUE_LABEL[issue.code]}</span>
						<span className="min-w-0 break-all font-data">成交 {issue.fillId}</span>
						{issue.relatedFillId && <span className="min-w-0 break-all font-data">关联 {issue.relatedFillId}</span>}
						{issue.adjustmentId && <span className="min-w-0 break-all font-data">事件 {issue.adjustmentId}</span>}
						{issue.mismatchedFields.length > 0 && (
							<span className="font-data">字段 {issue.mismatchedFields.join(", ")}</span>
						)}
					</li>
				))}
			</ul>
		</div>
	);
}

export function FillLedgerList({ enabled = true }: FillLedgerListProps) {
	const { data, isLoading, isError, refetch } = useFillLedger(undefined, { enabled });
	const [activeCorrection, setActiveCorrection] = useState<ActiveCorrection | null>(null);
	const [correctionOpen, setCorrectionOpen] = useState(false);
	const [correctionResult, setCorrectionResult] = useState<string | null>(null);
	const fills = data?.fills ?? [];
	const issues = data?.issues ?? [];
	const fillsByIntent = fills.reduce<Record<string, number>>((counts, fill) => {
		counts[fill.intentId] = (counts[fill.intentId] ?? 0) + 1;
		return counts;
	}, {});

	function openCorrection(kind: FillCorrectionKind, fill: FillLedgerEntry, trigger: HTMLButtonElement) {
		setCorrectionResult(null);
		setActiveCorrection({ kind, fill, trigger });
		setCorrectionOpen(true);
	}

	return (
		<>
			<ContextSection title="手工执行流水" count={fills.length} data-info-level="l1" data-info-unit="fill-ledger">
				<div className="py-2">
					{isLoading && (
						<div role="status" aria-label="手工执行流水加载中">
							<LoadingSkeleton variant="table" rows={4} />
						</div>
					)}
					{isError && (
						<div
							role="alert"
							className="flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
						>
							<span>手工执行流水加载失败</span>
							<Button variant="outline" size="sm" onClick={() => void refetch()}>
								重试
							</Button>
						</div>
					)}
					{!isLoading && !isError && <FillLedgerConsistencyAlert issues={issues} />}
					{!isLoading && !isError && fills.length === 0 && issues.length === 0 && (
						<div
							role="status"
							aria-label="手工执行流水状态"
							className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)"
						>
							尚未录入手工成交
						</div>
					)}
					{correctionResult && (
						<p
							role="status"
							aria-label="成交更正结果"
							aria-live="polite"
							className="mb-2 rounded-(--radius-sm) bg-(--color-system-healthy)/8 px-2 py-1.5 text-sm text-(--color-system-healthy-fg)"
						>
							{correctionResult}
						</p>
					)}
					{!isLoading && !isError && fills.length > 0 && (
						<>
							<span role="status" aria-label="手工执行流水加载完成" className="sr-only">
								手工执行流水已加载，共 {fills.length} 笔
							</span>
							<ul
								aria-label="手工成交记录"
								// biome-ignore lint/a11y/noNoninteractiveTabindex: The horizontally scrollable ledger must be keyboard-focusable in narrow activity rails.
								tabIndex={0}
								className="m-0 flex list-none flex-col gap-1 overflow-x-auto p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-focus-ring)"
							>
								{fills.map((fill) => (
									<FillLedgerRow
										key={fill.id}
										fill={fill}
										splitCount={fillsByIntent[fill.intentId] ?? 0}
										onCorrect={openCorrection}
									/>
								))}
							</ul>
						</>
					)}
				</div>
			</ContextSection>
			{activeCorrection && (
				<FillCorrectionSheet
					key={`${activeCorrection.kind}-${activeCorrection.fill.id}`}
					fill={activeCorrection.fill}
					kind={activeCorrection.kind}
					open={correctionOpen}
					triggerElement={activeCorrection.trigger}
					onOpenChange={setCorrectionOpen}
					onClosed={() => setActiveCorrection(null)}
					onSuccess={setCorrectionResult}
					onRefresh={() => void refetch()}
				/>
			)}
		</>
	);
}

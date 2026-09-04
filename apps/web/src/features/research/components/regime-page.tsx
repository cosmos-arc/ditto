import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { AnalyticalLayout } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { RegimeDiagnostics, RegimeDiagnosticsScope } from "../api/regime-diagnostics";
import { isCompleteRegimeScope, useRegimeDiagnostics } from "../hooks/use-regime-diagnostics";
import { RegimeDiagnosticsView, regimeLabelMeta } from "./regime-diagnostics-view";

const FIELD_CLASS =
	"h-9 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 font-data text-xs text-(--color-foreground) outline-none focus:border-(--color-border-strong)";

function typedError(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "REGIME_DIAGNOSTICS_ERROR"}: ${error.message}`
		: error.message;
}

function compactIdentity(value: string): string {
	return value.length > 24 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}

function ScopeField({
	label,
	name,
	type = "text",
	defaultValue,
	placeholder,
}: {
	readonly label: string;
	readonly name: string;
	readonly type?: "text" | "number" | "date";
	readonly defaultValue: string | number;
	readonly placeholder?: string;
}) {
	return (
		<label className="block space-y-1.5 text-xs text-(--color-foreground-secondary)">
			<span>{label}</span>
			<input
				required
				name={name}
				type={type}
				min={type === "number" ? 1 : undefined}
				aria-label={label}
				defaultValue={defaultValue}
				placeholder={placeholder}
				className={FIELD_CLASS}
				spellCheck={false}
			/>
		</label>
	);
}

function RegimeScopeSheet({
	open,
	scope,
	onApply,
	onOpenChange,
}: {
	readonly open: boolean;
	readonly scope: RegimeDiagnosticsScope | null;
	readonly onApply: (scope: RegimeDiagnosticsScope) => void;
	readonly onOpenChange: (open: boolean) => void;
}) {
	const [validation, setValidation] = useState<string | null>(null);

	function submit(event: FormEvent<HTMLFormElement>): void {
		event.preventDefault();
		const data = new FormData(event.currentTarget);
		const candidate: RegimeDiagnosticsScope = {
			snapshotId: String(data.get("snapshotId") ?? "").trim(),
			snapshotManifestHash: String(data.get("snapshotManifestHash") ?? "").trim(),
			benchmarkInstrumentId: Number(data.get("benchmarkInstrumentId")),
			startDate: String(data.get("startDate") ?? "").trim(),
			endDate: String(data.get("endDate") ?? "").trim(),
			knowledgeCutoff: String(data.get("knowledgeCutoff") ?? "").trim(),
		};
		if (!isCompleteRegimeScope(candidate)) {
			setValidation("请提供 64 位小写 manifest hash，并确保开始日 ≤ 结束日 < 知识截止日。");
			return;
		}
		setValidation(null);
		onApply(candidate);
		onOpenChange(false);
	}

	return (
		<Sheet
			open={open}
			onOpenChange={(next) => {
				if (!next) setValidation(null);
				onOpenChange(next);
			}}
		>
			<SheetContent side="right" className="p-0" aria-label="绑定 PIT 诊断范围">
				<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<SheetTitle>绑定 PIT 诊断范围</SheetTitle>
					<SheetDescription>只读取一个内容寻址快照；任一身份缺失时保持未评估。</SheetDescription>
				</SheetHeader>
				<form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
					<div className="flex-1 space-y-4 overflow-y-auto p-5">
						<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3 text-xs leading-5 text-(--color-foreground-tertiary)">
							收盘数据按日终观测。服务端强制{" "}
							<span className="font-data text-(--color-foreground-secondary)">end_date &lt; knowledge_cutoff</span>
							，不会把截止日当天收盘价当成已知事实。
						</div>
						<ScopeField
							label="研究快照 ID"
							name="snapshotId"
							defaultValue={scope?.snapshotId ?? ""}
							placeholder="snapshot-regime-1"
						/>
						<ScopeField
							label="快照 manifest hash"
							name="snapshotManifestHash"
							defaultValue={scope?.snapshotManifestHash ?? ""}
							placeholder="64 位 sha256"
						/>
						<ScopeField
							label="基准 Instrument ID"
							name="benchmarkInstrumentId"
							type="number"
							defaultValue={scope?.benchmarkInstrumentId ?? ""}
						/>
						<div className="grid grid-cols-2 gap-3">
							<ScopeField label="诊断开始日期" name="startDate" type="date" defaultValue={scope?.startDate ?? ""} />
							<ScopeField label="诊断结束日期" name="endDate" type="date" defaultValue={scope?.endDate ?? ""} />
						</div>
						<ScopeField
							label="知识截止日期"
							name="knowledgeCutoff"
							type="date"
							defaultValue={scope?.knowledgeCutoff ?? ""}
						/>
						{validation && (
							<p role="alert" className="text-xs text-(--color-led-danger)">
								{validation}
							</p>
						)}
					</div>
					<SheetFooter className="border-t border-(--color-border-subtle) p-4">
						<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
							取消
						</Button>
						<Button type="submit">运行 PIT 诊断</Button>
					</SheetFooter>
				</form>
			</SheetContent>
		</Sheet>
	);
}

function RegimeStrip({
	diagnostics,
	scope,
	onBind,
}: {
	readonly diagnostics?: RegimeDiagnostics;
	readonly scope: RegimeDiagnosticsScope | null;
	readonly onBind: () => void;
}) {
	const meta = diagnostics ? regimeLabelMeta(diagnostics.current.label) : null;
	const metricClass = "flex items-center gap-1.5 whitespace-nowrap";
	const labelClass = "text-xs text-(--color-foreground-tertiary)";
	const valueClass = "font-data text-xs font-medium text-(--color-foreground)";
	return (
		<div
			data-info-level="l1"
			data-info-unit="regime-strip"
			className="flex h-[42px] items-center gap-(--density-gutter) overflow-x-auto border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
		>
			<div className={metricClass}>
				<span className={labelClass}>REGIME</span>
				{meta ? (
					<StatusBadge size="sm" variant={meta.badge} label={meta.code} />
				) : (
					<span className="text-xs text-(--color-led-warning)">未评估</span>
				)}
			</div>
			<span className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
			<div className={metricClass}>
				<span className={labelClass}>SCORE</span>
				<span className={valueClass}>{diagnostics ? diagnostics.current.score.toFixed(1) : "—"}</span>
			</div>
			<span className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
			<div className={metricClass}>
				<span className={labelClass}>BENCHMARK</span>
				<span className={valueClass}>{scope?.benchmarkInstrumentId ?? "未绑定"}</span>
			</div>
			<span className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
			<div className={metricClass}>
				<span className={labelClass}>CUTOFF</span>
				<span className={valueClass}>{scope?.knowledgeCutoff ?? "未绑定"}</span>
			</div>
			<span className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
			<div className={`${metricClass} min-w-0`}>
				<span className={labelClass}>SNAPSHOT</span>
				<span className={`${valueClass} max-w-48 truncate`} title={scope?.snapshotId}>
					{scope?.snapshotId ?? "未绑定"}
				</span>
			</div>
			<Button type="button" size="xs" variant="outline" className="ml-auto" onClick={onBind}>
				{scope ? "更改诊断范围" : "绑定诊断范围"}
			</Button>
		</div>
	);
}

function EmptyWorkspace({ onBind }: { readonly onBind: () => void }) {
	return (
		<div className="flex h-full min-h-80 items-center justify-center p-5">
			<div className="w-full max-w-2xl rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-6 text-center shadow-[0_18px_60px_color-mix(in_oklch,var(--color-surface-app)_70%,transparent)]">
				<div className="mx-auto flex size-11 items-center justify-center rounded-full border border-(--color-accent) bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] font-data text-xs font-semibold text-(--color-accent)">
					PIT
				</div>
				<h2 className="mt-4 text-base font-semibold">诊断范围未绑定</h2>
				<p className="mx-auto mt-2 max-w-xl text-xs leading-5 text-(--color-foreground-tertiary)">
					Regime 不从“最新行情”推断。绑定不可变快照、manifest、基准与知识截止日后，才展示服务端评分。
				</p>
				<div className="mt-5 grid gap-2 text-left sm:grid-cols-3">
					{[
						["01", "锁定制品", "snapshot + manifest hash"],
						["02", "锁定时间", "start / end / cutoff"],
						["03", "核验基准", "instrument id + bars evidence"],
					].map(([index, title, detail]) => (
						<div
							key={index}
							className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-app) p-3"
						>
							<span className="font-data text-xs text-(--color-accent)">{index}</span>
							<p className="mt-1 text-xs font-medium">{title}</p>
							<p className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">{detail}</p>
						</div>
					))}
				</div>
				<Button type="button" className="mt-5" onClick={onBind}>
					绑定诊断范围
				</Button>
			</div>
		</div>
	);
}

function ErrorWorkspace({ error, onRetry }: { readonly error: Error; readonly onRetry: () => void }) {
	return (
		<div className="flex h-full min-h-72 items-center justify-center p-5">
			<div className="w-full max-w-xl rounded-(--radius-lg) border border-(--color-led-danger) bg-(--color-surface-panel-base) p-5">
				<p className="text-xs font-medium text-(--color-led-danger)">诊断证据不可用</p>
				<p role="alert" className="mt-2 break-words font-data text-xs text-(--color-foreground-secondary)">
					{typedError(error)}
				</p>
				<p className="mt-3 text-xs leading-5 text-(--color-foreground-tertiary)">
					页面保持未评估；不会退回静态 Regime、伪造驱动因子或策略建议。
				</p>
				<Button type="button" size="sm" variant="outline" className="mt-4" onClick={onRetry}>
					重试同一范围
				</Button>
			</div>
		</div>
	);
}

function EvidenceRow({
	label,
	value,
	mono = false,
}: {
	readonly label: string;
	readonly value: string;
	readonly mono?: boolean;
}) {
	return (
		<div className="border-b border-(--color-border-subtle) py-2.5 last:border-b-0">
			<dt className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">{label}</dt>
			<dd
				title={value}
				className={`mt-1 break-all text-xs text-(--color-foreground-secondary) ${mono ? "font-data" : ""}`}
			>
				{value}
			</dd>
		</div>
	);
}

function RegimeEvidenceRail({
	diagnostics,
	scope,
}: {
	readonly diagnostics?: RegimeDiagnostics;
	readonly scope: RegimeDiagnosticsScope | null;
}) {
	return (
		<div
			data-info-level="l2"
			data-info-unit="regime-evidence"
			className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-panel-base)"
		>
			<div className="h-full overflow-y-auto p-3">
				<div className="flex items-center justify-between gap-2">
					<h2 className="text-sm font-semibold">证据与方法</h2>
					<span className="rounded-full bg-(--color-surface-strip) px-2 py-1 text-xs text-(--color-foreground-tertiary)">
						{diagnostics ? "VERIFIED" : scope ? "UNVERIFIED" : "UNBOUND"}
					</span>
				</div>
				<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
					单一 momentum 20D 模型；不声称覆盖波动率、资金流、市场广度或宏观驱动。
				</p>
				<dl className="mt-3">
					<EvidenceRow label="Snapshot" value={scope?.snapshotId ?? "未绑定"} mono />
					<EvidenceRow
						label="Manifest SHA-256"
						value={scope ? compactIdentity(scope.snapshotManifestHash) : "未绑定"}
						mono
					/>
					<EvidenceRow label="Date scope" value={scope ? `${scope.startDate} → ${scope.endDate}` : "未绑定"} mono />
					<EvidenceRow label="Knowledge cutoff" value={scope?.knowledgeCutoff ?? "未绑定"} mono />
					<EvidenceRow label="Bars input" value={diagnostics?.barsInputId ?? "未核验"} mono />
					<EvidenceRow label="Dataset" value={diagnostics?.datasetId ?? "未核验"} mono />
				</dl>
				<div className="mt-4 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-app) p-3">
					<p className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">Source snapshots</p>
					{diagnostics?.sourceSnapshotIds.length ? (
						diagnostics.sourceSnapshotIds.map((source) => (
							<p key={source} className="mt-2 break-all font-data text-xs text-(--color-foreground-secondary)">
								{source}
							</p>
						))
					) : (
						<p className="mt-2 text-xs text-(--color-led-warning)">未核验</p>
					)}
				</div>
				<div className="mt-3 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-xs leading-5 text-(--color-foreground-tertiary)">
					<p className="font-medium text-(--color-foreground-secondary)">策略影响</p>
					<p className="mt-1">当前 API 未返回策略归因或可执行建议，因此保持“未评估”。模型映射比率仅是评分引擎输出。</p>
				</div>
			</div>
		</div>
	);
}

function TransitionBand({ diagnostics }: { readonly diagnostics?: RegimeDiagnostics }) {
	const transitions = diagnostics?.transitions.slice(-4).toReversed() ?? [];
	return (
		<div
			data-info-level="l2"
			data-info-unit="regime-transitions"
			className="h-full overflow-y-auto border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-3"
		>
			<div className="flex items-center justify-between gap-3">
				<div>
					<h2 className="text-xs font-semibold">状态切换</h2>
					<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">连续可见观测之间的标签变化</p>
				</div>
				<span className="font-data text-xs text-(--color-foreground-tertiary)">
					{diagnostics ? `${transitions.length} transitions` : "未评估"}
				</span>
			</div>
			{transitions.length === 0 ? (
				<p className="mt-4 text-xs text-(--color-foreground-tertiary)">
					{diagnostics ? "该范围内没有状态切换" : "绑定范围后显示服务端状态切换"}
				</p>
			) : (
				<div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
					{transitions.map((transition) => (
						<div
							key={`${transition.observedAt}-${transition.fromLabel}-${transition.toLabel}`}
							className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-3 py-2"
						>
							<p className="font-data text-xs text-(--color-foreground-tertiary)">{transition.observedAt}</p>
							<div className="mt-1.5 flex items-center gap-1.5 text-xs">
								<span>{regimeLabelMeta(transition.fromLabel).code}</span>
								<span className="text-(--color-foreground-tertiary)">→</span>
								<span className="font-medium text-(--color-foreground)">
									{regimeLabelMeta(transition.toLabel).code}
								</span>
							</div>
						</div>
					))}
				</div>
			)}
		</div>
	);
}

export interface RegimePageProps {
	readonly initialScope?: RegimeDiagnosticsScope | null;
}

export function RegimePage({ initialScope = null }: RegimePageProps) {
	const [scope, setScope] = useState<RegimeDiagnosticsScope | null>(initialScope);
	const [scopeOpen, setScopeOpen] = useState(false);
	const query = useRegimeDiagnostics(scope);
	const diagnostics = query.data;

	let mainContent: ReactNode;
	if (!scope) mainContent = <EmptyWorkspace onBind={() => setScopeOpen(true)} />;
	else if (query.isPending)
		mainContent = (
			<div className="p-(--density-panel-padding)">
				<LoadingSkeleton variant="panel" rows={8} />
			</div>
		);
	else if (query.error) mainContent = <ErrorWorkspace error={query.error} onRetry={() => void query.refetch()} />;
	else if (diagnostics) mainContent = <RegimeDiagnosticsView diagnostics={diagnostics} />;
	else
		mainContent = (
			<div className="flex h-full items-center justify-center text-xs text-(--color-foreground-tertiary)">
				响应为空，未评估
			</div>
		);

	return (
		<>
			<section aria-label="PIT Regime 诊断" className="h-full min-h-0">
				<AnalyticalLayout
					className="[--height-strip-min:42px] [--height-main-min:20rem] [--height-analysis-band:10.5rem]"
					analysisSpansActivity
					strip={<RegimeStrip diagnostics={diagnostics} scope={scope} onBind={() => setScopeOpen(true)} />}
					main={
						<div
							data-info-level="l1"
							data-info-unit="regime-workspace"
							className="h-full overflow-y-auto p-(--density-panel-padding)"
						>
							{mainContent}
						</div>
					}
					activity={<RegimeEvidenceRail diagnostics={diagnostics} scope={scope} />}
					analysis={<TransitionBand diagnostics={diagnostics} />}
				/>
			</section>
			<RegimeScopeSheet open={scopeOpen} scope={scope} onApply={setScope} onOpenChange={setScopeOpen} />
		</>
	);
}

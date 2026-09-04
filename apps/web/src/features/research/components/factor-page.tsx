import { useParams } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { ObjectHubLayout, ShellHeaderExtension } from "@/features/shell";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { FactorDiagnosticsView } from "./factor-diagnostics-view";
import { type FactorPageOverlay, FactorPageOverlays } from "./factor-page-overlays";

const SCOPE_INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)";

interface FactorPageProps {
	readonly initialScope?: FactorDiagnosticsScope | null;
}

function ScopeField({
	label,
	name,
	defaultValue,
}: {
	readonly label: string;
	readonly name: string;
	readonly defaultValue: string;
}) {
	return (
		<label className="flex min-w-0 flex-col gap-1 text-xs text-(--color-foreground-secondary)">
			<span>{label}</span>
			<input name={name} required defaultValue={defaultValue} className={SCOPE_INPUT_CLASS} />
		</label>
	);
}

function RequirementRow({ label, value }: { readonly label: string; readonly value?: string }) {
	return (
		<div className="border-b border-(--color-border-subtle) py-3 last:border-b-0">
			<dt className="text-xs text-(--color-foreground-tertiary)">{label}</dt>
			<dd
				className={`mt-1 break-all text-xs ${
					value ? "font-data text-(--color-foreground)" : "text-(--color-led-warning)"
				}`}
			>
				{value || "未绑定"}
			</dd>
		</div>
	);
}

function DiagnosticsWorkspace({
	factorId,
	scope,
}: {
	readonly factorId: string;
	readonly scope: FactorDiagnosticsScope | null;
}) {
	return (
		<div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_21.25rem] gap-(--section-gap) p-(--density-panel-padding) max-[899px]:grid-cols-1">
			<section aria-label="诊断工作区" data-testid="factor-analysis-main" className="min-h-0 overflow-y-auto">
				{scope ? (
					<FactorDiagnosticsView factorId={factorId} scope={scope} />
				) : (
					<div className="flex h-full min-h-80 items-center justify-center p-6">
						<div className="w-full max-w-2xl rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-2) p-6 text-center">
							<div className="mx-auto flex size-10 items-center justify-center rounded-full border border-(--color-accent) bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] font-data text-sm text-(--color-accent)">
								PIT
							</div>
							<h2 className="mt-4 text-base font-semibold">等待不可变诊断</h2>
							<p className="mx-auto mt-2 max-w-lg text-xs leading-5 text-(--color-foreground-tertiary)">
								诊断不会从目录预览推导。绑定同一份数据快照、完整窗口与 registry hash 后，才读取服务端制品。
							</p>
							<ol className="mt-5 grid gap-2 text-left sm:grid-cols-3">
								{["绑定数据快照", "确认开始与结束日", "校验 Registry Hash"].map((step, index) => (
									<li
										key={step}
										className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-xs text-(--color-foreground-secondary)"
									>
										<span className="mr-2 font-data text-(--color-accent)">0{index + 1}</span>
										{step}
									</li>
								))}
							</ol>
						</div>
					</div>
				)}
			</section>
			<aside
				aria-label="证据要求"
				data-testid="factor-analysis-sidebar"
				className="min-h-0 overflow-y-auto border-l border-(--color-border-subtle) bg-(--color-surface-2) p-4 max-[899px]:hidden"
			>
				<div className="flex items-center justify-between gap-2">
					<h2 className="text-sm font-semibold">证据要求</h2>
					<span className="rounded-full bg-(--color-surface-3) px-2 py-1 text-[0.65rem] text-(--color-foreground-tertiary)">
						{scope ? "4 / 4" : "0 / 4"}
					</span>
				</div>
				<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
					缺少任一字段时查询 fail closed，不展示 0 值或目录级估计。
				</p>
				<dl className="mt-3">
					<RequirementRow label="Snapshot ID" value={scope?.snapshotId} />
					<RequirementRow label="开始日" value={scope?.startDate} />
					<RequirementRow label="结束日" value={scope?.endDate} />
					<RequirementRow label="Registry Hash" value={scope?.registryHash} />
				</dl>
				<div className="mt-4 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-xs text-(--color-foreground-tertiary)">
					<p className="font-medium text-(--color-foreground-secondary)">读取规则</p>
					<p className="mt-1 leading-5">
						窗口左闭；knowledge date、publication cutoff 与 source snapshot 由服务端验证。
					</p>
				</div>
			</aside>
		</div>
	);
}

/** Full-scope factor diagnostics task page. Scope must be explicit before any read. */
export function FactorPage({ initialScope = null }: FactorPageProps) {
	const { id } = useParams({ strict: false }) as { id: string };
	const factorId = id ?? "";
	const [scope, setScope] = useState<FactorDiagnosticsScope | null>(initialScope);
	const [overlay, setOverlay] = useState<FactorPageOverlay | null>(null);

	function submitScope(event: FormEvent<HTMLFormElement>): void {
		event.preventDefault();
		const data = new FormData(event.currentTarget);
		setScope({
			snapshotId: String(data.get("snapshotId") ?? "").trim(),
			startDate: String(data.get("startDate") ?? "").trim(),
			endDate: String(data.get("endDate") ?? "").trim(),
			registryHash: String(data.get("registryHash") ?? "").trim(),
		});
	}

	return (
		<>
			<ShellHeaderExtension>
				<div className="flex items-center gap-2">
					<Button type="button" size="sm" variant="outline" onClick={() => setOverlay("add-backtest")}>
						加入回测
					</Button>
					<Button type="button" size="sm" variant="outline" onClick={() => setOverlay("add-experiment")}>
						加入实验
					</Button>
					<Button type="button" size="sm" onClick={() => setOverlay("ai-analysis")}>
						AI 解读
					</Button>
				</div>
			</ShellHeaderExtension>
			<ObjectHubLayout
				meta={
					<div
						data-info-level="l1"
						data-info-unit="factor-meta"
						className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
					>
						<div className="flex flex-col gap-1">
							<span className="text-lg font-semibold">{factorId || "因子诊断"}</span>
							<span className="text-xs text-(--color-foreground-tertiary)">
								完整 scope 与 artifact identity 必须由服务端验证
							</span>
						</div>
						<span
							className={`rounded-full px-2 py-1 text-xs ${
								scope
									? "bg-(--color-led-success-bg) text-(--color-led-success)"
									: "bg-(--color-surface-2) text-(--color-foreground-tertiary)"
							}`}
						>
							{scope ? "不可变范围已绑定" : "诊断范围未绑定"}
						</span>
					</div>
				}
				tabs={
					<form
						onSubmit={submitScope}
						className="grid gap-2 border-y border-(--color-border-subtle) p-(--density-panel-padding) max-[899px]:grid-cols-1 min-[900px]:grid-cols-[minmax(8rem,1fr)_9rem_9rem_minmax(12rem,2fr)_auto]"
					>
						<ScopeField label="Snapshot ID" name="snapshotId" defaultValue={initialScope?.snapshotId ?? ""} />
						<ScopeField label="开始日" name="startDate" defaultValue={initialScope?.startDate ?? ""} />
						<ScopeField label="结束日" name="endDate" defaultValue={initialScope?.endDate ?? ""} />
						<ScopeField label="Registry Hash" name="registryHash" defaultValue={initialScope?.registryHash ?? ""} />
						<button
							type="submit"
							className="self-end rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs text-(--brand-accent-fg)"
						>
							读取诊断
						</button>
					</form>
				}
				main={
					<div data-info-level="l1" data-info-unit="factor-diagnostics-workspace" className="h-full overflow-y-auto">
						<DiagnosticsWorkspace factorId={factorId} scope={scope} />
					</div>
				}
				bottom={
					<div className="flex min-h-11 flex-wrap items-center justify-between gap-3 border-t border-(--color-border-subtle) bg-(--color-surface-2) px-4 py-2">
						<div className="min-w-0 text-xs text-(--color-foreground-tertiary)">
							{scope ? (
								<>
									<span className="font-data text-(--color-foreground-secondary)">{scope.snapshotId}</span>
									<span className="mx-2">·</span>
									<span className="font-data">
										{scope.startDate} → {scope.endDate}
									</span>
								</>
							) : (
								"绑定完整范围后可查看服务端诊断制品"
							)}
						</div>
						<Button
							type="button"
							size="sm"
							variant="outline"
							disabled={!scope}
							onClick={() => setOverlay("diagnostic-detail")}
						>
							诊断详情
						</Button>
					</div>
				}
			/>
			<FactorPageOverlays factorId={factorId} scope={scope} open={overlay} onClose={() => setOverlay(null)} />
		</>
	);
}

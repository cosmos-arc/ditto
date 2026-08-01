import { useParams } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { ObjectHubLayout } from "@/features/shell";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { FactorDiagnosticsView } from "./factor-diagnostics-view";

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

/** Full-scope factor diagnostics task page. Scope must be explicit before any read. */
export function FactorPage({ initialScope = null }: FactorPageProps) {
	const { id } = useParams({ strict: false }) as { id: string };
	const factorId = id ?? "";
	const [scope, setScope] = useState<FactorDiagnosticsScope | null>(initialScope);

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
		<ObjectHubLayout
			meta={
				<div data-info-level="l1" data-info-unit="factor-meta" className="flex flex-col gap-1 px-4 py-3">
					<span className="text-lg font-semibold">{factorId || "因子诊断"}</span>
					<span className="text-xs text-(--color-foreground-tertiary)">
						完整 scope 与 artifact identity 必须由服务端验证
					</span>
				</div>
			}
			tabs={
				<form
					onSubmit={submitScope}
					className="grid gap-2 border-y border-(--color-border-subtle) p-(--density-panel-padding) max-[899px]:grid-cols-1 sm:grid-cols-2 xl:grid-cols-[1fr_9rem_9rem_2fr_auto]"
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
				<div data-info-level="l1" data-info-unit="factor-diagnostics-workspace">
					{scope ? (
						<FactorDiagnosticsView factorId={factorId} scope={scope} />
					) : (
						<p className="p-(--density-panel-padding) text-sm text-(--color-foreground-tertiary)">
							填写 snapshot、window 与 registry hash 后读取不可变诊断制品。
						</p>
					)}
				</div>
			}
		/>
	);
}

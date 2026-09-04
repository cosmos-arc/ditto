import type { SpecValidation } from "@/types/strategy";

interface StrategyStudioLogsProps {
	readonly isDirty: boolean;
	readonly isSaving: boolean;
	readonly isValidating: boolean;
	readonly mutationError: string | null;
	readonly operationNotice: string | null;
	readonly validation: SpecValidation | null;
	readonly validationIsStale: boolean;
}

export function StrategyStudioLogs({
	isDirty,
	isSaving,
	isValidating,
	mutationError,
	operationNotice,
	validation,
	validationIsStale,
}: StrategyStudioLogsProps) {
	const state = isValidating
		? "校验中"
		: isSaving
			? "保存中"
			: validationIsStale
				? "校验已过期"
				: validation?.valid
					? "校验有效"
					: validation
						? "校验未通过"
						: "等待校验";

	return (
		<section
			aria-label="Studio 日志"
			className="h-[132px] border-t border-(--color-border-subtle) bg-(--color-surface-1)"
		>
			<div className="flex h-8 items-center border-b border-(--color-border-subtle) px-3 text-[11px]">
				<span className="border-b-2 border-(--color-accent) px-2 py-2 font-medium text-(--color-foreground)">
					校验结果
				</span>
				<span className="px-2 text-(--color-foreground-tertiary)">Dry Run</span>
				<span className="px-2 text-(--color-foreground-tertiary)">保存记录</span>
				<span className="ml-auto font-data text-(--color-foreground-tertiary)">
					{isDirty ? "working copy 已修改" : "working copy 已同步"}
				</span>
			</div>
			<div className="grid h-[100px] grid-cols-[12rem_minmax(0,1fr)_minmax(16rem,0.8fr)] gap-4 overflow-hidden px-4 py-3 text-xs">
				<div>
					<p className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">状态</p>
					<p className="mt-1 font-medium text-(--color-foreground)">{state}</p>
					{operationNotice && (
						<p role="status" aria-label="Studio 操作结果" className="mt-1 text-(--color-led-success)">
							{operationNotice}
						</p>
					)}
				</div>
				<div className="min-w-0">
					<p className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">Canonical identity</p>
					<p className="mt-1 truncate font-data text-(--color-foreground-secondary)">
						candidate {validation && !validationIsStale ? validation.canonicalHash : "—"}
					</p>
					<p className="mt-1 truncate font-data text-(--color-foreground-tertiary)">
						base {validation?.baseSpecHash ?? "—"}
					</p>
				</div>
				<div className="min-w-0">
					<p className="text-xs uppercase tracking-wide text-(--color-foreground-tertiary)">消息</p>
					{mutationError ? (
						<p role="alert" className="mt-1 text-(--color-led-danger)">
							{mutationError}
						</p>
					) : validation?.errors.length ? (
						<p className="mt-1 truncate text-(--color-led-danger)">{validation.errors.join(" · ")}</p>
					) : (
						<p className="mt-1 text-(--color-foreground-tertiary)">
							保存前必须使用当前 working copy 完成服务端校验；Dry Run 与回测在实验侧固定 PIT 身份。
						</p>
					)}
				</div>
			</div>
		</section>
	);
}

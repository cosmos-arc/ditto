/**
 * WorkspacePlaceholder — "自定义工作区 — 即将推出"
 * Matches prototype .workspace-placeholder: dashed border, icon, title, desc.
 */
export function WorkspacePlaceholder() {
	return (
		<div
			className="mt-2 flex flex-col items-center justify-center rounded-md border border-dashed border-(--color-border) px-3 py-4 text-center"
			data-info-level="l2"
			data-info-unit="workspace-placeholder"
		>
			<div className="mb-1.5 text-(length:--font-size-24) opacity-50">🧩</div>
			<div className="mb-1 text-sm text-(--color-foreground-secondary)">自定义工作区 — 即将推出</div>
			<div className="max-w-[240px] text-sm leading-normal text-(--color-foreground-tertiary)">
				拖拽配置个性化工作区布局，按需组合持仓概览、关注列表、快捷入口等模块
			</div>
		</div>
	);
}

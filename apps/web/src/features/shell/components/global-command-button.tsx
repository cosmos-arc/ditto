interface GlobalCommandButtonProps {
	readonly onOpenCommand?: (() => void) | undefined;
}

export function GlobalCommandButton({ onOpenCommand }: GlobalCommandButtonProps) {
	return (
		<button
			type="button"
			aria-label="打开全局命令"
			aria-disabled={!onOpenCommand}
			aria-description={onOpenCommand ? undefined : "全局命令暂不可用"}
			title={onOpenCommand ? "打开全局命令" : "全局命令暂不可用"}
			data-search-scope="global"
			data-shell-utility="command"
			onClick={onOpenCommand}
			className="flex h-8 items-center gap-[var(--spacing-1)] rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-panel-base)] px-[var(--spacing-2)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)] hover:text-[var(--color-foreground-secondary)]"
		>
			<svg width={14} height={14} viewBox="0 0 20 20" fill="none" aria-hidden="true">
				<circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth={1.5} />
				<path d="M13 13l4 4" stroke="currentColor" strokeWidth={1.5} />
			</svg>
			<span className="hidden text-xs text-[var(--color-foreground-muted)] sm:inline">
				{onOpenCommand ? "命令" : "命令暂不可用"}
			</span>
		</button>
	);
}

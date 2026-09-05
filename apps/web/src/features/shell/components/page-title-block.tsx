interface PageTitleBlockProps {
	readonly title?: string | undefined;
	readonly subtitle?: string | undefined;
}

export function PageTitleBlock({ title, subtitle }: PageTitleBlockProps) {
	if (!title) return null;

	return (
		<div className="relative min-w-0">
			<h1 className="relative truncate whitespace-nowrap text-lg font-semibold text-(--color-foreground) after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:w-2/5 after:rounded-[1px] after:bg-linear-to-r after:from-(--color-accent) after:via-(--color-signature-fg) after:to-transparent">
				{title}
			</h1>
			{subtitle && <p className="mt-1 truncate text-xs text-(--color-foreground-tertiary)">{subtitle}</p>}
		</div>
	);
}

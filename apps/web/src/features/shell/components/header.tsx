import { useMatches } from "@tanstack/react-router";

/**
 * Resolves the page title from route matches.
 * Uses the last match that provides a `handle.title` property,
 * which corresponds to the most specific (deepest) route.
 */
function resolveTitle(matches: readonly { handle?: { title?: string } }[]): string | undefined {
	for (let i = matches.length - 1; i >= 0; i--) {
		const title = matches[i]?.handle?.title;
		if (title) return title;
	}
	return undefined;
}

/**
 * ShellHeader -- 68px global top bar.
 * Shows: dynamic page title (from route handle), spacer, action placeholders.
 */
export function ShellHeader() {
	const matches = useMatches();
	const title = resolveTitle(matches);

	return (
		<header
			className={[
				"flex h-[var(--height-header)] items-center border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] px-[var(--spacing-4)] gap-[var(--spacing-4)]",
				"z-5",
			].join(" ")}
		>
			{/* Page title */}
			{title && (
				<h1 className="whitespace-nowrap text-[var(--text-lg)] font-[var(--font-weight-semibold)] text-[var(--color-foreground)]">
					{title}
				</h1>
			)}

			{/* Spacer pushes actions to the right */}
			<div className="flex-1" />

			{/* Action placeholders */}
			<div className="flex items-center gap-[var(--spacing-2)]">
				<button
					type="button"
					aria-label="搜索"
					className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] hover:bg-[var(--color-surface-1)]"
				>
					<span
						aria-hidden="true"
						className="block h-4 w-4 rounded-sm bg-[var(--color-foreground-tertiary)]"
					/>
				</button>

				<button
					type="button"
					aria-label="通知"
					className="relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] hover:bg-[var(--color-surface-1)]"
				>
					<span
						aria-hidden="true"
						className="block h-4 w-4 rounded-full bg-[var(--color-foreground-tertiary)]"
					/>
				</button>

				<button
					type="button"
					aria-label="用户头像"
					className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-foreground-tertiary)]"
				>
					<span
						aria-hidden="true"
						className="block h-5 w-5 rounded-full bg-[var(--color-surface-0)]"
					/>
				</button>
			</div>
		</header>
	);
}

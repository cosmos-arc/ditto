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
 * Shows: dynamic page title (from route handle), spacer, action controls.
 */
export function ShellHeader() {
	const matches = useMatches();
	const title = resolveTitle(matches);

	return (
		<header
			className={[
				"flex h-[var(--height-header)] items-center border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-app)] px-[var(--spacing-4)] gap-[var(--spacing-4)]",
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

			{/* Action controls */}
			<div className="flex items-center gap-[var(--spacing-2)]">
				{/* Search button */}
				<button
					type="button"
					aria-label="搜索"
					className="flex h-8 items-center gap-[var(--spacing-1)] rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-panel-base)] px-[var(--spacing-2)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)]"
				>
					<svg
						width={14}
						height={14}
						viewBox="0 0 14 14"
						fill="none"
						aria-hidden="true"
					>
						<path
							d="M6 11A5 5 0 1 0 6 1a5 5 0 0 0 0 10ZM10 10l3 3"
							stroke="currentColor"
							strokeWidth={1.5}
							strokeLinecap="round"
						/>
					</svg>
					<kbd className="hidden text-[10px] text-[var(--color-foreground-muted)] sm:inline">
						⌘K
					</kbd>
				</button>

				{/* Notification button */}
				<button
					type="button"
					aria-label="通知"
					className="relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)]"
				>
					<svg
						width={16}
						height={16}
						viewBox="0 0 16 16"
						fill="none"
						aria-hidden="true"
					>
						<path
							d="M8 1.5a4.5 4.5 0 0 0-4.5 4.5v3l-1 2h11l-1-2V6A4.5 4.5 0 0 0 8 1.5Z"
							stroke="currentColor"
							strokeWidth={1.2}
							strokeLinecap="round"
							strokeLinejoin="round"
						/>
						<path
							d="M6.5 13a1.5 1.5 0 0 0 3 0"
							stroke="currentColor"
							strokeWidth={1.2}
							strokeLinecap="round"
						/>
					</svg>
					{/* Unread badge */}
					<span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--color-red-400)]" />
				</button>

				{/* User avatar */}
				<button
					type="button"
					aria-label="用户头像"
					className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-accent)] text-xs font-[var(--font-weight-semibold)] text-[var(--color-accent-fg)]"
				>
					C
				</button>
			</div>
		</header>
	);
}

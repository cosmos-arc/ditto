import { useMatches, useRouter } from "@tanstack/react-router";
import { ThemeSwitcher } from "./theme-switcher";

/**
 * Resolves the page title from route matches.
 * Uses the last match that provides a `handle.title` property,
 * which corresponds to the most specific (deepest) route.
 */
function resolveTitle(matches: readonly { routeId?: string }[]): string | undefined {
	const router = useRouter();
	for (let i = matches.length - 1; i >= 0; i--) {
		const routeId = matches[i]?.routeId;
		if (!routeId) continue;
		// Access route options via router's route tree
		const route = (router as unknown as { routesById?: Record<string, { options?: { handle?: { title?: string } } }> }).routesById?.[routeId]
			?? (router as unknown as { routeTree?: { children?: Array<{ id?: string; options?: { handle?: { title?: string } } }> } }).routeTree?.children?.find(r => r.id === routeId);
		const title = route?.options?.handle?.title;
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
			data-slot="header"
			className={[
				"flex h-[var(--height-header)] items-center border-b border-[var(--color-border-subtle)] bg-(--color-surface-frosted) backdrop-blur-(--blur-frosted) px-[var(--spacing-4)] gap-[var(--spacing-4)]",
				"z-5 relative after:absolute after:bottom-0 after:inset-x-0 after:h-px",
			].join(" ")}
		>
			{/* Page title */}
			{title && (
				<h1 className="relative whitespace-nowrap text-lg font-semibold text-(--color-foreground) after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:w-2/5 after:bg-linear-to-r after:from-(--color-accent) after:via-(--color-signature-fg) after:to-transparent after:rounded-[1px]">
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
						viewBox="0 0 20 20"
						fill="none"
						aria-hidden="true"
					>
						<circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth={1.5} />
						<path d="M13 13l4 4" stroke="currentColor" strokeWidth={1.5} />
					</svg>
					<span className="text-xs text-[var(--color-foreground-muted)] sm:inline">搜索...</span>
					<kbd className="hidden text-xs text-[var(--color-foreground-muted)] sm:inline">
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
						viewBox="0 0 20 20"
						fill="none"
						aria-hidden="true"
					>
						<path
							d="M10 3a5 5 0 00-5 5v4l-2 2h14l-2-2V8a5 5 0 00-5-5z"
							stroke="currentColor"
							strokeWidth={1.5}
							strokeLinecap="round"
							strokeLinejoin="round"
						/>
						<path
							d="M8 16a2 2 0 004 0"
							stroke="currentColor"
							strokeWidth={1.5}
							strokeLinecap="round"
						/>
					</svg>
					{/* Unread badge */}
					<span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--color-red-400)]" />
				</button>

				{/* Help button */}
				<button
					type="button"
					aria-label="Help"
					title="Help"
					className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)]"
				>
					<svg
						width={16}
						height={16}
						viewBox="0 0 20 20"
						fill="none"
						aria-hidden="true"
					>
						<circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth={1.5} />
						<path
							d="M7.5 7.5a2.5 2.5 0 014.5 1.5c0 2-3 2.5-3 4m0 2h.01"
							stroke="currentColor"
							strokeWidth={1.5}
							strokeLinecap="round"
							strokeLinejoin="round"
						/>
					</svg>
				</button>

				{/* Theme & Density switcher */}
				<ThemeSwitcher />

				{/* User avatar */}
				<button
					type="button"
					aria-label="用户头像"
					className="flex h-7 w-7 items-center justify-center rounded-full bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] text-sm font-medium text-(--color-accent)"
				>
					C
				</button>
			</div>
		</header>
	);
}

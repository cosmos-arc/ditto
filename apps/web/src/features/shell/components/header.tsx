import { useMatches, useRouter } from "@tanstack/react-router";
import { HeaderUtilityBar } from "./header-utility-bar";
import { PageTitleBlock } from "./page-title-block";

/**
 * Resolves the page title from route matches.
 * Uses the last match that provides a `staticData.title` property,
 * which corresponds to the most specific (deepest) route.
 */
function resolveTitle(matches: readonly { routeId?: string }[]): string | undefined {
	const router = useRouter();
	for (let i = matches.length - 1; i >= 0; i--) {
		const routeId = matches[i]?.routeId;
		if (!routeId) continue;
		// Access route options via router's route tree
		const route = (router as unknown as { routesById?: Record<string, { options?: { staticData?: { title?: string } } }> }).routesById?.[routeId]
			?? (router as unknown as { routeTree?: { children?: Array<{ id?: string; options?: { staticData?: { title?: string } } }> } }).routeTree?.children?.find(r => r.id === routeId);
		const title = route?.options?.staticData?.title;
		if (title) return title;
	}
	return undefined;
}

interface ShellHeaderProps {
	readonly onOpenCopilot?: () => void;
}

/**
 * ShellHeader -- 68px global top bar.
 * Shows: dynamic page title (from route static data), spacer, action controls.
 */
export function ShellHeader({ onOpenCopilot }: ShellHeaderProps) {
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
			<PageTitleBlock title={title} />

			{/* Spacer pushes actions to the right */}
			<div className="flex-1" />

			<HeaderUtilityBar onOpenCopilot={onOpenCopilot} />
		</header>
	);
}

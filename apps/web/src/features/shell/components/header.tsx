import { useMatches, useRouter } from "@tanstack/react-router";
import { HeaderUtilityBar } from "./header-utility-bar";
import { PageTitleBlock } from "./page-title-block";

/**
 * Resolves the page title from route matches.
 * Uses the last match that provides a `staticData.title` property,
 * which corresponds to the most specific (deepest) route.
 */
interface RouterWithStaticTitles {
	readonly routesById?: Readonly<
		Record<string, { readonly options?: { readonly staticData?: { readonly title?: string } } }>
	>;
	readonly routeTree?: {
		readonly children?: readonly {
			readonly id?: string;
			readonly options?: { readonly staticData?: { readonly title?: string } };
		}[];
	};
}

function resolveTitle(matches: readonly { routeId?: string }[], router: RouterWithStaticTitles): string | undefined {
	for (let i = matches.length - 1; i >= 0; i--) {
		const routeId = matches[i]?.routeId;
		if (!routeId) continue;
		// Access route options via router's route tree
		const route =
			router.routesById?.[routeId] ?? router.routeTree?.children?.find((candidate) => candidate.id === routeId);
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
	const router = useRouter() as unknown as RouterWithStaticTitles;
	const title = resolveTitle(matches, router);

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

import { useMatches, useRouter } from "@tanstack/react-router";
import { DOMAINS, type DomainId } from "@/features/navigation";
import { HeaderUtilityBar } from "./header-utility-bar";
import { PageTitleBlock } from "./page-title-block";
import { SHELL_HEADER_EXTENSION_ID } from "./shell-header-extension";

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
	readonly activeDomain?: DomainId;
	readonly onOpenAgent?: (() => void) | undefined;
}

/**
 * ShellHeader -- 68px global top bar.
 * Shows: dynamic page title (from route static data), spacer, action controls.
 */
export function ShellHeader({ activeDomain = "home", onOpenAgent }: ShellHeaderProps) {
	const matches = useMatches();
	const router = useRouter() as unknown as RouterWithStaticTitles;
	const title = resolveTitle(matches, router);
	const domainLabel = DOMAINS.find((candidate) => candidate.id === activeDomain)?.label ?? "Today";

	return (
		<header
			data-slot="header"
			className={[
				"flex h-[var(--height-header)] items-center border-b border-[var(--color-border-subtle)] bg-(--color-surface-frosted) backdrop-blur-(--blur-frosted) px-[var(--spacing-4)] gap-[var(--spacing-4)]",
				"z-5 relative after:absolute after:bottom-0 after:inset-x-0 after:h-px",
			].join(" ")}
		>
			<span
				data-domain-identity={activeDomain}
				className="shrink-0 rounded-full border border-(--color-border-subtle) bg-(--color-surface-strip) px-2 py-1 text-xs font-semibold tracking-[0.08em] text-(--color-signature-fg) uppercase"
			>
				<span className="sr-only">当前产品域：</span>
				{domainLabel}
			</span>
			<PageTitleBlock title={title} />

			<div id={SHELL_HEADER_EXTENSION_ID} className="flex min-w-0 flex-1 items-center" />

			<HeaderUtilityBar onOpenAgent={onOpenAgent} />
		</header>
	);
}

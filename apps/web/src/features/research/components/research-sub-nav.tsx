import { Link, useLocation } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import type { ResearchSection } from "../sections";
import { RESEARCH_SECTIONS } from "../sections";

/** exact 项精确匹配（总览），其余前缀匹配。 */
function isSectionActive(section: ResearchSection, pathname: string): boolean {
	return section.exact ? pathname === section.path : pathname.startsWith(section.path);
}

/**
 * ResearchSubNav -- research 域顶部水平子导航。
 * 暴露 8 个主干分区入口，复用 Rail 的「active 高亮 + accent 指示条」范式。
 */
export function ResearchSubNav() {
	const { pathname } = useLocation();

	return (
		<nav aria-label="研究子导航" className="flex h-10 items-center gap-1 border-b border-(--color-border-subtle) px-4">
			{RESEARCH_SECTIONS.map((section) => {
				const active = isSectionActive(section, pathname);
				return (
					<Link
						key={section.path}
						to={section.path}
						aria-current={active ? "page" : undefined}
						className={cn(
							"relative rounded-(--radius-md) px-3 py-2 text-sm transition-colors",
							active
								? "text-(--color-accent)"
								: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)",
						)}
					>
						{section.label}
						{active && (
							<span aria-hidden="true" className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-(--color-accent)" />
						)}
					</Link>
				);
			})}
		</nav>
	);
}

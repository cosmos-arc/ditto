import { useLocation, Link } from "@tanstack/react-router";
import { DOMAINS } from "@/features/navigation/types";
import { DomainIcon } from "@/features/navigation/components/domain-icon";
import type { DomainId } from "@/features/navigation/types";

/**
 * Checks if a domain is active based on the current pathname.
 * Home requires exact match ("/"), others use startsWith.
 */
function isDomainActive(domainId: DomainId, pathname: string): boolean {
	const domain = DOMAINS.find((d) => d.id === domainId);
	if (!domain) return false;

	if (domainId === "home") {
		return pathname === "/";
	}
	return pathname.startsWith(domain.path);
}

/**
 * Placeholder icon for settings / user at the rail bottom.
 */
function PlaceholderIcon() {
	return (
		<span
			aria-hidden="true"
			className="block h-5 w-5 rounded-full bg-[var(--color-foreground-tertiary)]"
		/>
	);
}

/**
 * Rail -- 56px left-side icon navigation bar.
 * Contains: Logo, domain navigation icons, settings/user placeholders.
 */
export function Rail() {
	const { pathname } = useLocation();

	return (
		<nav
			aria-label="主导航"
			className="flex w-[var(--width-rail)] flex-col items-center border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] py-[var(--spacing-2)] gap-[var(--spacing-1)]"
		>
			{/* Logo */}
			<span
				aria-hidden="true"
				className="flex h-8 w-8 items-center justify-center text-[var(--text-2xl)] font-bold text-[var(--color-accent)] select-none"
			>
				D
			</span>

			{/* Domain navigation icons */}
			<div className="flex flex-1 flex-col items-center gap-[var(--spacing-1)]">
				{DOMAINS.map((domain) => {
					const active = isDomainActive(domain.id, pathname);

					return (
						<Link
							key={domain.id}
							to={domain.path}
							aria-label={domain.label}
							className={[
								"relative flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors",
								active
									? "bg-[var(--color-brand-50)] text-[var(--color-accent)]"
									: "hover:bg-[var(--color-surface-1)]",
							].join(" ")}
						>
							{active && (
								<span
									aria-hidden="true"
									className="absolute left-0 top-1/2 h-5 -translate-x-2 -translate-y-1/2 w-[3px] rounded-r-sm bg-[var(--color-accent)]"
								/>
							)}
							<DomainIcon domainId={domain.id} />
						</Link>
					);
				})}
			</div>

			{/* Bottom placeholders */}
			<div className="flex flex-col items-center gap-[var(--spacing-1)]">
				<button
					type="button"
					aria-label="设置"
					className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] hover:bg-[var(--color-surface-1)]"
				>
					<PlaceholderIcon />
				</button>
				<button
					type="button"
					aria-label="用户"
					className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] hover:bg-[var(--color-surface-1)]"
				>
					<PlaceholderIcon />
				</button>
			</div>
		</nav>
	);
}

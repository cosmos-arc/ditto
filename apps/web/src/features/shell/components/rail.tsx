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
 * Settings icon for the rail bottom.
 */
function SettingsIcon() {
	return (
		<svg width={18} height={18} viewBox="0 0 18 18" fill="none" aria-hidden="true">
			<path
				d="M7.5 2.25h3l.375 1.5a5.625 5.625 0 0 1 1.5.875L14.25 4.5l1.5 2.625-1.125 1.125a5.625 5.625 0 0 1 0 1.75L15.75 11.125l-1.5 2.625-1.875-.625a5.625 5.625 0 0 1-1.5.875L10.5 15.75h-3l-.375-1.5a5.625 5.625 0 0 1-1.5-.875L3.75 13.875l-1.5-2.625L3.375 10.125a5.625 5.625 0 0 1 0-1.75L2.25 7.125l1.5-2.625 1.875.625a5.625 5.625 0 0 1 1.5-.875L7.5 2.25Z"
				stroke="currentColor"
				strokeWidth={1.2}
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
			<circle cx="9" cy="9" r="2.25" stroke="currentColor" strokeWidth={1.2} />
		</svg>
	);
}

/**
 * User icon for the rail bottom.
 */
function UserIcon() {
	return (
		<svg width={18} height={18} viewBox="0 0 18 18" fill="none" aria-hidden="true">
			<circle cx="9" cy="6.75" r="3" stroke="currentColor" strokeWidth={1.2} />
			<path
				d="M3 15.75c0-3.314 2.686-6 6-6s6 2.686 6 6"
				stroke="currentColor"
				strokeWidth={1.2}
				strokeLinecap="round"
			/>
		</svg>
	);
}

/**
 * Rail -- 56px left-side icon navigation bar.
 * Contains: Logo, domain navigation icons, settings/user icons.
 */
export function Rail() {
	const { pathname } = useLocation();

	return (
		<nav
			aria-label="主导航"
			className="flex w-[var(--width-rail)] flex-col items-center border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-app)] py-[var(--spacing-2)] gap-[var(--spacing-1)]"
		>
			{/* Logo */}
			<span
				aria-hidden="true"
				className="flex h-8 w-8 items-center justify-center text-md font-semibold text-(--color-accent) select-none"
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
								"relative flex h-9 w-9 items-center justify-center rounded-(--radius-md) text-(--color-foreground-tertiary) transition-colors",
								active
									? "bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] text-(--color-accent)"
									: "hover:bg-(--color-interaction-hover-subtle-bg)",
							].join(" ")}
						>
							{active && (
								<span
									aria-hidden="true"
									className="absolute left-0 top-1/2 h-5 -translate-x-2 -translate-y-1/2 w-[3px] rounded-r-sm bg-[var(--color-accent)] shadow-[0_0_6px_var(--color-accent)]"
								/>
							)}
							<DomainIcon domainId={domain.id} />
						</Link>
					);
				})}
			</div>

			{/* Bottom actions */}
			<div className="flex flex-col items-center gap-[var(--spacing-1)]">
				<button
					type="button"
					aria-label="设置"
					className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)]"
				>
					<SettingsIcon />
				</button>
				<button
					type="button"
					aria-label="用户"
					className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)]"
				>
					<UserIcon />
				</button>
			</div>
		</nav>
	);
}

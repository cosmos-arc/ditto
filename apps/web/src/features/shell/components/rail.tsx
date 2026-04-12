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
		<svg
			width={18}
			height={18}
			viewBox="0 0 20 20"
			fill="none"
			stroke="currentColor"
			strokeWidth={1.5}
			aria-hidden="true"
		>
			<circle cx="10" cy="10" r="2.5" />
			<path d="M10 3v2m0 10v2m-7-7h2m10 0h2m-2.5-4.5l-1.4 1.4M6.9 13.1L5.5 14.5m9-9l-1.4 1.4M6.9 6.9L5.5 5.5" />
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
			className="flex h-full w-(--width-rail) flex-col items-center border-r border-(--color-border-subtle) bg-(--color-surface-app) py-2 gap-1"
		>
			{/* Logo */}
			<span
				aria-hidden="true"
				className="flex h-8 w-8 items-center justify-center text-md font-semibold text-(--color-accent) select-none"
			>
				D
			</span>

			{/* Domain navigation icons */}
			<div className="flex flex-1 flex-col items-center gap-1">
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
									className="absolute left-0 top-1/2 h-5 w-0.75 -translate-x-2 -translate-y-1/2 rounded-r-sm bg-(--color-accent) shadow-[0_0_6px_var(--color-accent)]"
								/>
							)}
							<DomainIcon domainId={domain.id} />
						</Link>
					);
				})}
			</div>

			{/* Bottom actions */}
			<div className="flex flex-col items-center gap-1">
				<button
					type="button"
					aria-label="设置"
					className="flex h-9 w-9 items-center justify-center rounded-(--radius-md) text-(--color-foreground-tertiary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					<SettingsIcon />
				</button>
				<button
					type="button"
					aria-label="用户"
					className="flex h-9 w-9 items-center justify-center rounded-(--radius-md) text-(--color-foreground-tertiary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					<UserIcon />
				</button>
			</div>
		</nav>
	);
}

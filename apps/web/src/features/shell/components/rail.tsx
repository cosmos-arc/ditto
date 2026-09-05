import { Link, useLocation } from "@tanstack/react-router";
import { DOMAINS, DomainIcon, type DomainId } from "@/features/navigation";

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
 * Rail -- 56px left-side icon navigation bar.
 * Contains: Logo and top-level domain navigation icons.
 * Right ambient light bar is rendered as the last child (moved from NoiseLayer
 * to match prototype structure).
 */
export function Rail() {
	const { pathname } = useLocation();

	return (
		<nav
			aria-label="主导航"
			className="relative flex h-full w-(--width-rail) flex-col items-center border-r border-(--color-border-subtle) bg-(--color-surface-app) py-2 gap-1"
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
							data-rail-domain={domain.id}
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

			{/* Right ambient light bar -- vertical brand glow along right edge of rail */}
			<div
				aria-hidden="true"
				data-slot="rail-right-light"
				data-testid="rail-right-light"
				className="absolute inset-y-0 -right-px w-px"
			/>
		</nav>
	);
}

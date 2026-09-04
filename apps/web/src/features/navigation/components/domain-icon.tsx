import type { DomainId } from "../types";

/** Outline-style SVG children for each domain icon (viewBox 20x20) */
function iconChildren(domainId: DomainId): React.ReactNode {
	switch (domainId) {
		case "home":
			return <path d="M3 10.5V17a1 1 0 001 1h4v-5h4v5h4a1 1 0 001-1v-6.5L10 3 3 10.5z" />;
		case "markets":
			return (
				<>
					<path d="M3 17l4-4 3 2 7-8" />
					<circle cx="17" cy="7" r="1.5" fill="currentColor" />
				</>
			);
		case "research":
			return (
				<>
					<circle cx="9" cy="9" r="5.5" />
					<path d="M13 13l4 4" />
				</>
			);
		case "portfolio":
			return (
				<>
					<rect x="3" y="6" width="14" height="10" rx="1" />
					<path d="M3 10h14M7 6v10M13 6v10" />
				</>
			);
		case "system":
			return (
				<>
					<rect x="3" y="3" width="6" height="6" rx="1" />
					<rect x="11" y="3" width="6" height="6" rx="1" />
					<rect x="3" y="11" width="6" height="6" rx="1" />
					<rect x="11" y="11" width="6" height="6" rx="1" />
				</>
			);
	}
}

interface DomainIconProps {
	readonly domainId: DomainId;
}

/**
 * Renders an outline-style SVG icon for a given domain.
 * Uses 20x20 viewBox with stroke-based rendering matching the prototype.
 */
export function DomainIcon({ domainId }: DomainIconProps) {
	return (
		<svg
			width={18}
			height={18}
			viewBox="0 0 20 20"
			fill="none"
			stroke="currentColor"
			strokeWidth={1.5}
			xmlns="http://www.w3.org/2000/svg"
			role="img"
			aria-hidden="true"
		>
			{iconChildren(domainId)}
		</svg>
	);
}

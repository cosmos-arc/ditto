import type { DomainId } from "../types";

/** SVG path data for each domain -- simple but distinguishable */
const ICON_PATHS: Record<DomainId, string> = {
	home: "M3 10.5L9.75 4.75L16.5 10.5V18H11.25V13.5H8.25V18H3V10.5Z",
	markets:
		"M3 16L7.5 10L11.25 13.5L16.5 6L18 7.5V18H3V16Z",
	research:
		"M9.75 3C7.4 3 5.25 4.2 4 6C2.75 7.8 2.25 10 2.75 12.2C3.25 14.4 4.75 16.25 6.75 17.3C8.75 18.35 11.1 18.5 13.2 17.7C15.3 16.9 17 15.2 17.75 13.1H15.5C14.85 14.45 13.7 15.5 12.25 16.05C10.8 16.6 9.15 16.5 7.75 15.75C6.35 15 5.35 13.65 4.95 12.1C4.55 10.55 4.9 8.9 5.9 7.6C6.9 6.3 8.4 5.5 9.75 5.5V3Z",
	trading:
		"M4 6H6V18H4V6ZM9 10H11V18H9V10ZM14 3H16V18H14V3Z",
	ai: "M9.75 2.25C6.75 2.25 4 3.75 2.5 6L5 7.5C6 5.75 7.75 4.5 9.75 4.5V2.25ZM9.75 16.5C7.75 16.5 6 15.25 5 13.5L2.5 15C4 17.25 6.75 18.75 9.75 18.75V16.5ZM17 9.75C17 11.5 16.5 13.1 15.5 14.5L13 13C13.75 12 14.25 10.9 14.25 9.75H17ZM9.75 4.5C11.75 4.5 13.5 5.75 14.5 7.5L17 6C15.5 3.75 12.75 2.25 9.75 2.25V4.5ZM14.5 7.5C15.25 8.5 15.75 9.6 15.75 10.75H13.25C13.25 10 13 9.35 12.5 8.75L14.5 7.5Z",
	platform:
		"M3 5.25H16.5V7.5H3V5.25ZM3 10.5H16.5V12.75H3V10.5ZM3 15.75H11.25V18H3V15.75Z",
};

interface DomainIconProps {
	readonly domainId: DomainId;
}

/**
 * Renders an SVG icon for a given domain.
 * Icons are simple but distinguishable silhouettes.
 */
export function DomainIcon({ domainId }: DomainIconProps) {
	return (
		<svg
			width={18}
			height={18}
			viewBox="0 0 18 18"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			role="img"
			aria-hidden="true"
		>
			<path d={ICON_PATHS[domainId]} fill="currentColor" />
		</svg>
	);
}

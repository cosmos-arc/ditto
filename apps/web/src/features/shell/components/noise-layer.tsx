/**
 * NoiseLayer -- decorative overlay providing the Graphite Studio visual atmosphere.
 *
 * Renders three non-interactive layers:
 * 1. SVG feTurbulence noise texture at very low opacity (~0.018)
 * 2. Top ambient light bar (brand-500 gradient fading down)
 * 3. Right ambient light bar (brand-500 gradient fading left)
 */
export function NoiseLayer() {
	return (
		<div
			aria-hidden="true"
			className="pointer-events-none absolute inset-0 z-50"
		>
			{/* Noise texture — SVG feTurbulence filter */}
			<svg
				className="h-full w-full"
				opacity="0.018"
				xmlns="http://www.w3.org/2000/svg"
			>
				<filter id="noise-filter">
					<feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
					<feColorMatrix type="saturate" values="0" />
				</filter>
				<rect width="100%" height="100%" filter="url(#noise-filter)" />
			</svg>

			{/* Top ambient light bar — brand glow from top edge */}
			<div
				data-testid="noise-top-light"
				className="absolute inset-x-0 top-0 h-[1.5px] bg-linear-to-b from-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] to-transparent"
			/>

			{/* Right ambient light bar — brand glow from right edge */}
			<div
				data-testid="noise-right-light"
				className="absolute inset-y-0 right-0 w-px bg-linear-to-l from-[color-mix(in_oklch,var(--color-accent)_18%,transparent)] to-transparent"
			/>
		</div>
	);
}

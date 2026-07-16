/**
 * NoiseLayer -- decorative overlay for Graphite Studio atmosphere.
 *
 * Two non-interactive layers:
 * 1. SVG feTurbulence noise texture (opacity ~0.018)
 * 2. Top ambient light bar (horizontal brand glow along top edge)
 *
 * Note: Right ambient light bar has been moved to the Rail component
 * to match prototype structure where it sits inside the rail nav element.
 */
export function NoiseLayer() {
	return (
		<div aria-hidden="true" data-slot="noise-layer" className="pointer-events-none absolute inset-0 z-0">
			{/* Noise texture -- SVG feTurbulence filter */}
			<svg
				className="h-full w-full"
				opacity="0.018"
				xmlns="http://www.w3.org/2000/svg"
				aria-hidden="true"
				focusable="false"
			>
				<filter id="noise-filter">
					<feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
					<feColorMatrix type="saturate" values="0" />
				</filter>
				<rect width="100%" height="100%" filter="url(#noise-filter)" />
			</svg>

			{/* Top ambient light bar -- horizontal 90deg brand glow along top edge */}
			<div
				data-testid="noise-top-light"
				className="absolute inset-x-0 top-0 h-[1.5px]"
				style={{
					backgroundImage:
						"linear-gradient(90deg, transparent 0%, color-mix(in oklch, var(--color-accent) 10%, transparent) 20%, color-mix(in oklch, var(--color-accent) 18%, transparent) 50%, color-mix(in oklch, var(--color-accent) 10%, transparent) 80%, transparent 100%)",
				}}
			/>
		</div>
	);
}

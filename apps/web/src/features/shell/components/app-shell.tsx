import type { ReactNode } from "react";
import { Rail } from "./rail";
import { ShellHeader } from "./header";
import { NoiseLayer } from "./noise-layer";

interface AppShellProps {
	children: ReactNode;
}

/**
 * AppShell -- global layout container.
 *
 * 2-column grid: Rail (56px) | Content (1fr).
 * Header (68px) spans full width above Content.
 * NoiseLayer overlays as a decorative atmosphere.
 */
export function AppShell({ children }: AppShellProps) {
	return (
		<div
			className={
				"relative grid h-screen w-screen overflow-hidden " +
				"grid-cols-[var(--width-rail)_1fr] " +
				"grid-rows-[var(--height-header)_1fr]"
			}
		>
			<div className="row-span-2">
				<Rail />
			</div>
			<div className="col-start-2">
				<ShellHeader />
			</div>
			<div className="relative col-start-2 row-start-2 min-h-0 overflow-hidden">
				{children}
			</div>
			<NoiseLayer />
		</div>
	);
}

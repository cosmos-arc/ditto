import type { ReactNode } from "react";
import { Rail } from "./rail";
import { ShellHeader } from "./header";
import { NoiseLayer } from "./noise-layer";
import { StatusBar } from "./status-bar";

interface AppShellProps {
	children: ReactNode;
}

/**
 * AppShell -- global layout container.
 *
 * 2-column, 3-row grid: Rail | Content.
 * Header spans full width above Content, StatusBar at bottom.
 * NoiseLayer overlays as a decorative atmosphere.
 */
export function AppShell({ children }: AppShellProps) {
	return (
		<div
			className={
				"relative grid h-screen w-screen overflow-hidden " +
				"grid-cols-[var(--width-rail)_1fr] " +
				"grid-rows-[var(--height-header)_1fr_var(--height-status-bar)]"
			}
		>
			<div className="row-span-3">
				<Rail />
			</div>
			<div className="col-start-2">
				<ShellHeader />
			</div>
			<div className="relative col-start-2 row-start-2 min-h-0 overflow-hidden">
				{children}
			</div>
			<div className="col-start-2 row-start-3">
				<StatusBar />
			</div>
			<NoiseLayer />
		</div>
	);
}

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useActiveDomain } from "../hooks/use-active-domain";
import { useAtmosphere } from "../hooks/use-atmosphere";
import { ShellHeader } from "./header";
import { NoiseLayer } from "./noise-layer";
import { Rail } from "./rail";

interface WorkspaceShellProps {
	readonly children: ReactNode;
	readonly launcher?: (activeDomain: ReturnType<typeof useActiveDomain>) => ReactNode;
	readonly onOpenLauncher?: (() => void) | undefined;
}

export function WorkspaceShell({ children, launcher, onOpenLauncher }: WorkspaceShellProps) {
	const activeDomain = useActiveDomain();
	useAtmosphere();

	useEffect(() => {
		document.documentElement.setAttribute("data-domain", activeDomain);
	}, [activeDomain]);

	return (
		<div
			data-slot="app-shell"
			className={
				"relative grid h-screen w-screen overflow-hidden " +
				"grid-cols-[var(--width-rail)_minmax(0,1fr)] " +
				"grid-rows-[var(--height-header)_1fr]"
			}
		>
			<div className="row-span-2">
				<Rail />
			</div>
			<div className="col-start-2">
				<ShellHeader activeDomain={activeDomain} onOpenAgent={onOpenLauncher} />
			</div>
			<div className="relative col-start-2 row-start-2 min-h-0 overflow-hidden">{children}</div>
			{launcher?.(activeDomain)}
			<NoiseLayer />
		</div>
	);
}

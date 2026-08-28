import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { AgentLauncherSidecar } from "@/features/agent";
import { useActiveDomain } from "../hooks/use-active-domain";
import { useAtmosphere } from "../hooks/use-atmosphere";
import { ShellHeader } from "./header";
import { NoiseLayer } from "./noise-layer";
import { Rail } from "./rail";

interface AppShellProps {
	children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
	const activeDomain = useActiveDomain();
	const [isAgentLauncherOpen, setIsAgentLauncherOpen] = useState(false);
	useAtmosphere();

	useEffect(() => {
		document.documentElement.setAttribute("data-domain", activeDomain);
	}, [activeDomain]);

	return (
		<div
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
				<ShellHeader onOpenAgent={() => setIsAgentLauncherOpen(true)} />
			</div>
			<div className="relative col-start-2 row-start-2 min-h-0 overflow-hidden">{children}</div>
			<AgentLauncherSidecar open={isAgentLauncherOpen} onOpenChange={setIsAgentLauncherOpen} />
			<NoiseLayer />
		</div>
	);
}

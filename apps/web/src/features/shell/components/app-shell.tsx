import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { CopilotSidecar } from "@/features/copilot";
import { Rail } from "./rail";
import { ShellHeader } from "./header";
import { NoiseLayer } from "./noise-layer";
import { useActiveDomain } from "../hooks/use-active-domain";
import { useAtmosphere } from "../hooks/use-atmosphere";

interface AppShellProps {
	children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
	const activeDomain = useActiveDomain();
	const [isCopilotOpen, setIsCopilotOpen] = useState(false);
	useAtmosphere();

	useEffect(() => {
		document.documentElement.setAttribute("data-domain", activeDomain);
	}, [activeDomain]);

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
				<ShellHeader onOpenCopilot={() => setIsCopilotOpen(true)} />
			</div>
			<div className="relative col-start-2 row-start-2 min-h-0 overflow-hidden">
				{children}
			</div>
			<CopilotSidecar open={isCopilotOpen} onOpenChange={setIsCopilotOpen} />
			<NoiseLayer />
		</div>
	);
}

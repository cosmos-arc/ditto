import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

interface OverlayController {
	readonly activeOverlayId: string | null;
	readonly openOverlay: (overlayId: string) => void;
	readonly closeOverlay: () => void;
}

const OverlayContext = createContext<OverlayController | null>(null);

interface OverlayProviderProps {
	readonly children: ReactNode;
}

export function OverlayProvider({ children }: OverlayProviderProps) {
	const [activeOverlayId, setActiveOverlayId] = useState<string | null>(null);

	const controller = useMemo<OverlayController>(
		() => ({
			activeOverlayId,
			openOverlay: setActiveOverlayId,
			closeOverlay: () => setActiveOverlayId(null),
		}),
		[activeOverlayId],
	);

	return (
		<OverlayContext.Provider value={controller}>
			{children}
		</OverlayContext.Provider>
	);
}

export function useOverlayController(): OverlayController {
	const controller = useContext(OverlayContext);
	if (!controller) {
		throw new Error("useOverlayController must be used inside OverlayProvider");
	}
	return controller;
}

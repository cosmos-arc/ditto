import { useCallback, useEffect, useState } from "react";

type Density = "compact" | "comfortable" | "ultra-compact";

const STORAGE_KEY = "ditto-density";

const DENSITY_CYCLE: Density[] = ["compact", "comfortable", "ultra-compact"];

function getInitialDensity(): Density {
	const stored = localStorage.getItem(STORAGE_KEY);
	if (stored === "compact" || stored === "comfortable" || stored === "ultra-compact") {
		return stored;
	}
	return "compact";
}

export function useDensity() {
	const [density, setDensityState] = useState<Density>(getInitialDensity);

	const applyDensity = useCallback((d: Density) => {
		document.documentElement.setAttribute("data-grid-density", d);
		localStorage.setItem(STORAGE_KEY, d);
	}, []);

	const setDensity = useCallback(
		(d: Density) => {
			setDensityState(d);
			applyDensity(d);
		},
		[applyDensity],
	);

	const cycleDensity = useCallback(() => {
		const current = DENSITY_CYCLE.indexOf(density);
		const next = DENSITY_CYCLE[(current + 1) % DENSITY_CYCLE.length];
		setDensity(next);
	}, [density, setDensity]);

	useEffect(() => {
		applyDensity(density);
	}, [density, applyDensity]);

	return { density, setDensity, cycleDensity } as const;
}

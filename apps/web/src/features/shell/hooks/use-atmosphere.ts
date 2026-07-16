import { useEffect } from "react";

type MarketPhase = "pre-market" | "active" | "post-market" | "closed";

const PHASE_PROFILES = {
	"pre-market": { hueShift: 5, chromaBoost: 0.001, lightnessShift: 0.002 },
	active: { hueShift: 0, chromaBoost: 0, lightnessShift: 0 },
	"post-market": { hueShift: -3, chromaBoost: -0.001, lightnessShift: -0.001 },
	closed: { hueShift: -5, chromaBoost: -0.0015, lightnessShift: -0.002 },
} as const;

function getMarketPhase(): MarketPhase {
	const hour = new Date().getHours();
	if (hour >= 9 && hour < 15) return "active";
	if (hour >= 8 && hour < 9) return "pre-market";
	if (hour >= 15 && hour < 16) return "post-market";
	return "closed";
}

export function useAtmosphere(): void {
	useEffect(() => {
		function update() {
			const phase = getMarketPhase();
			const config = PHASE_PROFILES[phase];
			const root = document.documentElement.style;
			root.setProperty("--atmosphere-hue-shift", String(config.hueShift));
			root.setProperty(
				"--atmosphere-chroma-boost",
				String(config.chromaBoost),
			);
			root.setProperty(
				"--atmosphere-lightness-shift",
				String(config.lightnessShift),
			);
		}
		update();
		const interval = setInterval(update, 300_000);
		return () => clearInterval(interval);
	}, []);
}

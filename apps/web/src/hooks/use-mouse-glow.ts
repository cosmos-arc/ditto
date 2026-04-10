import { useCallback, useRef } from "react";

const GLOW_X = "--_glow-x" as const;
const GLOW_Y = "--_glow-y" as const;

type MouseGlowReturn = readonly [
	ref: React.RefObject<HTMLElement | null>,
	handlers: {
		onMouseMove: (e: React.MouseEvent<HTMLElement>) => void;
		onMouseLeave: () => void;
	},
];

export function useMouseGlow(): MouseGlowReturn {
	const ref = useRef<HTMLElement | null>(null);

	const onMouseMove = useCallback((e: React.MouseEvent<HTMLElement>) => {
		const el = e.currentTarget;
		const rect = el.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;

		el.style.setProperty(GLOW_X, `${x}px`);
		el.style.setProperty(GLOW_Y, `${y}px`);
	}, []);

	const onMouseLeave = useCallback(() => {
		const el = ref.current;
		if (!el) return;

		el.style.setProperty(GLOW_X, "");
		el.style.setProperty(GLOW_Y, "");
	}, []);

	return [ref, { onMouseMove, onMouseLeave }] as const;
}

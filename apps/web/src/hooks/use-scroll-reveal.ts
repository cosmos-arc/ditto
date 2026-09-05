import { useCallback, useEffect, useRef, useState } from "react";

/* ── Options ── */

interface ScrollRevealOptions {
	/** Intersection ratio threshold (default 0.1) */
	readonly threshold?: number;
	/** Root margin for IntersectionObserver (default "0px") */
	readonly rootMargin?: string;
	/** Disconnect observer after first reveal (default true) */
	readonly once?: boolean;
}

/* ── Return type ── */

interface ScrollRevealReturn {
	/** Callback ref — attach to the element to observe */
	readonly ref: React.RefCallback<HTMLElement>;
	/** Whether the element is currently visible in the viewport */
	readonly isVisible: boolean;
}

/* ── Defaults ── */

const DEFAULTS = {
	threshold: 0.1,
	rootMargin: "0px",
	once: true,
} as const satisfies Required<ScrollRevealOptions>;

/* ── Hook ── */

export function useScrollReveal(options?: ScrollRevealOptions): ScrollRevealReturn {
	const { threshold, rootMargin, once } = { ...DEFAULTS, ...options };

	const [isVisible, setIsVisible] = useState(false);
	const observerRef = useRef<IntersectionObserver | null>(null);

	const ref = useCallback(
		(element: HTMLElement | null) => {
			// Disconnect previous observer if it exists
			observerRef.current?.disconnect();
			observerRef.current = null;

			if (!element) return;

			const observer = new IntersectionObserver(
				([entry]) => {
					if (!entry) return;
					const visible = entry.isIntersecting;
					setIsVisible(visible);

					if (visible && once) {
						observer.disconnect();
						observerRef.current = null;
					}
				},
				{ threshold, rootMargin },
			);

			observer.observe(element);
			observerRef.current = observer;
		},
		[threshold, rootMargin, once],
	);

	useEffect(() => {
		return () => {
			observerRef.current?.disconnect();
		};
	}, []);

	return { ref, isVisible };
}

export type { ScrollRevealOptions, ScrollRevealReturn };

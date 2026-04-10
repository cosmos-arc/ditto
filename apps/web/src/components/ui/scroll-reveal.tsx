import type { ReactNode } from "react";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

/* ── Types ── */

interface ScrollRevealProps {
	readonly children: ReactNode;
	readonly className?: string;
	/** Stagger delay tier: 0 = none, 1 = 60ms, 2 = 120ms */
	readonly stagger?: number;
}

/* ── Component ── */

/**
 * ScrollReveal — wrapper that applies a reveal-up entrance animation
 * when the element scrolls into the viewport via IntersectionObserver.
 */
export function ScrollReveal({ children, className, stagger = 0 }: ScrollRevealProps) {
	const { ref, isVisible } = useScrollReveal();

	return (
		<div
			ref={ref}
			className={[
				"reveal-up",
				isVisible && "is-visible",
				stagger === 1 && "stagger-1",
				stagger === 2 && "stagger-2",
				className,
			]
				.filter(Boolean)
				.join(" ")}
		>
			{children}
		</div>
	);
}

export type { ScrollRevealProps };

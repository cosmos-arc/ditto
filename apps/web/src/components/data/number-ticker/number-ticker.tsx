import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/* ── Easing: ease-out cubic ── */

function easeOutCubic(t: number): number {
	return 1 - (1 - t) ** 3;
}

/* ── Number formatting (cached formatter per decimal count) ── */

const formatterCache = new Map<number, Intl.NumberFormat>();

function getFormatter(decimals: number): Intl.NumberFormat {
	let fmt = formatterCache.get(decimals);
	if (!fmt) {
		fmt = new Intl.NumberFormat("en-US", {
			minimumFractionDigits: decimals,
			maximumFractionDigits: decimals,
		});
		formatterCache.set(decimals, fmt);
	}
	return fmt;
}

function formatNumber(value: number, decimals: number): string {
	return getFormatter(decimals).format(value);
}

/* ── Props ── */

interface NumberTickerProps extends React.HTMLAttributes<HTMLSpanElement> {
	readonly value: string | number;
	readonly decimals?: number;
	readonly prefix?: string;
	readonly suffix?: string;
	readonly duration?: number;
}

/* ── Component ── */

function NumberTicker({
	value,
	decimals = 2,
	prefix = "",
	suffix = "",
	duration = 1200,
	className,
	...props
}: NumberTickerProps) {
	const targetValue = typeof value === "string" ? Number.parseFloat(value) : value;
	const [displayValue, setDisplayValue] = useState(0);
	const rafRef = useRef<number>(0);
	const spanRef = useRef<HTMLSpanElement>(null);

	const animate = useCallback(
		(startTime: number) => {
			const step = (currentTime: number) => {
				const elapsed = currentTime - startTime;
				const progress = Math.min(elapsed / duration, 1);
				const eased = easeOutCubic(progress);
				setDisplayValue(eased * targetValue);

				if (progress < 1) {
					rafRef.current = requestAnimationFrame(step);
				}
			};
			rafRef.current = requestAnimationFrame(step);
		},
		[targetValue, duration],
	);

	useEffect(() => {
		const element = spanRef.current;
		if (!element) return;

		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0]?.isIntersecting) {
					const startTime = performance.now();
					animate(startTime);
					observer.disconnect();
				}
			},
			{ threshold: 0.1 },
		);

		observer.observe(element);

		return () => {
			observer.disconnect();
			cancelAnimationFrame(rafRef.current);
		};
	}, [animate]);

	const formatted = formatNumber(displayValue, decimals);

	return (
		<span
			ref={spanRef}
			data-slot="number-ticker"
			data-testid="number-ticker-root"
			className={cn("font-data tabular-nums", className)}
			{...props}
		>
			{prefix}
			{formatted}
			{suffix}
		</span>
	);
}

export { NumberTicker };
export type { NumberTickerProps };

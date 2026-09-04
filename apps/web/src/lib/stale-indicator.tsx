import { cn } from "@/lib/utils";

interface StaleIndicatorProps {
	readonly isStale: boolean;
	readonly className?: string;
}

function StaleIndicator({ isStale, className }: StaleIndicatorProps) {
	return (
		<div
			data-slot="stale-indicator"
			data-testid="stale-indicator"
			role="presentation"
			className={cn(
				"w-full overflow-hidden transition-all duration-200",
				isStale ? "h-[2px] opacity-100" : "h-0 opacity-0",
				"bg-(--color-accent)/60",
				className,
			)}
		/>
	);
}

export { StaleIndicator };

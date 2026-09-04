import { cn } from "@/lib/utils";

/* ── Types ── */

type ItemColor = "default" | "up" | "down" | "muted";

interface ContextBarProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly frosted?: boolean;
	readonly children: React.ReactNode;
}

interface ContextBarItemProps extends React.HTMLAttributes<HTMLSpanElement> {
	readonly label: string;
	readonly value: string | number;
	readonly color?: ItemColor;
}

/* ── Color mapping ── */

const VALUE_COLOR_CLASSES: Record<ItemColor, string> = {
	default: "text-(--color-foreground)",
	up: "text-(--color-market-up)",
	down: "text-(--color-market-down)",
	muted: "text-(--color-foreground-tertiary)",
};

/* ── ContextBar ── */

function ContextBar({ frosted = false, children, className, ...props }: ContextBarProps) {
	return (
		<div
			data-slot="context-bar"
			className={cn(
				"flex items-center gap-3 h-[var(--height-context-bar)] px-[var(--spacing-4)]",
				frosted
					? "bg-(--color-surface-frosted) backdrop-blur-[var(--blur-frosted)]"
					: "bg-(--color-surface-strip) border-b border-(--color-border-subtle)",
				className,
			)}
			{...props}
		>
			{children}
		</div>
	);
}

/* ── ContextBarItem ── */

function ContextBarItem({ label, value, color = "default", className, ...props }: ContextBarItemProps) {
	return (
		<span data-slot="context-bar-item" className={cn("flex flex-col", className)} {...props}>
			<span className="text-xs uppercase text-(--color-foreground-tertiary) tracking-wide">{label}</span>
			<span className={cn("font-data text-sm font-medium tabular-nums", VALUE_COLOR_CLASSES[color])}>{value}</span>
		</span>
	);
}

/* ── ContextBarSep ── */

function ContextBarSep() {
	return <span aria-hidden="true" className="w-px h-4 bg-(--color-border)" />;
}

export type { ContextBarItemProps, ContextBarProps, ItemColor };
export { ContextBar, ContextBarItem, ContextBarSep };

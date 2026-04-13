import type { ReactNode, HTMLAttributes } from "react";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

/* ------------------------------------------------------------------ */
/*  Panel -- flex-col container with surface background & border      */
/* ------------------------------------------------------------------ */

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
	children: ReactNode;
}

/**
 * Panel -- shell layout building block.
 * Renders a flex-column container with surface-panel-base background,
 * subtle border, and rounded corners.
 */
export function Panel({ className, children, ...rest }: PanelProps) {
	return (
		<div
			data-slot="panel"
			className={[
				"flex min-h-0 flex-col overflow-hidden rounded-(--radius-md)",
				"border border-(--color-border-subtle)",
				"bg-(--color-surface-panel-base)",
				"transition-shadow duration-200",
				"hover:shadow-[0_0_0_1px_color-mix(in_oklch,var(--color-accent)_6%,transparent),0_1px_3px_color-mix(in_oklch,var(--color-accent)_3%,transparent)]",
				className,
			].join(" ")}
			{...rest}
		>
			{children}
		</div>
	);
}

/* ------------------------------------------------------------------ */
/*  PanelHeader -- title row with optional count, subtitle & actions  */
/* ------------------------------------------------------------------ */

interface PanelHeaderProps {
	title: string;
	subtitle?: string;
	count?: number;
	actions?: ReactNode;
}

/**
 * PanelHeader -- horizontal header bar with title area (flex:1)
 * and an optional actions slot aligned to the right.
 * Title uses text-primary per prototype panel-title spec.
 */
export function PanelHeader({ title, subtitle, count, actions }: PanelHeaderProps) {
	return (
		<div
			className={[
				"flex shrink-0 items-center",
				"border-b border-(--color-border-subtle)",
				"px-3 py-2",
			].join(" ")}
		>
			<span className="flex min-w-0 flex-1 items-baseline gap-2 text-sm font-medium text-(--color-foreground)">
				{title}
				{subtitle && (
					<span
						data-testid="panel-subtitle"
						className="font-normal text-(--color-foreground-tertiary)"
					>
						{subtitle}
					</span>
				)}
				{count !== undefined && (
					<span
						data-testid="panel-count"
						className="flex h-4.5 items-center rounded-[4px] bg-(--color-surface-strip) px-2 font-data text-sm tabular-nums tracking-[-0.24px] text-(--color-foreground-tertiary)"
					>
						{count}
					</span>
				)}
			</span>

			{actions && (
				<div
					data-testid="panel-actions"
					className="ml-2 flex items-center gap-1"
				>
					{actions}
				</div>
			)}
		</div>
	);
}

/* ------------------------------------------------------------------ */
/*  PanelBody -- scrollable content area                              */
/* ------------------------------------------------------------------ */

interface PanelBodyProps extends HTMLAttributes<HTMLDivElement> {
	children: ReactNode;
}

/**
 * PanelBody -- flex-1 content region with overflow-y scroll.
 * Applies scroll-reveal entrance animation to content.
 */
export function PanelBody({ className, children, ...rest }: PanelBodyProps) {
	const { ref, isVisible } = useScrollReveal();

	return (
		<div
			ref={ref}
			className={[
				"flex-1 overflow-y-auto overflow-x-hidden",
				"reveal-up",
				isVisible && "is-visible",
				className,
			]
				.filter(Boolean)
				.join(" ")}
			{...rest}
		>
			{children}
		</div>
	);
}

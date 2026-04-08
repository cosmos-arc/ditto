import type { ReactNode, HTMLAttributes } from "react";

/* ------------------------------------------------------------------ */
/*  Panel -- flex-col container with surface background & border      */
/* ------------------------------------------------------------------ */

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
	children: ReactNode;
}

/**
 * Panel -- shell layout building block.
 * Renders a flex-column container with surface-1 background,
 * subtle border, and rounded corners.
 *
 * Accepts `className` for grid-area placement or additional styling.
 */
export function Panel({ className, children, ...rest }: PanelProps) {
	return (
		<div
			className={[
				"flex min-h-0 flex-col overflow-hidden rounded-[var(--radius-md)]",
				"border border-[var(--color-border-subtle)]",
				"bg-[var(--color-surface-1)]",
				className,
			].join(" ")}
			{...rest}
		>
			{children}
		</div>
	);
}

/* ------------------------------------------------------------------ */
/*  PanelHeader -- title row with optional subtitle & actions slot    */
/* ------------------------------------------------------------------ */

interface PanelHeaderProps {
	title: string;
	subtitle?: string;
	actions?: ReactNode;
}

/**
 * PanelHeader -- horizontal header bar with title area (flex:1)
 * and an optional actions slot aligned to the right.
 * Separated from body by a subtle bottom border.
 */
export function PanelHeader({ title, subtitle, actions }: PanelHeaderProps) {
	return (
		<div
			className={[
				"flex shrink-0 items-center",
				"border-b border-[var(--color-border-subtle)]",
				"px-[var(--spacing-3)] py-[var(--spacing-2)]",
			].join(" ")}
		>
			{/* Title area */}
			<div className="flex min-w-0 flex-1 flex-col gap-[var(--spacing-0-5)]">
				<span className="text-[var(--text-sm)] font-[var(--font-weight-medium)] text-[var(--color-foreground)]">
					{title}
				</span>
				{subtitle && (
					<span
						data-testid="panel-subtitle"
						className="text-[var(--text-sm)] text-[var(--color-foreground-secondary)]"
					>
						{subtitle}
					</span>
				)}
			</div>

			{/* Actions slot */}
			{actions && (
				<div
					data-testid="panel-actions"
					className="ml-[var(--spacing-2)] flex items-center gap-[var(--spacing-1)]"
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
 * Fills remaining vertical space within a Panel.
 */
export function PanelBody({ className, children, ...rest }: PanelBodyProps) {
	return (
		<div
			className={[
				"flex-1 overflow-y-auto overflow-x-hidden",
				className,
			].join(" ")}
			{...rest}
		>
			{children}
		</div>
	);
}

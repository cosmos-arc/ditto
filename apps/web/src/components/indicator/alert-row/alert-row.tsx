import { cn } from "@/lib/utils";
import { StatusDot } from "@/components/status";

const SEVERITY_DOT_MAP = {
	critical: "critical" as const,
	warning: "degraded" as const,
	info: "info" as const,
};

interface AlertRowProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly severity: "critical" | "warning" | "info";
	readonly title: string;
	readonly time?: string;
	readonly onClick?: () => void;
}

function AlertRow({
	severity,
	title,
	time,
	onClick,
	className,
	...props
}: AlertRowProps) {
	const dotVariant = SEVERITY_DOT_MAP[severity];

	return (
		<div
			data-slot="alert-row"
			data-severity={severity}
			data-testid="alert-row"
			className={cn(
				"flex items-center gap-[var(--space-8)] border-b border-(--color-border-subtle) last:border-b-0 py-[var(--density-cell-padding-y)] px-[var(--space-12)] transition-colors duration-120 hover:bg-(--color-surface-2)",
				onClick && "cursor-pointer",
				className,
			)}
			onClick={onClick}
			onKeyDown={onClick ? (e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					onClick();
				}
			} : undefined}
			role={onClick ? "button" : undefined}
			tabIndex={onClick ? 0 : undefined}
			{...props}
		>
			<StatusDot
				variant={dotVariant}
				className={severity === "critical" ? "animate-[dot-critical-pulse_2s_ease-in-out_infinite]" : undefined}
			/>

			<span className="min-w-0 flex-1 truncate text-[var(--font-size-12)] text-(--color-foreground-primary)">
				{title}
			</span>

			{time && (
				<span className="shrink-0 tabular-nums text-[var(--font-size-12)] text-(--color-foreground-tertiary)">
					{time}
				</span>
			)}
		</div>
	);
}

export { AlertRow };
export type { AlertRowProps };

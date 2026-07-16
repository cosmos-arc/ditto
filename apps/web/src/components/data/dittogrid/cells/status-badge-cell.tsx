import { StatusBadge, type BadgeVariant } from "@/components/status/status-badge";
import { cn } from "@/lib/utils";

interface StatusBadgeCellProps {
	readonly label: string;
	readonly variant?: BadgeVariant;
	readonly size?: "sm" | "md";
	readonly className?: string;
}

function StatusBadgeCell({
	label,
	variant = "default",
	size = "sm",
	className,
}: StatusBadgeCellProps) {
	return (
		<span
			data-slot="status-badge-cell"
			data-testid="status-badge-cell-root"
			className={cn("flex items-center", className)}
		>
			<StatusBadge variant={variant} label={label} size={size} />
		</span>
	);
}

export { StatusBadgeCell };
export type { StatusBadgeCellProps };

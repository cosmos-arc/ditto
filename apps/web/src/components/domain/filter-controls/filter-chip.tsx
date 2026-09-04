import { cn } from "@/lib/utils";

interface FilterChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
	readonly label: string;
	readonly active?: boolean;
	readonly count?: number;
}

function FilterChip({ label, active = false, count, className, ...props }: FilterChipProps) {
	return (
		<button
			data-slot="filter-chip"
			data-active={active}
			type="button"
			className={cn(
				"inline-flex items-center gap-1.5 text-sm py-2 px-2 rounded-(--radius-4) border transition-colors duration-120",
				active
					? "border-(--color-brand-accent) bg-(--color-brand-accent) text-white"
					: "border-(--color-border-subtle) bg-transparent text-(--color-foreground-secondary) hover:border-(--color-border-default) hover:bg-(--color-interaction-hover-subtle-bg)",
				className,
			)}
			{...props}
		>
			{label}
			{count !== undefined && <span className="text-xs tabular-nums">{count}</span>}
		</button>
	);
}

export type { FilterChipProps };
export { FilterChip };

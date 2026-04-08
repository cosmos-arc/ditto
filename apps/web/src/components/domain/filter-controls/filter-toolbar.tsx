import { cn } from "@/lib/utils";

interface FilterToolbarProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly children: React.ReactNode;
}

function FilterToolbar({
	children,
	className,
	...props
}: FilterToolbarProps) {
	return (
		<div
			data-slot="filter-toolbar"
			className={cn(
				"flex items-center gap-[var(--space-6)] bg-(--color-surface-1) border-b border-(--color-border-subtle) px-[var(--space-12)]",
				className,
			)}
			{...props}
		>
			{children}
		</div>
	);
}

export { FilterToolbar };
export type { FilterToolbarProps };

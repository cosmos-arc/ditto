import { cn } from "@/lib/utils";

interface ScopeStripProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly children: React.ReactNode;
}

function ScopeStrip({ children, role = "status", className, ...props }: ScopeStripProps) {
	return (
		<div
			data-slot="scope-strip"
			role={role}
			className={cn(
				"flex items-center gap-(--space-12) overflow-x-auto border-b border-(--color-border-subtle) bg-(--color-surface-1) px-(--density-gutter) h-(--density-strip-height)",
				className,
			)}
			{...props}
		>
			{children}
		</div>
	);
}

export type { ScopeStripProps };
export { ScopeStrip };

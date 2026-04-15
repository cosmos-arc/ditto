import { cn } from "@/lib/utils";
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";

interface DrawerProps {
	readonly open: boolean;
	readonly onClose: () => void;
	readonly title: string;
	readonly children: React.ReactNode;
	readonly className?: string;
}

function Drawer({
	open,
	onClose,
	title,
	children,
	className,
}: DrawerProps) {
	return (
		<Sheet open={open} onOpenChange={(isOpen) => {
				if (!isOpen) onClose();
			}}>
				<SheetContent
					side="right"
					showClose
					aria-label={title}
					aria-describedby={undefined}
					className={cn("w-[340px] max-w-[340px] p-0", className)}
				>
					<SheetHeader className="flex-row items-center justify-between border-b border-(--color-border-subtle) px-4 py-3 mb-3 space-y-0">
						<SheetTitle className="text-md text-(--color-foreground-primary)">
							{title}
						</SheetTitle>
					</SheetHeader>

					<div
						data-slot="drawer-body"
						className="flex-1 overflow-y-auto px-4 text-sm text-(--color-foreground-secondary) leading-relaxed"
					>
						{children}
					</div>
				</SheetContent>
			</Sheet>
	);
}

export { Drawer };
export type { DrawerProps };

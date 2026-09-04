import { type ReactNode, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";

export type PageActionOverlayKind = "drawer" | "sheet" | "modal" | "alert-dialog" | "toast" | "inline";

export interface PageActionDefinition<Id extends string> {
	readonly id: Id;
	readonly label: string;
}

interface PageActionBarProps<Id extends string> {
	readonly actions: readonly PageActionDefinition<Id>[];
	readonly ariaLabel: string;
	readonly onOpen: (id: Id) => void;
}

export function PageActionBar<Id extends string>({ actions, ariaLabel, onOpen }: PageActionBarProps<Id>) {
	return (
		<div aria-label={ariaLabel} className="flex max-w-full items-center gap-1.5 overflow-x-auto" role="toolbar">
			{actions.map((action) => (
				<Button
					key={action.id}
					type="button"
					variant="outline"
					size="xs"
					className="shrink-0"
					onClick={() => onOpen(action.id)}
				>
					{action.label}
				</Button>
			))}
		</div>
	);
}

interface PageActionOverlayProps {
	readonly actions?: ReactNode;
	readonly children?: ReactNode;
	readonly description: string;
	readonly kind: PageActionOverlayKind;
	readonly onClose: () => void;
	readonly open: boolean;
	readonly title: string;
}

function OverlayBody({ children }: { readonly children?: ReactNode }) {
	return (
		<div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-5 text-sm text-(--color-foreground-secondary)">
			{children}
		</div>
	);
}

export function PageActionOverlay({
	actions,
	children,
	description,
	kind,
	onClose,
	open,
	title,
}: PageActionOverlayProps) {
	const returnFocusRef = useRef<HTMLElement | null>(null);

	useEffect(() => {
		if (!open) return;
		returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		return () => {
			const target = returnFocusRef.current;
			returnFocusRef.current = null;
			if (target?.isConnected) target.focus();
		};
	}, [open]);

	if (!open) return null;

	if (kind === "toast" || kind === "inline") {
		return (
			<div
				aria-label={title}
				className="fixed right-4 bottom-[calc(var(--height-status-bar)+1rem)] z-50 w-[min(24rem,calc(100vw-2rem))] rounded-(--radius-md) border border-(--color-border-strong) bg-(--color-surface-3) p-4 shadow-lg"
				role="status"
			>
				<div className="flex items-start justify-between gap-3">
					<div>
						<p className="font-medium text-(--color-foreground)">{title}</p>
						<p className="mt-1 text-xs leading-5 text-(--color-foreground-secondary)">{description}</p>
					</div>
					<Button type="button" variant="ghost" size="xs" aria-label={`关闭${title}`} onClick={onClose}>
						关闭
					</Button>
				</div>
				{children && <div className="mt-3">{children}</div>}
			</div>
		);
	}

	if (kind === "drawer") {
		return (
			<Sheet open onOpenChange={(isOpen) => !isOpen && onClose()}>
				<SheetContent side="right" aria-label={title} className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>{title}</SheetTitle>
						<SheetDescription>{description}</SheetDescription>
					</SheetHeader>
					<OverlayBody>{children}</OverlayBody>
					{actions && <SheetFooter className="border-t border-(--color-border-subtle) p-4">{actions}</SheetFooter>}
				</SheetContent>
			</Sheet>
		);
	}

	return (
		<Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
			<DialogContent
				aria-label={title}
				className="max-h-[min(88vh,760px)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden p-0"
			>
				<DialogHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<DialogTitle>{title}</DialogTitle>
					<DialogDescription>{description}</DialogDescription>
				</DialogHeader>
				<OverlayBody>{children}</OverlayBody>
				{actions && <DialogFooter className="border-t border-(--color-border-subtle) p-4">{actions}</DialogFooter>}
			</DialogContent>
		</Dialog>
	);
}

export function OverlayFactList({ facts }: { readonly facts: readonly (readonly [string, ReactNode])[] }) {
	return (
		<dl className="divide-y divide-(--color-border-subtle) rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)">
			{facts.map(([label, value]) => (
				<div key={label} className="grid grid-cols-[minmax(7rem,0.8fr)_minmax(0,1.2fr)] gap-3 px-3 py-2.5">
					<dt className="text-xs text-(--color-foreground-tertiary)">{label}</dt>
					<dd className="break-words text-right font-data text-xs text-(--color-foreground)">{value}</dd>
				</div>
			))}
		</dl>
	);
}

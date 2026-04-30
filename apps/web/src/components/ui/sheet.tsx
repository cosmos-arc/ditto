"use client";

import { Dialog as DialogPrimitive } from "radix-ui";
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const sheetVariants = cva(
	"fixed z-50 gap-4 border border-(--color-border-subtle) bg-(--color-surface-3) shadow-lg transition ease-in-out",
	{
		variants: {
			side: {
				top: "inset-x-0 top-0 border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
				bottom:
					"inset-x-0 bottom-0 border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
				left: "inset-y-0 left-0 h-full w-(--width-drawer) max-w-(--width-drawer) border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
				right:
					"inset-y-0 right-0 h-full w-(--width-drawer) max-w-(--width-drawer) border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
			},
		},
		defaultVariants: {
			side: "right",
		},
	},
);

function Sheet({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
	return <DialogPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetTrigger({
	...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
	return <DialogPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function CloseIcon() {
	return (
		<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
			<path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
		</svg>
	);
}

function SheetClose({
	className,
	children,
	"aria-label": ariaLabel = "Close",
	...props
}: React.ComponentProps<typeof DialogPrimitive.Close>) {
	return (
		<DialogPrimitive.Close
			data-slot="sheet-close"
			aria-label={ariaLabel}
			className={cn(
				"absolute top-4 right-4 flex h-8 w-8 items-center justify-center rounded-(--radius-md)",
				"text-(--color-foreground-tertiary) transition-colors",
				"hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)",
				"focus:outline-none focus:ring-2 focus:ring-(--color-focus-ring)",
				className,
			)}
			{...props}
		>
			{children ?? <CloseIcon />}
		</DialogPrimitive.Close>
	);
}

function SheetPortal({
	...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
	return <DialogPrimitive.Portal data-slot="sheet-portal" {...props} />;
}

function SheetOverlay({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
	return (
		<DialogPrimitive.Overlay
			data-slot="sheet-overlay"
			className={cn(
				"fixed inset-0 z-50 bg-(--color-surface-overlay) opacity-[var(--opacity-overlay)]",
				"data-[state=open]:animate-in data-[state=open]:fade-in-0",
				"data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
				className,
			)}
			{...props}
		/>
	);
}

interface SheetContentProps
	extends React.ComponentProps<typeof DialogPrimitive.Content>,
		VariantProps<typeof sheetVariants> {
	readonly showClose?: boolean;
}

function SheetContent({
	side = "right",
	className,
	children,
	showClose = true,
	...props
}: SheetContentProps) {
	return (
		<SheetPortal>
			<SheetOverlay />
			<DialogPrimitive.Content
				data-slot="sheet-content"
				data-side={side}
				className={cn(
					sheetVariants({ side }),
					"flex flex-col",
					"duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out",
					className,
				)}
				{...props}
			>
				{children}
				{showClose && (
					<SheetClose aria-label="Close" />
				)}
			</DialogPrimitive.Content>
		</SheetPortal>
	);
}

function SheetHeader({
	className,
	...props
}: React.HTMLAttributes<HTMLDivElement>) {
	return (
		<div
			data-slot="sheet-header"
			className={cn(
				"flex flex-col space-y-2 text-center sm:text-left",
				className,
			)}
			{...props}
		/>
	);
}

function SheetFooter({
	className,
	...props
}: React.HTMLAttributes<HTMLDivElement>) {
	return (
		<div
			data-slot="sheet-footer"
			className={cn(
				"flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
				className,
			)}
			{...props}
		/>
	);
}

function SheetTitle({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
	return (
		<DialogPrimitive.Title
			data-slot="sheet-title"
			className={cn(
				"text-lg font-semibold leading-none text-(--color-foreground)",
				className,
			)}
			{...props}
		/>
	);
}

function SheetDescription({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
	return (
		<DialogPrimitive.Description
			data-slot="sheet-description"
			className={cn(
				"text-sm text-(--color-foreground-secondary)",
				className,
			)}
			{...props}
		/>
	);
}

export {
	Sheet,
	SheetClose,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetOverlay,
	SheetPortal,
	SheetTitle,
	SheetTrigger,
	sheetVariants,
};

"use client";

import { Dialog as DialogPrimitive } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

function Dialog({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
	return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({
	...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
	return (
		<DialogPrimitive.Trigger
			data-slot="dialog-trigger"
			{...props}
		/>
	);
}

function DialogClose({
	...props
}: React.ComponentProps<typeof DialogPrimitive.Close>) {
	return (
		<DialogPrimitive.Close
			data-slot="dialog-close"
			className={cn(
				"absolute top-4 right-4 rounded-sm opacity-70 ring-offset-background transition-opacity",
				"hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
				"disabled:pointer-events-none",
			)}
			{...props}
		/>
	);
}

function DialogPortal({
	...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
	return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogOverlay({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
	return (
		<DialogPrimitive.Overlay
			data-slot="dialog-overlay"
			className={cn(
				"fixed inset-0 z-50 bg-black/50",
				"data-[state=open]:animate-in data-[state=open]:fade-in-0",
				"data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
				className,
			)}
			{...props}
		/>
	);
}

function DialogContent({
	className,
	children,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
	return (
		<DialogPortal>
			<DialogOverlay />
			<DialogPrimitive.Content
				data-slot="dialog-content"
				className={cn(
					"fixed top-[50%] left-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%]",
					"gap-4 border border-(--color-border-subtle) bg-(--color-surface-3) p-6 shadow-lg",
					"rounded-(--radius-lg,8px)",
					"duration-200 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]",
					"data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]",
					className,
				)}
				{...props}
			>
				{children}
				<DialogClose className="absolute top-4 right-4 rounded-sm opacity-70 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
					&times;
				</DialogClose>
			</DialogPrimitive.Content>
		</DialogPortal>
	);
}

function DialogHeader({
	className,
	...props
}: React.HTMLAttributes<HTMLDivElement>) {
	return (
		<div
			data-slot="dialog-header"
			className={cn(
				"flex flex-col space-y-1.5 text-center sm:text-left",
				className,
			)}
			{...props}
		/>
	);
}

function DialogFooter({
	className,
	...props
}: React.HTMLAttributes<HTMLDivElement>) {
	return (
		<div
			data-slot="dialog-footer"
			className={cn(
				"flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
				className,
			)}
			{...props}
		/>
	);
}

function DialogTitle({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
	return (
		<DialogPrimitive.Title
			data-slot="dialog-title"
			className={cn(
				"text-lg font-semibold leading-none tracking-tight text-(--color-foreground-primary)",
				className,
			)}
			{...props}
		/>
	);
}

function DialogDescription({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
	return (
		<DialogPrimitive.Description
			data-slot="dialog-description"
			className={cn(
				"text-sm text-(--color-foreground-secondary)",
				className,
			)}
			{...props}
		/>
	);
}

export {
	Dialog,
	DialogClose,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogOverlay,
	DialogPortal,
	DialogTitle,
	DialogTrigger,
};

declare module "jsdom" {
	export interface ConstructorOptions {
		readonly pretendToBeVisual?: boolean;
		readonly resources?: "usable";
		readonly runScripts?: "dangerously" | "outside-only";
		readonly url?: string;
	}

	export class JSDOM {
		readonly window: Window & typeof globalThis & { close(): void };
		constructor(html?: string, options?: ConstructorOptions);
		serialize(): string;
	}
}

declare module "culori" {
	export interface Color {
		readonly mode: string;
		readonly [channel: string]: unknown;
	}

	export function parse(value: string): Color | undefined;
	export function oklch(value: { readonly mode: string }): Color | undefined;
	export function formatCss(value: Color | undefined): string;
	export function formatHex(value: Color): string | undefined;
	export function formatHex8(value: Color): string | undefined;
}

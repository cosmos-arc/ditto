export type OverlayKind =
	| "drawer"
	| "sheet"
	| "modal"
	| "alert-dialog"
	| "toast"
	| "inline";

export interface OverlayContract {
	readonly id: string;
	readonly kind: OverlayKind;
	readonly blocking: boolean;
	readonly requiredInDefaultFlow: boolean;
	readonly trigger: {
		readonly slot: string;
		readonly action: string;
	};
	readonly prototypeSelector: string;
	readonly reactComponent: string;
	readonly closeBehavior: readonly string[];
}

import { type ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";

export const SHELL_HEADER_EXTENSION_ID = "ditto-shell-header-extension";

export function ShellHeaderExtension({ children }: { readonly children: ReactNode }) {
	const [target, setTarget] = useState<HTMLElement | null>(null);

	useEffect(() => {
		setTarget(document.getElementById(SHELL_HEADER_EXTENSION_ID));
	}, []);

	return target ? createPortal(children, target) : children;
}

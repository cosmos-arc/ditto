import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { QueryProvider } from "@/providers";

// Fonts — Geist Sans/Mono via Fontsource (swap), Noto Sans SC via custom @font-face (optional)
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "@/styles/fonts.css";

import "@/styles/globals.css";

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}

async function enableMocking(): Promise<void> {
	if (import.meta.env.DEV) {
		const { worker } = await import("@/mocks/browser");
		await worker.start({ onUnhandledRequest: "bypass" });
	}
}

enableMocking().then(() => {
	createRoot(document.getElementById("root")!).render(
		<StrictMode>
			<QueryProvider>
				<RouterProvider router={router} />
			</QueryProvider>
		</StrictMode>,
	);
});

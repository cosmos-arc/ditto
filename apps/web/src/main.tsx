import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryProvider } from "@/providers";
import { routeTree } from "./routeTree.gen";

// Fonts — all via Fontsource (bundled woff2, no Google Fonts dependency)
// Inter: body text (400/500/600)
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
// JetBrains Mono: data/code (400/500)
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
// Geist Sans/Mono: heading/code accents (400/500/600)
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
// Noto Sans SC: CJK fallback via custom @font-face (optional)
import "@/styles/fonts.css";

import "@/styles/globals.css";

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}

async function enableMocking(): Promise<void> {
	if (import.meta.env.VITE_USE_MOCK === "true") {
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

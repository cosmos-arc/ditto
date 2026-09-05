import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initializeRuntimeConfig, verifyBackendCompatibility } from "@/api";
import { QueryProvider } from "@/providers";
import {
	type BootstrapStage,
	BootstrapStageFailure,
	diagnosticFromBootstrapFailure,
	renderBootstrapFailure,
} from "./bootstrap-failure";
import { routeTree } from "./routeTree.gen";

import "@/styles/core-fonts.css";
import "@/styles/globals.css";

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}

async function bootstrap(): Promise<void> {
	let stage: BootstrapStage = "runtime_config";
	try {
		const runtime = await initializeRuntimeConfig({ production: import.meta.env.PROD });
		const compatibilityWarnings: string[] = [];
		if (runtime.runtime === "mock") {
			stage = "mock_runtime";
			if (!import.meta.env.DEV) throw new Error("mock runtime is unavailable outside development builds");
			const { worker } = await import("@/mocks/browser");
			await worker.start({ onUnhandledRequest: "error" });
		} else {
			stage = "backend_compatibility";
			await verifyBackendCompatibility({
				release: import.meta.env.PROD,
				onWarning: (message) => compatibilityWarnings.push(message),
			});
		}
		stage = "application_render";
		createRoot(document.getElementById("root")!).render(
			<StrictMode>
				{compatibilityWarnings.length > 0 && (
					<aside
						role="status"
						aria-live="polite"
						className="fixed right-4 bottom-4 z-50 max-w-md rounded-(--radius-sm) border border-(--color-risk-warning-fg) bg-(--color-risk-warning-bg) p-3 text-xs text-(--color-risk-warning-fg)"
					>
						<strong>Ditto compatibility warning</strong>
						{compatibilityWarnings.map((message) => (
							<p key={message}>{message}</p>
						))}
					</aside>
				)}
				<QueryProvider>
					<RouterProvider router={router} />
				</QueryProvider>
			</StrictMode>,
		);
	} catch (error) {
		throw new BootstrapStageFailure(stage, error);
	}
}

function failClosed(error: unknown): void {
	renderBootstrapFailure(document.getElementById("root"), diagnosticFromBootstrapFailure(error));
}

void bootstrap().catch(failClosed);

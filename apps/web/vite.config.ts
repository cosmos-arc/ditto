import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), "");
	const apiTarget = env.VITE_DEV_API_TARGET ?? "http://localhost:8000";

	return {
		plugins: [TanStackRouterVite({ quoteStyle: "double" }), react(), tailwindcss()],
		resolve: {
			alias: {
				"@": path.resolve(__dirname, "./src"),
			},
		},
		server: {
			proxy: {
				"/api": {
					target: apiTarget,
					changeOrigin: true,
				},
			},
		},
	};
});

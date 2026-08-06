import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { ResearchPage } from "./components/research-page";

vi.mock("@tanstack/react-router", () => ({
	Link: ({ children, to }: { readonly children: ReactNode; readonly to: string }) => <a href={to}>{children}</a>,
}));

function wrapper({ children }: { readonly children: ReactNode }) {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

it("uses only frozen live R3 resources and exposes typed retry errors when mocks are disabled", async () => {
	vi.stubEnv("VITE_USE_MOCK", "false");
	const requests: string[] = [];
	server.use(
		http.get("/api/v1/research/experiments", ({ request }) => {
			requests.push(new URL(request.url).pathname);
			return HttpResponse.json(
				{ detail: "experiment catalog unavailable", error_code: "EXPERIMENT_CATALOG_UNAVAILABLE" },
				{ status: 503 },
			);
		}),
		http.get("/api/v1/research/reviews", ({ request }) => {
			requests.push(new URL(request.url).pathname);
			return HttpResponse.json(
				{ detail: "review queue unavailable", error_code: "REVIEW_QUEUE_UNAVAILABLE" },
				{ status: 503 },
			);
		}),
	);

	render(<ResearchPage />, { wrapper });

	expect(screen.queryByText(/prototype only/i)).not.toBeInTheDocument();
	await expect(screen.findByText(/503 EXPERIMENT_CATALOG_UNAVAILABLE/)).resolves.toBeInTheDocument();
	await expect(screen.findByText(/503 REVIEW_QUEUE_UNAVAILABLE/)).resolves.toBeInTheDocument();
	expect(screen.getByRole("button", { name: "重试实验目录" })).toBeInTheDocument();
	expect(screen.getByRole("button", { name: "重试审查队列" })).toBeInTheDocument();
	await waitFor(() => expect(requests.sort()).toEqual(["/api/v1/research/experiments", "/api/v1/research/reviews"]));
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { ReviewQueuePage } from "./review-queue-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("ReviewQueuePage", () => {
	it("shows a typed retryable error instead of an empty queue when the API fails", async () => {
		server.use(
			http.get("/api/v1/research/reviews", () =>
				HttpResponse.json(
					{ detail: "review read unavailable", error_code: "REVIEW_READ_UNAVAILABLE" },
					{ status: 503 },
				),
			),
		);
		render(<ReviewQueuePage />, { wrapper });

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 REVIEW_READ_UNAVAILABLE/);
		expect(screen.getByRole("button", { name: "重试审查队列" })).toBeInTheDocument();
		expect(screen.queryByText("暂无待审查版本。")).not.toBeInTheDocument();
	});
});

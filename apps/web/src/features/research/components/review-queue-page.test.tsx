import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { ReviewQueuePage } from "./review-queue-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			to,
			params,
			children,
			className,
		}: {
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
			readonly children: ReactNode;
			readonly className?: string;
		}) => (
			<a href={params?.id ? to.replace("$id", params.id) : to} className={className}>
				{children}
			</a>
		),
	};
});

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("ReviewQueuePage", () => {
	it("renders a live governed catalog and updates the exact selected review identity", async () => {
		const user = userEvent.setup();
		render(<ReviewQueuePage />, { wrapper });

		expect(await screen.findByRole("region", { name: "受控审查队列" })).toBeInTheDocument();
		expect(screen.getByRole("searchbox", { name: "搜索审查版本" })).toBeInTheDocument();
		await screen.findByRole("button", { name: "选择 seed_etf_industry_rotation v4" });
		expect(screen.getByRole("complementary", { name: "审查详情" })).toHaveTextContent("exp-rotation-v4");
		expect(screen.getByRole("complementary", { name: "审查详情" })).toHaveTextContent("approved");

		await user.click(screen.getByRole("button", { name: "选择 seed_etf_trend_following v3" }));
		expect(screen.getByRole("complementary", { name: "审查详情" })).toHaveTextContent("exp-trend-v3");
		expect(screen.getByRole("complementary", { name: "审查详情" })).toHaveTextContent("pending");

		await user.type(screen.getByRole("searchbox", { name: "搜索审查版本" }), "industry");
		expect(screen.getByRole("button", { name: "选择 seed_etf_industry_rotation v4" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "选择 seed_etf_trend_following v3" })).not.toBeInTheDocument();
	});

	it("keeps a review without a persisted packet visible but not actionable", async () => {
		const user = userEvent.setup();
		render(<ReviewQueuePage />, { wrapper });

		await user.click(await screen.findByRole("button", { name: "选择 seed_stock_picking v2" }));
		expect(screen.getByRole("complementary", { name: "审查详情" })).toHaveTextContent("Review packet 尚未生成");
		expect(screen.queryByRole("link", { name: "打开审查工作台" })).not.toBeInTheDocument();
	});

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

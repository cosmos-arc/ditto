import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { selectionRotationFixture } from "@/mocks/fixtures/selection";
import { selectionHandlers } from "@/mocks/handlers/selection";
import { server } from "@/mocks/server";
import { IndustryRotationPage } from "./industry-rotation-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => server.use(...selectionHandlers));

describe("IndustryRotationPage", () => {
	it("reads an exact snapshot and inspects deterministic rank contributions", async () => {
		const user = userEvent.setup();
		render(<IndustryRotationPage initialSnapshotId={selectionRotationFixture.snapshot_id} />, { wrapper: wrapper() });

		await expect(screen.findByText("电子")).resolves.toBeInTheDocument();
		expect(screen.getByText("relative_strength_20d")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "检查 传媒" }));
		expect(screen.getByRole("heading", { name: "传媒" })).toBeInTheDocument();
		expect(screen.getByText("fundamental_score")).toBeInTheDocument();
		expect(screen.getAllByText("sw-l1:2026-08-31").length).toBeGreaterThan(0);
	});
});

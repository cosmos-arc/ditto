import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { RegimePage } from "./regime-page";

const HASH = "a".repeat(64);
const DIAGNOSTICS = {
	snapshot_id: "snapshot-regime-1",
	snapshot_manifest_hash: HASH,
	dataset_id: "research-index-daily",
	source_snapshot_ids: ["provider-bars-v1"],
	builder_version: "research-snapshot-builder-v1",
	known_at_policy: "sample_time",
	benchmark_instrument_id: 300001,
	start_date: "2026-01-21",
	end_date: "2026-01-25",
	knowledge_cutoff: "2026-01-26",
	model_id: "momentum-20d-v1",
	lookback_observations: 20,
	bear_threshold: 35,
	bull_threshold: 65,
	bars_input_id: "bars-regime-1",
	bars_content_hash: "b".repeat(64),
	bars_schema_hash: "c".repeat(64),
	current: {
		observed_at: "2026-01-25",
		score: 80,
		label: "bull" as const,
		position_ratio: 1,
		indicators: [{ name: "momentum", normalized_score: 0.8 }],
	},
	observations: [
		{
			observed_at: "2026-01-23",
			score: 50,
			label: "neutral" as const,
			position_ratio: 0.7,
			indicators: [{ name: "momentum", normalized_score: 0.5 }],
		},
		{
			observed_at: "2026-01-25",
			score: 80,
			label: "bull" as const,
			position_ratio: 1,
			indicators: [{ name: "momentum", normalized_score: 0.8 }],
		},
	],
	transitions: [{ observed_at: "2026-01-25", from_label: "neutral" as const, to_label: "bull" as const }],
};

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

async function bindExactScope(user: ReturnType<typeof userEvent.setup>) {
	await user.click(screen.getAllByRole("button", { name: "绑定诊断范围" })[0] as HTMLButtonElement);
	expect(screen.getByRole("dialog", { name: "绑定 PIT 诊断范围" })).toBeInTheDocument();
	await user.type(screen.getByLabelText("研究快照 ID"), "snapshot-regime-1");
	await user.type(screen.getByLabelText("快照 manifest hash"), HASH);
	await user.type(screen.getByLabelText("基准 Instrument ID"), "300001");
	await user.type(screen.getByLabelText("诊断开始日期"), "2026-01-21");
	await user.type(screen.getByLabelText("诊断结束日期"), "2026-01-25");
	await user.type(screen.getByLabelText("知识截止日期"), "2026-01-26");
	await user.click(screen.getByRole("button", { name: "运行 PIT 诊断" }));
}

describe("RegimePage exact PIT diagnostics", () => {
	it("fails closed until exact scope is bound, then preserves every scope field and renders governed evidence", async () => {
		const user = userEvent.setup();
		const requests: URL[] = [];
		server.use(
			http.get("/api/v1/market/regime", ({ request }) => {
				requests.push(new URL(request.url));
				return HttpResponse.json({ data: DIAGNOSTICS });
			}),
		);

		render(<RegimePage />, { wrapper: createWrapper() });

		expect(await screen.findByText("诊断范围未绑定")).toBeInTheDocument();
		expect(requests).toHaveLength(0);

		await bindExactScope(user);

		expect(await screen.findByRole("heading", { name: "风险偏好" })).toBeInTheDocument();
		expect(screen.getAllByText("80.0").length).toBeGreaterThan(0);
		expect(screen.getByText("momentum-20d-v1")).toBeInTheDocument();
		expect(screen.getByText("provider-bars-v1")).toBeInTheDocument();
		expect(screen.queryByText(/北向资金/)).not.toBeInTheDocument();
		expect(requests).toHaveLength(1);

		const params = requests[0]?.searchParams;
		expect(params?.get("snapshot_id")).toBe("snapshot-regime-1");
		expect(params?.get("snapshot_manifest_hash")).toBe(HASH);
		expect(params?.get("benchmark_instrument_id")).toBe("300001");
		expect(params?.get("start_date")).toBe("2026-01-21");
		expect(params?.get("end_date")).toBe("2026-01-25");
		expect(params?.get("knowledge_cutoff")).toBe("2026-01-26");
	});

	it("shows the typed service error without reviving retired static regime claims", async () => {
		const user = userEvent.setup();
		server.use(
			http.get("/api/v1/market/regime", () =>
				HttpResponse.json(
					{ detail: "snapshot evidence unavailable", error_code: "REGIME_DIAGNOSTICS_UNAVAILABLE" },
					{ status: 503 },
				),
			),
		);

		render(<RegimePage />, { wrapper: createWrapper() });
		await bindExactScope(user);

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 REGIME_DIAGNOSTICS_UNAVAILABLE/);
		expect(screen.queryByText("risk_on")).not.toBeInTheDocument();
		expect(screen.queryByText(/北向资金/)).not.toBeInTheDocument();
	});
});

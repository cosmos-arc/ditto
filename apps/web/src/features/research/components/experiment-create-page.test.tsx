import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { ExperimentCreatePage } from "./experiment-create-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

function readyPreflight() {
	return {
		status: "ready",
		plan_hash: "d".repeat(64),
		checks: [
			{
				rule_id: "history-and-isolation",
				outcome: "PASS",
				code: null,
				reason: null,
				remediation: null,
				observed: { eligible_month_count: 96, purge_sessions: 5, embargo_sessions: 1 },
				policy: { promotion_minimum_months: 96 },
			},
		],
		candidate_count: 3,
		planned_fold_count: 12,
		budget_run_count: 12,
		estimated_trading_sessions: 2048,
		estimated_disk_bytes: 4096,
		eligible_month_count: 96,
		isolation_width_sessions: 6,
	};
}

describe("ExperimentCreatePage", () => {
	it("renders a governed studio with the exact planning identity and an honest preflight state", async () => {
		render(<ExperimentCreatePage />, { wrapper });

		const studio = screen.getByRole("region", { name: "实验规划工作区" });
		expect(within(studio).getByText("r3-experiment")).toBeInTheDocument();
		expect(within(studio).getByText("seed_stock_selection_rotation@1")).toBeInTheDocument();
		expect(within(studio).getByText("certified-snapshot-r3")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='source']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='main']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='inspector']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='logs']")).toBeInTheDocument();
		expect(within(studio).getByText("尚未运行。Preflight 为只读，不创建 experiment。")).toBeInTheDocument();
	});

	it("binds launch to one confirmed preflight and invalidates confirmation after any edit", async () => {
		const user = userEvent.setup();
		const onLaunched = vi.fn();
		server.use(
			http.post("/api/v1/research/experiments/:experimentId/preflight", () =>
				HttpResponse.json({ data: readyPreflight() }),
			),
			http.post("/api/v1/research/experiments", () =>
				HttpResponse.json({
					data: {
						experiment_id: "r3-experiment",
						status: "queued",
						queue_ordinal: 1,
						revision: 1,
						plan_hash: "d".repeat(64),
						candidate_count: 3,
						fold_count: 12,
					},
				}),
			),
		);

		render(<ExperimentCreatePage onLaunched={onLaunched} />, { wrapper });

		expect(screen.getByText("3 / 128")).toBeInTheDocument();
		expect(screen.getByLabelText("Worker count")).toHaveValue("2");
		expect(screen.getByLabelText("Worker count").querySelectorAll("option")).toHaveLength(2);
		expect(screen.getByRole("button", { name: "启动实验" })).toBeDisabled();

		await user.click(screen.getByRole("button", { name: "运行只读 Preflight" }));
		await expect(screen.findByText("96 个月")).resolves.toBeInTheDocument();
		expect(screen.getByText(/purge_sessions/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "启动实验" })).toBeDisabled();

		await user.click(screen.getByRole("checkbox", { name: /确认 plan hash/ }));
		expect(screen.getByRole("button", { name: "启动实验" })).toBeEnabled();
		await user.clear(screen.getByLabelText("Seed"));
		await user.type(screen.getByLabelText("Seed"), "43");
		expect(screen.getByText("Preflight 已过期")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "启动实验" })).toBeDisabled();

		await user.click(screen.getByRole("button", { name: "运行只读 Preflight" }));
		await user.click(await screen.findByRole("checkbox", { name: /确认 plan hash/ }));
		await user.click(screen.getByRole("button", { name: "启动实验" }));
		await expect.poll(() => onLaunched).toHaveBeenCalledWith("r3-experiment");
	});

	it.each([
		[409, "PLAN_HASH_STALE"],
		[422, "PLANNING_INVALID"],
	] as const)("keeps the confirmed server preflight and form after a %s launch rejection", async (status, code) => {
		const user = userEvent.setup();
		server.use(
			http.post("/api/v1/research/experiments/:experimentId/preflight", () =>
				HttpResponse.json({ data: readyPreflight() }),
			),
			http.post("/api/v1/research/experiments", () =>
				HttpResponse.json({ detail: "server rejected launch", error_code: code }, { status }),
			),
		);

		render(<ExperimentCreatePage />, { wrapper });
		await user.click(screen.getByRole("button", { name: "运行只读 Preflight" }));
		await user.click(await screen.findByRole("checkbox", { name: /确认 plan hash/ }));
		await user.click(screen.getByRole("button", { name: "启动实验" }));

		await expect(screen.findByText(new RegExp(`${status} ${code}`))).resolves.toBeInTheDocument();
		expect(screen.getByLabelText("Experiment ID")).toHaveValue("r3-experiment");
		expect(screen.getByText("96 个月")).toBeInTheDocument();
		expect(screen.getByRole("checkbox", { name: /确认 plan hash/ })).toBeChecked();
	});

	it("preserves form truth and reuses the launch key after a typed 503", async () => {
		const user = userEvent.setup();
		const keys: string[] = [];
		let launches = 0;
		server.use(
			http.post("/api/v1/research/experiments/:experimentId/preflight", () =>
				HttpResponse.json({ data: readyPreflight() }),
			),
			http.post("/api/v1/research/experiments", ({ request }) => {
				launches += 1;
				keys.push(request.headers.get("Idempotency-Key") ?? "");
				if (launches === 1) {
					return HttpResponse.json(
						{ detail: "launch outcome unknown", error_code: "LAUNCH_OUTCOME_UNKNOWN" },
						{ status: 503 },
					);
				}
				return HttpResponse.json({
					data: {
						experiment_id: "r3-experiment",
						status: "queued",
						queue_ordinal: 1,
						revision: 1,
						plan_hash: "d".repeat(64),
						candidate_count: 3,
						fold_count: 12,
					},
				});
			}),
		);

		render(<ExperimentCreatePage />, { wrapper });
		await user.click(screen.getByRole("button", { name: "运行只读 Preflight" }));
		await user.click(await screen.findByRole("checkbox", { name: /确认 plan hash/ }));
		await user.click(screen.getByRole("button", { name: "启动实验" }));
		await expect(screen.findByText(/503 LAUNCH_OUTCOME_UNKNOWN/)).resolves.toBeInTheDocument();
		expect(screen.getByLabelText("Experiment ID")).toHaveValue("r3-experiment");

		await user.click(screen.getByRole("button", { name: "启动实验" }));
		await expect.poll(() => launches).toBe(2);
		expect(keys[0]).toBeTruthy();
		expect(keys[1]).toBe(keys[0]);
	});
});

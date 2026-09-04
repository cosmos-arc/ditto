import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { mockStrategyDetailDto } from "@/mocks/fixtures/strategy-live";
import { server } from "@/mocks/server";
import { QueryProvider } from "@/providers";
import { routeTree } from "@/routeTree.gen";
import { useStrategyStudioStore } from "../state/strategy-studio-store";

const STUDIO_ROUTE = "/research/strategies/seed_etf_industry_rotation/studio";

function renderStudio(): void {
	const history = createMemoryHistory({ initialEntries: [STUDIO_ROUTE] });
	const router = createRouter({ routeTree, history });
	render(
		<QueryProvider>
			<RouterProvider router={router} />
		</QueryProvider>,
	);
}

beforeEach(() => {
	useStrategyStudioStore.setState({
		workingSpec: null,
		savedSpec: null,
		mode: "form",
		selectedNodeKey: null,
	});
});

describe("StrategyPage governed workspace", () => {
	it("renders the live strategy identity, four studio surfaces, and honest evidence state", async () => {
		renderStudio();

		const workspace = await screen.findByRole("region", { name: "策略 Studio 工作区" });
		expect(await within(workspace).findByText("ETF 行业轮动")).toBeInTheDocument();
		expect(within(workspace).getAllByText(/seed_etf_industry_rotation · v3/)).not.toHaveLength(0);
		expect(await within(workspace).findByText("h-v3")).toBeInTheDocument();
		expect(within(workspace).getByText("未绑定，Experiment preflight 时固定")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='source']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='main']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='inspector']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='logs']")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "校验" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "Dry Run" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "提交回测" })).toBeInTheDocument();
		expect(screen.queryByText("多因子动量策略 v2.3")).not.toBeInTheDocument();
		expect(screen.queryByText("校验通过，Dry Run 可执行")).not.toBeInTheDocument();
	});

	it("validates the edited working copy before confirming an idempotent new version save", async () => {
		const user = userEvent.setup();
		let putCalls = 0;
		let idempotencyKey = "";
		let savedVersion = 0;
		server.use(
			http.put("/api/v1/strategies/:id", async ({ request }) => {
				putCalls += 1;
				idempotencyKey = request.headers.get("Idempotency-Key") ?? "";
				const body = (await request.json()) as { readonly version: number };
				savedVersion = body.version;
				return HttpResponse.json({ data: { ...mockStrategyDetailDto, version: 4 } });
			}),
		);
		renderStudio();

		const name = await screen.findByRole("textbox", { name: "名称" });
		await user.clear(name);
		await user.type(name, "ETF 行业轮动增强");
		await user.click(screen.getByRole("button", { name: "校验" }));

		expect(await screen.findAllByText("h-candidate")).not.toHaveLength(0);
		expect(screen.getByRole("status", { name: "Spec 校验结果" })).toHaveTextContent("校验有效");
		await user.click(screen.getByRole("button", { name: "保存" }));
		const dialog = await screen.findByRole("dialog", { name: "保存新版本" });
		expect(within(dialog).getByText(/base v3/)).toBeInTheDocument();
		expect(within(dialog).getByText("h-candidate")).toBeInTheDocument();
		expect(putCalls).toBe(0);

		await user.click(within(dialog).getByRole("button", { name: "确认保存新版本" }));
		await waitFor(() => expect(putCalls).toBe(1));
		expect(savedVersion).toBe(3);
		expect(idempotencyKey).toMatch(/^strategy-save-/);
		expect(await screen.findByRole("status", { name: "Studio 操作结果" })).toHaveTextContent("已保存为新版本");
	});

	it("shows detached Author draft, compile, validate, diff, and tests without mutation authority", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		let mutationCalls = 0;
		const operation = (kind: "draft" | "compile" | "validate" | "diff") => ({
			kind,
			subject_id: "seed_etf_industry_rotation",
			subject_version: "3",
			valid: true,
			changed: kind === "diff",
			publishable: false as const,
			payload_hash: `${kind}-hash`,
			payload: { operation: kind, publishable: false },
			lineage: [`author-preview:${kind}`],
		});
		server.use(
			http.post("/api/v1/strategies/:id/versions/:version/author-preview", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({
					data: {
						strategy_id: "seed_etf_industry_rotation",
						base_version: 3,
						valid: true,
						publishable: false,
						canonical_hash: "author-candidate-hash",
						draft: operation("draft"),
						compile: [operation("compile")],
						validation: operation("validate"),
						diff: operation("diff"),
						tests: [
							{ name: "canonical_hash_consistent", passed: true, detail: "one candidate" },
							{ name: "preview_non_publishable", passed: true, detail: "no mutation authority" },
						],
					},
				});
			}),
			http.put("/api/v1/strategies/:id", () => {
				mutationCalls += 1;
				return HttpResponse.json({ data: mockStrategyDetailDto });
			}),
			http.post("/api/v1/strategies/:id/versions/:version/:action", () => {
				mutationCalls += 1;
				return HttpResponse.json({ data: {} });
			}),
		);
		renderStudio();

		await screen.findByText("ETF 行业轮动");
		await user.click(screen.getByRole("button", { name: "Author 预览" }));
		const sheet = await screen.findByRole("dialog", { name: "Author 安全预览" });
		for (const section of ["Draft", "Compile", "Validate", "Diff", "Tests"]) {
			expect(within(sheet).getByRole("heading", { name: section })).toBeInTheDocument();
		}
		expect(within(sheet).getByText("author-candidate-hash")).toBeInTheDocument();
		expect(within(sheet).getByText("canonical_hash_consistent")).toBeInTheDocument();
		expect(within(sheet).getByText("只读预览 · 不可发布")).toBeInTheDocument();
		expect(requestBody).toMatchObject({ spec_json: { strategy_id: "seed_etf_industry_rotation" } });
		expect((requestBody as { expressions: unknown[] }).expressions).toContainEqual({
			derived_id: "momentum_1m",
			version: 1,
			expression: "momentum_1m",
		});
		expect(mutationCalls).toBe(0);
	});

	it("keeps dry-run and backtest as exact planning handoffs without inventing a run", async () => {
		const user = userEvent.setup();
		let experimentWrites = 0;
		server.use(
			http.post("/api/v1/research/experiments/:path*", () => {
				experimentWrites += 1;
				return HttpResponse.json({ data: {} });
			}),
		);
		renderStudio();

		await screen.findByText("ETF 行业轮动");
		await user.click(screen.getByRole("button", { name: "Dry Run" }));
		let sheet = await screen.findByRole("dialog", { name: "Dry Run 规划" });
		expect(within(sheet).getByText("seed_etf_industry_rotation@3")).toBeInTheDocument();
		expect(within(sheet).getByText("未运行")).toBeInTheDocument();
		expect(within(sheet).getByText(/snapshot、时间范围、registry hash/)).toBeInTheDocument();
		expect(experimentWrites).toBe(0);
		await user.click(within(sheet).getByRole("button", { name: "关闭" }));

		await user.click(screen.getByRole("button", { name: "提交回测" }));
		sheet = await screen.findByRole("dialog", { name: "提交回测规划" });
		expect(within(sheet).getByText("seed_etf_industry_rotation@3")).toBeInTheDocument();
		expect(within(sheet).getByRole("link", { name: "打开实验创建器" })).toHaveAttribute(
			"href",
			"/research/experiments/new",
		);
		expect(experimentWrites).toBe(0);
	});

	it("previews only live factors and deprecates through the audited command", async () => {
		const user = userEvent.setup();
		let deprecateBody: unknown;
		let deprecateKey = "";
		server.use(
			http.post("/api/v1/strategies/:id/versions/:version/deprecate", async ({ request }) => {
				deprecateBody = await request.json();
				deprecateKey = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
					data: {
						strategy_id: "seed_etf_industry_rotation",
						version: 3,
						state: "deprecated",
						review_outcome: "approved",
					},
				});
			}),
		);
		renderStudio();

		await screen.findByText("ETF 行业轮动");
		await user.click(screen.getByRole("button", { name: "因子预览" }));
		let sheet = await screen.findByRole("dialog", { name: "因子预览" });
		expect(within(sheet).getByText("momentum_1m")).toBeInTheDocument();
		expect(within(sheet).getByText("0.5")).toBeInTheDocument();
		expect(within(sheet).getByText("分布未评估")).toBeInTheDocument();
		expect(within(sheet).queryByText("45%")).not.toBeInTheDocument();
		await user.click(within(sheet).getByRole("button", { name: "关闭" }));

		await user.click(screen.getByRole("button", { name: "弃用版本" }));
		sheet = await screen.findByRole("dialog", { name: "弃用版本" });
		await user.type(within(sheet).getByRole("textbox", { name: "执行者" }), "reviewer-a");
		await user.type(within(sheet).getByRole("textbox", { name: "原因" }), "策略已由受控新版本替代");
		await user.click(within(sheet).getByRole("button", { name: "确认弃用" }));

		await waitFor(() => expect(deprecateBody).toEqual({ actor: "reviewer-a", reason: "策略已由受控新版本替代" }));
		expect(deprecateKey).toMatch(/^strategy-governance-/);
	});
});

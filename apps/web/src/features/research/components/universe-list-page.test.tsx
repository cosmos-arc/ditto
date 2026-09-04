import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { UniverseListPage } from "./universe-list-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })}
		>
			{children}
		</QueryClientProvider>
	);
}

const PRESET = {
	universe_id: "csi300",
	name: "沪深 300",
	universe_type: "preset",
	description: "官方指数范围",
	source_ref: "index:csi300",
};

describe("UniverseListPage governed catalog", () => {
	it("loads official definitions and fails closed until an explicit membership as-of is bound", async () => {
		const memberRequests: string[] = [];
		server.use(
			http.get("/api/v1/universes", () => HttpResponse.json({ data: [PRESET] })),
			http.get("/api/v1/universes/csi300/members", ({ request }) => {
				memberRequests.push(request.url);
				const asof = new URL(request.url).searchParams.get("asof");
				return HttpResponse.json({ data: [{ instrument_id: asof === "2026-06-30" ? 510300 : 999999 }] });
			}),
		);

		render(<UniverseListPage />, { wrapper });

		expect(await screen.findByRole("region", { name: "受控股票池目录" })).toBeInTheDocument();
		expect(await screen.findByRole("button", { name: "选择股票池 csi300" })).toBeInTheDocument();
		expect(screen.getByText(/选择 as-of 日期后读取成分/)).toBeInTheDocument();
		expect(memberRequests).toHaveLength(0);

		fireEvent.change(screen.getByLabelText("股票池成分 as-of 日期"), { target: { value: "2026-06-30" } });

		expect(await screen.findByText("Instrument #510300")).toBeInTheDocument();
		expect(screen.queryByText("Instrument #999999")).not.toBeInTheDocument();
		expect(new URL(memberRequests[0] ?? "http://invalid").searchParams.get("asof")).toBe("2026-06-30");
	});

	it("shows a typed list retry without falling back to retired static definitions", async () => {
		server.use(
			http.get("/api/v1/universes", () =>
				HttpResponse.json(
					{ detail: "catalog unavailable", error_code: "UNIVERSE_CATALOG_UNAVAILABLE" },
					{ status: 503 },
				),
			),
		);

		render(<UniverseListPage />, { wrapper });

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 UNIVERSE_CATALOG_UNAVAILABLE/);
		expect(screen.getByRole("button", { name: "重试股票池目录" })).toBeInTheDocument();
		expect(screen.queryByText("高股息精选")).not.toBeInTheDocument();
	});

	it("creates, edits, and explicitly deletes only custom definitions through generated commands", async () => {
		const user = userEvent.setup();
		let rows = [PRESET];
		server.use(
			http.get("/api/v1/universes", () => HttpResponse.json({ data: rows })),
			http.post("/api/v1/universes", async ({ request }) => {
				const body = (await request.json()) as { universe_id: string; name: string; description?: string };
				const created = {
					...body,
					description: body.description ?? "",
					universe_type: "custom",
					source_ref: "",
				};
				rows = [...rows, created];
				return HttpResponse.json({ data: created }, { status: 201 });
			}),
			http.put("/api/v1/universes/:id", async ({ params, request }) => {
				const body = (await request.json()) as { name: string; description?: string };
				const current = rows.find((row) => row.universe_id === params.id);
				const updated = { ...current, ...body } as (typeof rows)[number];
				rows = rows.map((row) => (row.universe_id === params.id ? updated : row));
				return HttpResponse.json({ data: updated });
			}),
			http.delete("/api/v1/universes/:id", ({ params }) => {
				rows = rows.filter((row) => row.universe_id !== params.id);
				return HttpResponse.json({ data: true });
			}),
		);

		render(<UniverseListPage />, { wrapper });
		await screen.findAllByText("沪深 300");

		await user.click(screen.getByRole("button", { name: "新建股票池" }));
		await user.type(screen.getByLabelText("Universe ID"), "etf_core");
		await user.type(screen.getByLabelText("股票池名称"), "ETF 核心池");
		await user.type(screen.getByLabelText("股票池描述"), "人工维护的核心范围");
		await user.click(screen.getByRole("button", { name: "创建股票池" }));
		expect(await screen.findByRole("button", { name: "选择股票池 etf_core" })).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "选择股票池 etf_core" }));
		await user.click(screen.getByRole("button", { name: "编辑股票池" }));
		const nameField = screen.getByLabelText("股票池名称");
		await user.clear(nameField);
		await user.type(nameField, "ETF 核心观察池");
		await user.click(screen.getByRole("button", { name: "保存股票池" }));
		expect((await screen.findAllByText("ETF 核心观察池")).length).toBeGreaterThan(0);

		await user.click(screen.getByRole("button", { name: "删除股票池" }));
		expect(screen.getByRole("dialog")).toHaveTextContent("etf_core");
		await user.click(screen.getByRole("button", { name: "确认删除股票池" }));
		await waitFor(() => expect(screen.queryByRole("button", { name: "选择股票池 etf_core" })).not.toBeInTheDocument());
	});
});

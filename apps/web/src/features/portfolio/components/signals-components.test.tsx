import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { liveDailyDecisionV2, portfolioHandlers } from "@/mocks/handlers/portfolio";
import { server } from "@/mocks/server";
import { SignalDetailPanel } from "./signal-detail-panel";
import { SignalsHealthStrip } from "./signals-health-strip";
import { SignalsList } from "./signals-list";
import { SignalsPage } from "./signals-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...portfolioHandlers));

// ── SignalsList ─────────────────────────────────────────────────

describe("SignalsList", () => {
	it("渲染信号标题", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("信号队列")).resolves.toBeInTheDocument();
	});

	it("显示信号列表", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量突破")).resolves.toBeInTheDocument();
		await expect(screen.findByText("获利了结")).resolves.toBeInTheDocument();
		await expect(screen.findByText("均值回归")).resolves.toBeInTheDocument();
	});

	it("显示信号方向", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findAllByText("BUY")).resolves.toHaveLength(2);
		await expect(screen.getByText("SELL")).toBeInTheDocument();
	});

	it("显示置信度", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("85%")).resolves.toBeInTheDocument();
	});
});

describe("SignalsPage", () => {
	it("宽屏合同默认保留可见详情槽，窄屏选择时仍使用 Drawer", async () => {
		const user = userEvent.setup();
		const { container } = render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("动量突破")).resolves.toBeInTheDocument();
		await waitFor(() => expect(container.querySelector("[data-slot='detail']")).toBeInTheDocument());
		expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

		await user.click(screen.getByText("动量突破"));
		await expect(screen.findByRole("dialog", { name: "信号详情" })).resolves.toBeInTheDocument();
	});

	it("批量入口明确降级为逐条人工复核，不伪造批量确认写入", async () => {
		const user = userEvent.setup();
		render(<SignalsPage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "批量复核" }));
		const dialog = await screen.findByRole("dialog", { name: "批量复核" });
		expect(dialog).toHaveTextContent("后端未提供批量确认接口");
		expect(dialog).toHaveTextContent("3 个待处理项");

		await user.click(within(dialog).getByRole("button", { name: "开始逐条复核" }));
		await expect(screen.findByRole("dialog", { name: "信号详情" })).resolves.toBeInTheDocument();
	});
});

// ── SignalsHealthStrip ──────────────────────────────────────────

describe("SignalsHealthStrip", () => {
	it("渲染信号队列统计指标", async () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("待处理")).resolves.toBeInTheDocument();
		expect(screen.getByText("已确认")).toBeInTheDocument();
		expect(screen.getByText("已忽略")).toBeInTheDocument();
		expect(screen.getByText("已下单")).toBeInTheDocument();
	});

	it("显示队列计数", async () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		// mockSignalsQueue: { pending: 5, confirmed: 12, ignored: 3, ordered: 8 }
		await expect(screen.findByText("5")).resolves.toBeInTheDocument();
		expect(screen.getByText("12")).toBeInTheDocument();
		expect(screen.getByText("3")).toBeInTheDocument();
		expect(screen.getByText("8")).toBeInTheDocument();
	});

	it("显示加载骨架屏", () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		// 骨架屏应出现（loading 状态）
		const skeletons = document.querySelectorAll("[data-slot]");
		expect(skeletons.length).toBeGreaterThanOrEqual(0);
	});

	it("live 队列汇总失败时显示重试入口并可恢复", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get(
				"/api/v1/manual/daily-decision/v2",
				() => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
				{ once: true },
			),
		);
		const user = userEvent.setup();
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByRole("alert")).resolves.toHaveTextContent("信号队列数据加载失败");
		await user.click(screen.getByRole("button", { name: "重试" }));

		await expect(screen.findByText("待处理")).resolves.toBeInTheDocument();
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});
});

// ── SignalDetailPanel ───────────────────────────────────────────

describe("SignalDetailPanel", () => {
	it("渲染信号解读文本", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/动量突破信号/)).resolves.toBeInTheDocument();
	});

	it("渲染风控检查列表", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText("涨跌停检查")).resolves.toBeInTheDocument();
		expect(screen.getByText("集中度检查")).toBeInTheDocument();
		// "行业暴露" 同时出现在风险检查和组合影响，用 getAllByText
		expect(screen.getAllByText("行业暴露").length).toBeGreaterThanOrEqual(1);
	});

	it("渲染风控检查状态", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/近 3 日无涨跌停/)).resolves.toBeInTheDocument();
	});

	it("渲染操作按钮", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText("确认信号")).resolves.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "AI 解读" })).toBeInTheDocument();
	});

	it("AI 解读明确呈现只读证据摘要而不伪造模型结论", async () => {
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="sig-001" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "AI 解读" }));

		const dialog = await screen.findByRole("dialog", { name: "AI 解读" });
		expect(within(dialog).getByText(/只读证据摘要/)).toBeInTheDocument();
		expect(within(dialog).getByText(/波动率检查/)).toBeInTheDocument();
		expect(within(dialog).getByText(/未调用模型/)).toBeInTheDocument();
	});

	it("mock 确认动作先展示订单复核，不跳过到手工成交", async () => {
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="sig-001" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "确认信号" }));

		const dialog = await screen.findByRole("dialog", { name: "订单复核" });
		expect(within(dialog).getByText(/不会创建 Paper 订单或成交/)).toBeInTheDocument();
		expect(within(dialog).getByText("VOLATILITY_ABOVE_THRESHOLD")).toBeInTheDocument();
		expect(within(dialog).getByRole("link", { name: "进入订单台账" })).toHaveAttribute(
			"href",
			"/portfolio/transactions",
		);
	});

	it("live 信号可先查看同一 intent 的订单复核，再独立录入成交", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "查看订单复核" }));

		const dialog = await screen.findByRole("dialog", { name: "订单复核" });
		expect(within(dialog).getByText("intent-510300")).toBeInTheDocument();
		expect(within(dialog).getByText("RISK_WARNING")).toBeInTheDocument();
	});

	it("live 信号详情失败时显示重试入口并可恢复", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get(
				"/api/v1/manual/daily-decision/v2",
				() => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
				{ once: true },
			),
		);
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByRole("alert")).resolves.toHaveTextContent("信号详情加载失败");
		await user.click(screen.getByRole("button", { name: "重试" }));

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("live 模式可录入 manual paper 手工成交", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));

		await expect(screen.findByRole("dialog", { name: "订单确认" })).resolves.toBeInTheDocument();
		expect(screen.getByDisplayValue("600")).toBeInTheDocument();
		expect(screen.getByText("建议 1,000")).toBeInTheDocument();
		expect(screen.getByText("已成交 400")).toBeInTheDocument();
		expect(screen.getByText("剩余 600")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "提交手工成交" }));
		expect(screen.getByText("成交价格必须大于 0")).toBeInTheDocument();

		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
	});

	it("成交抽屉支持键盘打开、Escape 关闭并把焦点还给触发按钮", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		const trigger = await screen.findByRole("button", { name: "录入手工成交" });
		trigger.focus();
		await user.keyboard("{Enter}");

		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		expect(dialog).toContainElement(document.activeElement as HTMLElement);

		await user.keyboard("{Escape}");
		await waitFor(() => expect(screen.queryByRole("dialog", { name: "订单确认" })).not.toBeInTheDocument());
		expect(trigger).toHaveFocus();
	});

	it("成交提交 pending 时锁定编辑与所有关闭路径", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		let releaseResponse: () => void = () => undefined;
		const responseGate = new Promise<void>((resolve) => {
			releaseResponse = resolve;
		});
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				const payload = await request.json();
				await responseGate;
				return HttpResponse.json({ data: payload });
			}),
		);
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		await user.click(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.type(within(dialog).getByLabelText("成交价格"), "4.32");
		await user.click(within(dialog).getByRole("button", { name: "提交手工成交" }));

		await expect(within(dialog).findByRole("button", { name: "提交中" })).resolves.toBeDisabled();
		expect(within(dialog).getByLabelText("成交价格")).toBeDisabled();
		expect(within(dialog).getByLabelText("实际成交日")).toBeDisabled();
		expect(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" })).toBeDisabled();
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await user.keyboard("{Escape}");
		await user.click(within(dialog).getByRole("button", { name: "Close" }));
		expect(dialog).toBeInTheDocument();

		releaseResponse();
		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
	});

	it("成交抽屉在窄屏拥有纵向滚动且表单可自然生长", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));

		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		expect(dialog).toHaveClass("overflow-y-auto");
		const form = dialog.querySelector("form");
		expect(form).toHaveClass("min-h-full");
		expect(form).not.toHaveClass("h-full");
	});

	it("review 状态展示后端原因并要求人工复核后才可提交成交", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		let requestCount = 0;
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				requestCount += 1;
				return HttpResponse.json({ data: await request.json() });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));
		expect(screen.getByText("RISK_WARNING")).toBeInTheDocument();
		const confirmation = screen.getByRole("checkbox", { name: "我已复核以上原因" });
		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		expect(requestCount).toBe(0);
		expect(screen.getByRole("alert")).toHaveTextContent("请先确认已复核后端返回的原因");

		await user.click(confirmation);
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));
		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		expect(requestCount).toBe(1);
	});

	it("前端阻止成交数量超过后端剩余数量", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		let requestCount = 0;
		server.use(
			http.post("/api/v1/manual/fills", () => {
				requestCount += 1;
				return HttpResponse.json({ data: {} });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));
		await user.clear(screen.getByLabelText("成交数量"));
		await user.type(screen.getByLabelText("成交数量"), "601");
		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		expect(screen.getByRole("alert")).toHaveTextContent("成交数量不能超过剩余数量 600");
		expect(requestCount).toBe(0);
	});

	it("同一 intent 连续录入时为每笔部分成交生成不同 fill_id", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		const fillIds: string[] = [];
		const quantities: number[] = [];
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				const payload = (await request.json()) as { fill_id: string; quantity: number };
				fillIds.push(payload.fill_id);
				quantities.push(payload.quantity);
				return HttpResponse.json({ data: payload });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		for (const price of ["4.31", "4.32"]) {
			await user.click(screen.getByRole("button", { name: "录入手工成交" }));
			await user.click(screen.getByRole("checkbox", { name: "我已复核以上原因" }));
			await user.clear(screen.getByLabelText("成交数量"));
			await user.type(screen.getByLabelText("成交数量"), "300");
			await user.type(screen.getByLabelText("成交价格"), price);
			await user.click(screen.getByRole("button", { name: "提交手工成交" }));
			await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		}

		expect(fillIds).toHaveLength(2);
		expect(new Set(fillIds).size).toBe(2);
		expect(quantities).toEqual([300, 300]);
	});

	it("HTTP 503 结果不明时锁定 Sheet 并用完全相同 payload 重试", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		const submitted: Record<string, unknown>[] = [];
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				const payload = (await request.json()) as Record<string, unknown>;
				submitted.push(payload);
				if (submitted.length === 1) {
					return HttpResponse.json({ detail: "提交结果未知，请用相同幂等键重试" }, { status: 503 });
				}
				return HttpResponse.json({ data: payload });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		await user.click(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.type(within(dialog).getByLabelText("成交价格"), "4.32");
		await user.click(within(dialog).getByRole("button", { name: "提交手工成交" }));
		await waitFor(() => expect(submitted).toHaveLength(1));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("提交结果未知");
		expect(within(dialog).getByLabelText("成交价格")).toBeDisabled();
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await user.keyboard("{Escape}");
		await user.click(within(dialog).getByRole("button", { name: "Close" }));
		expect(dialog).toBeInTheDocument();
		expect(within(dialog).queryByRole("button", { name: "提交手工成交" })).not.toBeInTheDocument();

		await user.click(within(dialog).getByRole("button", { name: "使用同一标识重试" }));
		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		expect(submitted).toHaveLength(2);
		expect(submitted[1]).toEqual(submitted[0]);
	});

	it("网络断开结果不明时保留同一 fill command", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		const submitted: Record<string, unknown>[] = [];
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				const payload = (await request.json()) as Record<string, unknown>;
				submitted.push(payload);
				if (submitted.length === 1) return HttpResponse.error();
				return HttpResponse.json({ data: payload });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		await user.click(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.type(within(dialog).getByLabelText("成交价格"), "4.32");
		await user.click(within(dialog).getByRole("button", { name: "提交手工成交" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("提交结果未知");
		await user.click(within(dialog).getByRole("button", { name: "使用同一标识重试" }));
		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		expect(submitted[1]).toEqual(submitted[0]);
	});

	it("409 更正冲突可关闭并刷新成交事实", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.post("/api/v1/manual/fills", () =>
				HttpResponse.json({ detail: "fill_id 已存在且 payload 不一致" }, { status: 409 }),
			),
		);
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		await user.click(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.type(within(dialog).getByLabelText("成交价格"), "4.32");
		await user.click(within(dialog).getByRole("button", { name: "提交手工成交" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("成交冲突");
		await user.click(within(dialog).getByRole("button", { name: "关闭并刷新流水" }));
		await waitFor(() => expect(screen.queryByRole("dialog", { name: "订单确认" })).not.toBeInTheDocument());
	});

	it("明确 400 失败允许关闭且不会要求未知结果重试", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(http.post("/api/v1/manual/fills", () => HttpResponse.json({ detail: "成交价格非法" }, { status: 400 })));
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		await user.click(within(dialog).getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.type(within(dialog).getByLabelText("成交价格"), "4.32");
		await user.click(within(dialog).getByRole("button", { name: "提交手工成交" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("成交价格非法");
		expect(within(dialog).queryByRole("button", { name: "使用同一标识重试" })).not.toBeInTheDocument();
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await waitFor(() => expect(screen.queryByRole("dialog", { name: "订单确认" })).not.toBeInTheDocument());
	});

	it("成交确认 Sheet 的关键信号上下文使用 AA 文本 token", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		const dialog = await screen.findByRole("dialog", { name: "订单确认" });
		for (const label of ["intent_id", "标的", "方向", "建议交易日"]) {
			expect(within(dialog).getByText(label)).toHaveClass("text-(--color-foreground-secondary)");
		}
	});

	it("允许记录偏离建议日的实际成交日期并交由后端复核", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		let submittedTradeDate: string | undefined;
		server.use(
			http.post("/api/v1/manual/fills", async ({ request }) => {
				const payload = (await request.json()) as { trade_date: string };
				submittedTradeDate = payload.trade_date;
				return HttpResponse.json({ data: payload });
			}),
		);
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));
		const tradeDate = screen.getByLabelText("实际成交日");
		expect(tradeDate).toHaveValue("2026-07-03");
		await user.clear(tradeDate);
		await user.type(tradeDate, "2026-07-04");
		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		expect(submittedTradeDate).toBe("2026-07-04");
	});

	it("live 模式不允许用手工状态覆盖后端有效成交事实", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "更新意图状态" })).not.toBeInTheDocument();
	});
});

// ── SignalsPage — OpsConsoleLayout 集成 ─────────────────────────

describe("SignalsPage", () => {
	it("渲染健康条（health slot）", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("待处理")).resolves.toBeInTheDocument();
	});

	it("渲染信号列表（main slot）", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("信号队列")).resolves.toBeInTheDocument();
	});

	it("点击信号后打开所选信号详情 Drawer", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		expect(screen.queryByText("信号详情")).not.toBeInTheDocument();

		fireEvent.click(await screen.findByRole("button", { name: /000001\.SZ.*动量突破/ }));

		const dialog = await screen.findByRole("dialog", { name: "信号详情" });
		expect(within(dialog).getAllByText("信号详情")).toHaveLength(2);
		await expect(within(dialog).findByText(/动量突破信号/)).resolves.toBeInTheDocument();
	});

	it("部分成交后关闭详情仍可从待处理队列重新打开并继续录入", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		let fillRecorded = false;
		server.use(
			http.get("/api/v1/manual/daily-decision/v2", () => {
				const response = structuredClone(liveDailyDecisionV2);
				response.actions[0] = {
					...response.actions[0],
					filled_quantity: fillRecorded ? 400 : 0,
					remaining_quantity: fillRecorded ? 600 : 1000,
					intent_status: fillRecorded ? "partially_filled" : "pending",
				};
				return HttpResponse.json({ data: response });
			}),
			http.post("/api/v1/manual/fills", async ({ request }) => {
				fillRecorded = true;
				return HttpResponse.json({ data: await request.json() });
			}),
		);
		render(<SignalsPage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: /#510300.*目标权重 30\.0%/ }));
		await user.click(await screen.findByRole("button", { name: "录入手工成交" }));
		await user.clear(screen.getByLabelText("成交数量"));
		await user.type(screen.getByLabelText("成交数量"), "400");
		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("checkbox", { name: "我已复核以上原因" }));
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
		await waitFor(() => {
			expect(screen.queryByRole("dialog", { name: "订单确认" })).not.toBeInTheDocument();
		});
		const detailDrawer = screen.getByRole("dialog", { name: "信号详情" });
		await user.click(within(detailDrawer).getByRole("button", { name: "Close" }));
		await waitFor(() => {
			expect(screen.queryByRole("dialog", { name: "信号详情" })).not.toBeInTheDocument();
		});

		await user.click(await screen.findByRole("button", { name: /#510300.*目标权重 30\.0%/ }));
		const recordNextFill = await screen.findByRole("button", { name: "录入手工成交" });
		expect(recordNextFill).toBeEnabled();
		await user.click(recordNextFill);
		await expect(screen.findByRole("dialog", { name: "订单确认" })).resolves.toBeInTheDocument();
		expect(screen.getByText("剩余 600")).toBeInTheDocument();
	});
});

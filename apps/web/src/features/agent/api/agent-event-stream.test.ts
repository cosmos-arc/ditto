import { describe, expect, it, vi } from "vitest";
import { createRecoverableAgentEventStream, parseAgentSse } from "./agent-event-stream";

const event = (id: number, type = "run_progressed") =>
	`id: ${id}\nevent: ${type}\ndata: {"event_id":${id},"event_type":"${type}","payload_hash":"${"a".repeat(64)}"}\n\n`;

describe("recoverable Agent event stream", () => {
	it("deduplicates replayed notifications and rejects out-of-order IDs", () => {
		const parsed = parseAgentSse(`${event(5)}${event(4)}${event(5)}${event(6)}`, 4);
		expect(parsed.map((item) => item.id)).toEqual([5, 6]);
	});

	it("resumes with Last-Event-ID and stops at a terminal event", async () => {
		const fetcher = vi.fn<typeof fetch>(async (_input, init) => {
			expect(new Headers(init?.headers).get("Last-Event-ID")).toBe("7");
			return new Response(event(8, "run_completed"), {
				status: 200,
				headers: { "Content-Type": "text/event-stream" },
			});
		});
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			path: "/v1/agent/runs/run-1/events",
			initialCursor: 7,
			fetcher,
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 8 })));
		expect(onState).toHaveBeenLastCalledWith("complete");
		expect(fetcher).toHaveBeenCalledTimes(1);
	});

	it("fails closed when the persisted cursor has expired", async () => {
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			path: "/v1/agent/runs/run-1/events",
			initialCursor: 99,
			fetcher: vi.fn<typeof fetch>(async () => new Response(null, { status: 410 })),
			onEvent: vi.fn(),
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenCalledWith("cursor-expired"));
		expect(stream.cursor).toBe(99);
	});
});

import { describe, expect, it, vi } from "vitest";
import type { EventStreamRequest } from "@/api";
import { createApiClient } from "@/api/transport";
import { createRecoverableAgentEventStream, parseAgentSse } from "./agent-event-stream";

const eventHash = (sequence: number) => (sequence + 2).toString(16).padStart(64, "0");

const event = (id: number, type = "provider_attempt", overrides: Readonly<Record<string, unknown>> = {}) => {
	const sequence = typeof overrides["run_sequence"] === "number" ? overrides["run_sequence"] : id;
	return `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({
		schema_version: 1,
		event_id: id,
		run_id: "run-1",
		run_sequence: sequence,
		event_type: type,
		payload_hash: "a".repeat(64),
		occurred_at: "2026-09-04T00:00:00Z",
		prev_hash: sequence === 1 ? null : eventHash(sequence - 1),
		event_hash: eventHash(sequence),
		...overrides,
	})}\n\n`;
};

const campaignEvent = (
	id: number,
	status: string,
	type = "candidate_dispatched",
	previousStatus: string | null = id === 1 ? null : "running",
) =>
	`id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({
		schema_version: 1,
		event_id: id,
		durable_event_id: `campaign-event-${id}`,
		campaign_id: "campaign-1",
		event_type: type,
		previous_status: previousStatus,
		status,
		payload_hash: "d".repeat(64),
		occurred_at: "2026-09-04T00:00:00Z",
	})}\n\n`;

function streamRequest(fetcher: typeof fetch): EventStreamRequest {
	return createApiClient({
		apiBaseUrl: "http://127.0.0.1:8000",
		apiContractVersion: "v1",
		fetcher: (request) => fetcher(request),
	}).getEventStream;
}

function errorResponse(status: number): Response {
	return Response.json({ error_code: `HTTP_${status}`, detail: `HTTP ${status}` }, { status });
}

describe("recoverable Agent event stream", () => {
	it("deduplicates a validated stale replay prefix and rejects out-of-order IDs", () => {
		const parsed = parseAgentSse(`${event(4)}${event(5)}${event(6)}`, 4);
		expect(parsed.map((item) => item.id)).toEqual([5, 6]);
		expect(() => parseAgentSse(`${event(5)}${event(4)}`, 4)).toThrow(/increasing/u);
	});

	it("ignores SSE comments while preserving the durable data record", () => {
		const parsed = parseAgentSse(`: heartbeat\n${event(1)}`);
		expect(parsed).toHaveLength(1);
		expect(parsed[0]).toMatchObject({ id: 1, eventType: "provider_attempt" });
	});

	it("validates stale replay payloads before deduplicating them", () => {
		const malformedStale = event(5).replace(`"payload_hash":"${"a".repeat(64)}"`, '"payload_hash":"weak"');
		expect(() => parseAgentSse(malformedStale, 5, { kind: "runs", identity: "run-1" })).toThrow(/payload_hash/u);
	});

	it("fails closed when adjacent Run sequence or previous hash continuity breaks", () => {
		expect(() =>
			parseAgentSse(`${event(1, "run_started")}${event(3, "provider_attempt")}`, 0, {
				kind: "runs",
				identity: "run-1",
			}),
		).toThrow(/run_sequence/u);
		expect(() =>
			parseAgentSse(`${event(1, "run_started")}${event(2, "provider_attempt", { prev_hash: "f".repeat(64) })}`, 0, {
				kind: "runs",
				identity: "run-1",
			}),
		).toThrow(/prev_hash/u);
	});

	it("fails closed when Campaign ordinal or previous status continuity breaks", () => {
		expect(() =>
			parseAgentSse(`${campaignEvent(1, "draft", "campaign_created")}${campaignEvent(3, "running")}`, 0, {
				kind: "campaigns",
				identity: "campaign-1",
			}),
		).toThrow(/event_id/u);
		expect(() =>
			parseAgentSse(
				`${campaignEvent(1, "draft", "campaign_created")}${campaignEvent(2, "running", "candidate_dispatched", "authorized")}`,
				0,
				{ kind: "campaigns", identity: "campaign-1" },
			),
		).toThrow(/previous_status/u);
	});

	it("rejects an unknown terminal-looking event and any durable frame after a terminal event", () => {
		expect(() => parseAgentSse(event(1, "audit_completed"), 0, { kind: "runs", identity: "run-1" })).toThrow(
			/event_type/u,
		);
		expect(() =>
			parseAgentSse(`${event(1, "run_completed")}${event(2, "provider_attempt")}`, 0, {
				kind: "runs",
				identity: "run-1",
			}),
		).toThrow(/terminal/u);
	});

	it("accepts a post-terminal Campaign race receipt while stopping on the terminal event kind", () => {
		const replay = `${campaignEvent(1, "draft", "campaign_created")}${campaignEvent(
			2,
			"completed",
			"campaign_completed",
			"draft",
		)}${campaignEvent(3, "completed", "candidate_dispatched", "completed")}`;

		expect(parseAgentSse(replay, 0, { kind: "campaigns", identity: "campaign-1" })).toHaveLength(3);
	});

	it("fails closed instead of silently dropping a malformed durable event", () => {
		const malformed = event(5).replace(`"payload_hash":"${"a".repeat(64)}"`, '"payload_hash":"weak"');
		expect(() => parseAgentSse(malformed, 4, { kind: "runs", identity: "run-1" })).toThrow(/payload_hash/u);
	});

	it.each([
		["missing id", event(5).replace("id: 5\n", ""), /id/u],
		["malformed id", event(5).replace("id: 5", "id: invalid"), /id/u],
		["missing data", event(5).replace(/^data:.*\n\n$/mu, ""), /data/u],
	] as const)("fails closed for a durable event with %s", (_case, input, expectedError) => {
		expect(() => parseAgentSse(input, 4, { kind: "runs", identity: "run-1" })).toThrow(expectedError);
	});

	it("halts without retrying after a payload runtime-contract violation", async () => {
		const malformed = event(1).replace(`"payload_hash":"${"a".repeat(64)}"`, '"payload_hash":"weak"');
		const fetcher = vi
			.fn<typeof fetch>()
			.mockResolvedValueOnce(new Response(malformed, { status: 200, headers: { "Content-Type": "text/event-stream" } }))
			.mockResolvedValueOnce(
				new Response(event(1, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			minimumRetryMs: 1,
			maximumRetryMs: 1,
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenCalledWith("error"));
		await new Promise((resolve) => setTimeout(resolve, 20));
		expect(onState).toHaveBeenLastCalledWith("error");
		expect(onEvent).not.toHaveBeenCalled();
		expect(fetcher).toHaveBeenCalledOnce();
	});

	it("preserves the Run chain checkpoint across reconnects", async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockResolvedValueOnce(
				new Response(event(1, "run_started"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			)
			.mockResolvedValueOnce(
				new Response(event(3, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			minimumRetryMs: 1,
			maximumRetryMs: 1,
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith("error"));
		expect(onEvent.mock.calls.map(([notification]) => notification.id)).toEqual([1]);
		expect(fetcher).toHaveBeenCalledTimes(2);
		expect(stream.cursor).toBe(1);
	});

	it("does not start a request when the connecting callback synchronously stops the stream", async () => {
		const fetcher = vi.fn<typeof fetch>(async () => errorResponse(500));
		let stream: ReturnType<typeof createRecoverableAgentEventStream>;
		const onState = vi.fn((state) => {
			if (state === "connecting") stream.stop();
		});
		stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent: vi.fn(),
			onState,
		});

		stream.start();
		await Promise.resolve();
		expect(fetcher).not.toHaveBeenCalled();
		expect(onState).toHaveBeenLastCalledWith("stopped");
	});

	it("does not consume a response body when the open callback synchronously stops the stream", async () => {
		const response = new Response(event(1, "run_completed"), {
			status: 200,
			headers: { "Content-Type": "text/event-stream" },
		});
		const readBody = vi.spyOn(response, "text");
		const request = (async () => response) as EventStreamRequest;
		let stream: ReturnType<typeof createRecoverableAgentEventStream>;
		const onState = vi.fn((state) => {
			if (state === "open") stream.stop();
		});
		stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request,
			onEvent: vi.fn(),
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith("stopped"));
		expect(readBody).not.toHaveBeenCalled();
	});

	it("does not retain a retry timer when the reconnecting callback synchronously stops the stream", async () => {
		vi.useFakeTimers();
		try {
			let stream: ReturnType<typeof createRecoverableAgentEventStream>;
			const onState = vi.fn((state) => {
				if (state === "reconnecting") stream.stop();
			});
			stream = createRecoverableAgentEventStream({
				target: { kind: "runs", identity: "run-1" },
				request: streamRequest(vi.fn<typeof fetch>(async () => errorResponse(500))),
				onEvent: vi.fn(),
				onState,
			});

			stream.start();
			await vi.advanceTimersByTimeAsync(0);
			expect(onState).toHaveBeenLastCalledWith("stopped");
			expect(vi.getTimerCount()).toBe(0);
		} finally {
			vi.useRealTimers();
		}
	});

	it("cleans up and permanently halts when a state callback throws", async () => {
		let listener: (() => void) | undefined;
		const visibility = {
			visibilityState: "visible" as DocumentVisibilityState,
			addEventListener: (_type: "visibilitychange", next: () => void) => {
				listener = next;
			},
			removeEventListener: (_type: "visibilitychange", next: () => void) => {
				if (listener === next) listener = undefined;
			},
		};
		const fetcher = vi.fn<typeof fetch>(async () => errorResponse(500));
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent: vi.fn(),
			onState: () => {
				throw new Error("consumer failed");
			},
			visibilityTarget: visibility,
		});

		stream.start();
		await Promise.resolve();
		stream.start();

		expect(fetcher).not.toHaveBeenCalled();
		expect(listener).toBeUndefined();
	});

	it("resumes with Last-Event-ID and stops at a terminal event", async () => {
		const fetcher = vi.fn<typeof fetch>(async (input) => {
			expect(new Request(input).headers.get("Last-Event-ID")).toBe("7");
			return new Response(event(8, "run_completed"), {
				status: 200,
				headers: { "Content-Type": "text/event-stream" },
			});
		});
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			initialCursor: 7,
			request: streamRequest(fetcher),
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
			target: { kind: "runs", identity: "run-1" },
			initialCursor: 99,
			request: streamRequest(vi.fn<typeof fetch>(async () => errorResponse(410))),
			onEvent: vi.fn(),
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenCalledWith("cursor-expired"));
		expect(stream.cursor).toBe(99);
	});

	it.each([
		["missing", undefined],
		["wrong", "application/json"],
	] as const)("halts instead of consuming a 200 stream with %s Content-Type", async (_case, contentType) => {
		const fetcher = vi.fn<typeof fetch>(
			async () =>
				new Response(event(1, "run_completed"), {
					status: 200,
					...(contentType ? { headers: { "Content-Type": contentType } } : {}),
				}),
		);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenCalledWith("error"));
		expect(onEvent).not.toHaveBeenCalled();
		expect(fetcher).toHaveBeenCalledOnce();
		stream.stop();
	});

	it.each([
		[401, "authorization-required"],
		[403, "authorization-required"],
		[404, "not-found"],
	] as const)("halts an HTTP %i stream as %s without retrying", async (status, expectedState) => {
		const fetcher = vi.fn<typeof fetch>(async () => errorResponse(status));
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent: vi.fn(),
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith(expectedState));
		expect(fetcher).toHaveBeenCalledOnce();
		stream.stop();
	});

	it.each([400, 422] as const)("halts an HTTP %i validation failure without retrying", async (status) => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockResolvedValueOnce(errorResponse(status))
			.mockResolvedValueOnce(
				new Response(event(1, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			);
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent: vi.fn(),
			onState,
			minimumRetryMs: 1,
			maximumRetryMs: 1,
		});

		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith("error"));
		await new Promise((resolve) => setTimeout(resolve, 10));
		expect(fetcher).toHaveBeenCalledOnce();
	});

	it.each([
		[{ initialCursor: -1 }, /initialCursor/u],
		[{ initialCursor: Number.MAX_SAFE_INTEGER + 1 }, /initialCursor/u],
		[{ minimumRetryMs: 0 }, /minimumRetryMs/u],
		[{ maximumRetryMs: Number.NaN }, /maximumRetryMs/u],
		[{ minimumRetryMs: 20, maximumRetryMs: 10 }, /retry/u],
	] as const)("rejects invalid stream controls %#", (controls, expected) => {
		expect(() =>
			createRecoverableAgentEventStream({
				target: { kind: "runs", identity: "run-1" },
				onEvent: vi.fn(),
				...controls,
			}),
		).toThrow(expected);
	});

	it("uses default cursor, retry bounds, and global fetcher when optional transport settings are absent", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () => errorResponse(401));
		vi.stubGlobal("fetch", fetchMock);
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "campaigns", identity: "campaign-1" },
			onEvent: vi.fn(),
			onState,
		});

		expect(stream.cursor).toBe(0);
		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith("authorization-required"));
		expect(fetchMock).toHaveBeenCalledOnce();
		vi.unstubAllGlobals();
	});

	it("pauses a visible stream on tab hiding and resumes it with reconnect state", async () => {
		let listener: (() => void) | undefined;
		const visibility = {
			visibilityState: "visible" as DocumentVisibilityState,
			addEventListener: (_type: "visibilitychange", next: () => void) => {
				listener = next;
			},
			removeEventListener: (_type: "visibilitychange", next: () => void) => {
				if (listener === next) listener = undefined;
			},
		};
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementationOnce(
				async (input) =>
					new Promise<Response>((_resolve, reject) => {
						new Request(input).signal.addEventListener(
							"abort",
							() => reject(new DOMException("visibility pause", "AbortError")),
							{
								once: true,
							},
						);
					}),
			)
			.mockResolvedValueOnce(
				new Response(event(1, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			);
		const onState = vi.fn();
		const onEvent = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent,
			onState,
			visibilityTarget: visibility,
		});

		stream.start();
		stream.start();
		await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
		visibility.visibilityState = "hidden";
		listener?.();
		expect(onState).toHaveBeenLastCalledWith("paused");
		visibility.visibilityState = "visible";
		listener?.();
		await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 1 })));
		expect(onState).toHaveBeenCalledWith("reconnecting");
		expect(onState).toHaveBeenLastCalledWith("complete");
	});

	it("connects when a stream started in a hidden document becomes visible", async () => {
		let listener: (() => void) | undefined;
		const visibility = {
			visibilityState: "hidden" as DocumentVisibilityState,
			addEventListener: (_type: "visibilitychange", next: () => void) => {
				listener = next;
			},
			removeEventListener: (_type: "visibilitychange", next: () => void) => {
				if (listener === next) listener = undefined;
			},
		};
		const fetcher = vi.fn<typeof fetch>(
			async () =>
				new Response(event(1, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
		);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent,
			onState,
			visibilityTarget: visibility,
		});

		stream.start();
		expect(fetcher).not.toHaveBeenCalled();
		expect(onState).toHaveBeenLastCalledWith("paused");
		visibility.visibilityState = "visible";
		listener?.();

		await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 1 })));
		expect(fetcher).toHaveBeenCalledOnce();
		expect(onState).toHaveBeenLastCalledWith("complete");
	});

	it("does not deliver a response that completes after stop aborts its request", async () => {
		let resolveResponse: ((response: Response) => void) | undefined;
		const fetcher = vi.fn<typeof fetch>(
			async () =>
				new Promise<Response>((resolve) => {
					resolveResponse = resolve;
				}),
		);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
		stream.stop();
		resolveResponse?.(
			new Response(event(1, "run_completed"), {
				status: 200,
				headers: { "Content-Type": "text/event-stream" },
			}),
		);
		await new Promise((resolve) => setTimeout(resolve, 10));

		expect(onEvent).not.toHaveBeenCalled();
		expect(onState).toHaveBeenLastCalledWith("stopped");
	});

	it("does not deliver a response that completes after visibility pause aborts its request", async () => {
		let listener: (() => void) | undefined;
		const visibility = {
			visibilityState: "visible" as DocumentVisibilityState,
			addEventListener: (_type: "visibilitychange", next: () => void) => {
				listener = next;
			},
			removeEventListener: (_type: "visibilitychange", next: () => void) => {
				if (listener === next) listener = undefined;
			},
		};
		let resolveResponse: ((response: Response) => void) | undefined;
		const fetcher = vi.fn<typeof fetch>(
			async () =>
				new Promise<Response>((resolve) => {
					resolveResponse = resolve;
				}),
		);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			onEvent,
			onState,
			visibilityTarget: visibility,
		});

		stream.start();
		await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
		visibility.visibilityState = "hidden";
		listener?.();
		resolveResponse?.(
			new Response(event(1, "run_completed"), {
				status: 200,
				headers: { "Content-Type": "text/event-stream" },
			}),
		);
		await new Promise((resolve) => setTimeout(resolve, 10));

		expect(onEvent).not.toHaveBeenCalled();
		expect(onState).toHaveBeenLastCalledWith("paused");
	});

	it("retries an HTTP failure, advances a non-terminal cursor, then halts on terminal truth", async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockResolvedValueOnce(errorResponse(500))
			.mockResolvedValueOnce(new Response(event(1), { status: 200, headers: { "Content-Type": "text/event-stream" } }))
			.mockResolvedValueOnce(
				new Response(event(2, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				}),
			);
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			request: streamRequest(fetcher),
			minimumRetryMs: 1,
			maximumRetryMs: 1,
			onEvent,
			onState,
		});

		stream.start();
		stream.start();
		await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith("complete"));
		expect(onEvent.mock.calls.map(([notification]) => notification.id)).toEqual([1, 2]);
		expect(fetcher).toHaveBeenCalledTimes(3);
		expect(stream.cursor).toBe(2);
	});

	it("reconnects after a transport failure and resumes from the last durable cursor", async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockRejectedValueOnce(new TypeError("simulated network disconnect"))
			.mockImplementationOnce(async (input) => {
				expect(new Request(input).headers.get("Last-Event-ID")).toBe("11");
				return new Response(event(12, "run_completed"), {
					status: 200,
					headers: { "Content-Type": "text/event-stream" },
				});
			});
		const onEvent = vi.fn();
		const onState = vi.fn();
		const stream = createRecoverableAgentEventStream({
			target: { kind: "runs", identity: "run-1" },
			initialCursor: 11,
			request: streamRequest(fetcher),
			minimumRetryMs: 1,
			maximumRetryMs: 1,
			onEvent,
			onState,
		});

		stream.start();
		await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 12 })));
		expect(onState).toHaveBeenCalledWith("error");
		expect(onState).toHaveBeenCalledWith("reconnecting");
		expect(onState).toHaveBeenLastCalledWith("complete");
		expect(fetcher).toHaveBeenCalledTimes(2);
		expect(stream.cursor).toBe(12);
	});
});

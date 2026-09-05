import type { Client, ClientPathsWithMethod } from "openapi-fetch";
import { describe, expect, it } from "vitest";
import type { components, paths } from "./generated/schema";
import type { EventStreamPath, OperationError, OperationInit, OperationSuccess, SuccessStatusKey } from "./transport";

type Api = Client<paths>;
type Equal<Left, Right> =
	(<Value>() => Value extends Left ? 1 : 2) extends <Value>() => Value extends Right ? 1 : 2 ? true : false;
type Assert<Value extends true> = Value;
type Not<Value extends boolean> = Value extends true ? false : true;
type Assignable<From, To> = From extends To ? true : false;

type GetPaths = ClientPathsWithMethod<Api, "get">;
type PostPaths = ClientPathsWithMethod<Api, "post">;
type StatusInit = Exclude<OperationInit<"get", "/api/v1/status">, undefined>;
type CreateStrategyInit = Exclude<OperationInit<"post", "/api/v1/strategies">, undefined>;

type ContractAssertions = readonly [
	Assert<Not<Assignable<"/api/v1/not-real", GetPaths>>>,
	Assert<Not<Assignable<"/api/v1/status", PostPaths>>>,
	Assert<Not<Assignable<{ params: { header: { "X-Ditto-API-Contract-Version": "v2" } } }, StatusInit>>>,
	Assert<Not<Assignable<{ body: { name: number } }, CreateStrategyInit>>>,
	Assert<Not<"parseAs" extends keyof StatusInit ? true : false>>,
	Assert<Not<"baseUrl" extends keyof StatusInit ? true : false>>,
	Assert<Not<"fetch" extends keyof StatusInit ? true : false>>,
	Assert<Not<"headers" extends keyof StatusInit ? true : false>>,
	Assert<Not<"pathSerializer" extends keyof StatusInit ? true : false>>,
	Assert<Not<"bodySerializer" extends keyof StatusInit ? true : false>>,
	Assert<Equal<EventStreamPath, "/api/v1/agent/campaigns/{campaign_id}/events" | "/api/v1/agent/runs/{run_id}/events">>,
	Assert<Equal<OperationSuccess<"get", "/api/v1/status">["api_contract_version"], string>>,
	Assert<Equal<OperationError<"get", "/api/v1/status">, components["schemas"]["ErrorResponse"]>>,
	Assert<Equal<SuccessStatusKey<299>, 299>>,
	Assert<Equal<SuccessStatusKey<300>, never>>,
];

describe("typed transport contract", () => {
	it("keeps path, method, parameter, body, success and error assumptions operation-derived", () => {
		const assertions: ContractAssertions = [
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
		];
		expect(assertions).toEqual([
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
			true,
		]);
	});
});

import type { components, operations } from "./generated/schema";

export type MarketContextContract = components["schemas"]["MarketContextResponse"];
export type MarketContextQuery = operations["market_get_context"]["parameters"]["query"];

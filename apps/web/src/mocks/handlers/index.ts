import type { RequestHandler } from "msw";
import { platformHandlers } from "./platform";
import { homeHandlers } from "./home";
import { marketsHandlers } from "./markets";
import { researchHandlers } from "./research";
import { tradingHandlers } from "./trading";
import { instrumentsHandlers } from "./instruments";
import { backtestHandlers } from "./backtest";
import { strategyHandlers } from "./strategy";
import { regimeHandlers } from "./regime";
import { intelligenceHandlers } from "./intelligence";
import { aiHandlers } from "./ai";
import { ordersHandlers } from "./orders";
import { riskHandlers } from "./risk";

export const handlers: RequestHandler[] = [
	...platformHandlers,
	...homeHandlers,
	...marketsHandlers,
	...researchHandlers,
	...tradingHandlers,
	...instrumentsHandlers,
	...backtestHandlers,
	...strategyHandlers,
	...regimeHandlers,
	...intelligenceHandlers,
	...aiHandlers,
	...ordersHandlers,
	...riskHandlers,
];

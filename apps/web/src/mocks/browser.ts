import { setupWorker } from "msw/browser";
import type { RequestHandler } from "msw";

export const worker = setupWorker(...([] as RequestHandler[]));

import { useParams } from "@tanstack/react-router";
import { useState } from "react";
import { StatusBar, StudioLayout } from "@/features/shell";
import type { SpecValidation } from "@/types/strategy";
import { serializeStrategySpec } from "../api/mappers";
import { useStrategy, useStrategyValidation } from "../hooks";
import { NodeLibrary } from "./node-library";
import { StrategyEditor } from "./strategy-editor";
import { StrategyHeader } from "./strategy-header";
import { StrategyInspector } from "./strategy-inspector";
import { StudioModeBar } from "./studio-mode-bar";
import { ValidationPanel } from "./validation-panel";

const STUDIO_MODES = [
	{ id: "form", label: "Form Builder" },
	{ id: "code", label: "Code Editor" },
] as const;

const DEFAULT_STRATEGY_ID = "seed_etf_industry_rotation";

export function StrategyPage() {
	const { id } = useParams({ strict: false }) as { id?: string };
	const strategyId = id ?? DEFAULT_STRATEGY_ID;
	const breadcrumbs = ["研究", "策略", strategyId] as const;

	const { data } = useStrategy(strategyId);
	const validate = useStrategyValidation();
	const [validation, setValidation] = useState<SpecValidation | null>(null);

	function handleValidate() {
		if (!data) return;
		validate.mutate(
			{
				strategyId,
				version: data.version,
				specJson: serializeStrategySpec(data.spec),
			},
			{ onSuccess: setValidation },
		);
	}

	return (
		<>
			<StudioLayout
				className="pb-(--height-status-bar)"
				modes={
					<div data-info-level="l1" data-info-unit="studio-mode-bar">
						<StudioModeBar modes={STUDIO_MODES} breadcrumbs={breadcrumbs} />
					</div>
				}
				source={
					<div data-info-level="l1" data-info-unit="node-library">
						<NodeLibrary />
					</div>
				}
				main={
					<div className="flex flex-col gap-(--section-gap)">
						<div data-info-level="l1" data-info-unit="strategy-header">
							<StrategyHeader id={strategyId} />
						</div>
						<div data-info-level="l1" data-info-unit="strategy-code">
							<StrategyEditor id={strategyId} />
						</div>
						<div data-info-level="l2" data-info-unit="validation-panel">
							<div className="flex flex-col gap-2 p-(--density-panel-padding)">
								<ValidationPanel validation={validation} isValidating={validate.isPending} />
								<button
									type="button"
									onClick={handleValidate}
									disabled={!data || validate.isPending}
									className="self-start rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover) disabled:opacity-50"
								>
									校验 Spec
								</button>
							</div>
						</div>
					</div>
				}
				inspector={
					<div data-info-level="l2" data-info-unit="strategy-inspector">
						<StrategyInspector id={strategyId} />
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}

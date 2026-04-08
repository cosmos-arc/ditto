import { createFileRoute } from "@tanstack/react-router";
import { StudioLayout } from "@/features/shell";
import { Placeholder } from "@/components/placeholder";

export const Route = createFileRoute("/research/strategy-studio")({
	component: StrategyStudioPage,
	handle: { title: "Strategy Studio" },
});

function StrategyStudioPage() {
	return (
		<StudioLayout
			source={<Placeholder label="Sources Panel" />}
			main={<Placeholder label="Strategy Editor" />}
			inspector={<Placeholder label="Inspector Panel" />}
			logs={<Placeholder label="Logs" />}
		/>
	);
}

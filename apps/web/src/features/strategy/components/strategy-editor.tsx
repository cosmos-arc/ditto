import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategyVersions } from "../hooks/use-strategy-versions";

interface StrategyEditorProps {
	readonly id: string;
}

function StrategyEditorContent({ id }: StrategyEditorProps) {
	const { data, isLoading, isError } = useStrategyVersions(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data || data.length === 0) {
		throw new Error("Failed to load strategy versions");
	}

	const latest = data[data.length - 1];

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<ContextSection title="最新版本">
				<pre className="overflow-auto p-[var(--density-panel-padding)] text-sm text-(--color-foreground-tertiary)">
					<code>{`version: ${latest.version}\nspec_hash: ${latest.specHash}\nstate: ${latest.state}\nreview: ${latest.reviewOutcome}`}</code>
				</pre>
			</ContextSection>
		</div>
	);
}

export function StrategyEditor(props: StrategyEditorProps) {
	return (
		<DittoErrorBoundary>
			<StrategyEditorContent {...props} />
		</DittoErrorBoundary>
	);
}

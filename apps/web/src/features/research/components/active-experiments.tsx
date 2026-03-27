import type { Experiment } from "../types";

const MOCK_EXPERIMENTS: Experiment[] = [
	{ name: "GPU-Worker_Alpha_Search", progress: 82 },
	{ name: "Monte_Carlo_Stress_Test", progress: 45 },
];

function ProgressBar({ value }: { readonly value: number }) {
	return (
		<div className="h-1 w-full overflow-hidden rounded-full bg-surface-raised">
			<div
				className="h-full rounded-full bg-blue-700 transition-all duration-300"
				style={{ width: `${value}%` }}
			/>
		</div>
	);
}

export function ActiveExperiments() {
	return (
		<div className="rounded-xl border border-outline/30 bg-surface-panel p-4 shadow-sm">
			<div className="mb-4 flex items-center justify-between">
				<span className="text-sm font-bold tracking-tight">Active Experiments</span>
				<span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">
					3 ACTIVE
				</span>
			</div>

			<div className="space-y-4">
				{MOCK_EXPERIMENTS.map((exp) => (
					<div key={exp.name}>
						<div className="mb-1.5 flex items-center justify-between text-xs">
							<span className="text-text-primary">{exp.name}</span>
							<span className="font-mono text-blue-700">{exp.progress}%</span>
						</div>
						<ProgressBar value={exp.progress} />
					</div>
				))}
			</div>
		</div>
	);
}

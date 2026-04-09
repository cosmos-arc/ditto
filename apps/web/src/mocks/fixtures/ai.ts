import type {
	AiPulseResponse,
	GetAgentQuickViewResponse,
	GetCopilotQuickViewResponse,
	GetCopilotSessionsResponse,
	CopilotMessage,
	GetAgentPlansResponse,
	GetAgentRunsResponse,
	GetAgentFindingsResponse,
} from "@/types";

// === AI 脉动 ===

export const mockAiPulse: AiPulseResponse = {
	runningPlans: 3,
	pendingApprovals: 2,
	activeCopilotSessions: 5,
} as const satisfies AiPulseResponse;

// === Agent 快览 ===

export const mockAgentQuickView: GetAgentQuickViewResponse = {
	plans: [
		{
			id: "plan-001",
			name: "因子池优化扫描",
			status: "running",
			progress: 68,
		},
		{
			id: "plan-002",
			name: "风控参数调优",
			status: "pending",
			progress: 0,
		},
		{
			id: "plan-003",
			name: "组合权重再平衡",
			status: "completed",
			progress: 100,
		},
	] as const,
	recentFindings: [
		{
			id: "finding-001",
			text: "动量因子 IC 连续 3 周下降至 0.028，低于阈值 0.04",
			confidence: 0.92,
			createdAt: "2026-04-08T09:15:00Z",
		},
		{
			id: "finding-002",
			text: "波动率模型建议将创业板止损从 -5% 收紧至 -3.5%",
			confidence: 0.87,
			createdAt: "2026-04-08T08:45:00Z",
		},
	] as const,
	recentCompleted: [
		{
			id: "run-003",
			name: "Q1 组合归因分析",
			completedAt: "2026-04-07T18:30:00Z",
			resultSummary: "科技板块贡献 62% 超额收益，消费板块拖累 -1.2%",
		},
	] as const,
} as const satisfies GetAgentQuickViewResponse;

// === Copilot 快览 ===

export const mockCopilotQuickView: GetCopilotQuickViewResponse = {
	sessions: [
		{
			id: "session-001",
			title: "因子衰减分析讨论",
			mode: "research",
			updatedAt: "2026-04-08T09:20:00Z",
			messageCount: 12,
		},
		{
			id: "session-002",
			title: "调仓建议方案",
			mode: "trading",
			updatedAt: "2026-04-08T08:30:00Z",
			messageCount: 8,
		},
		{
			id: "session-003",
			title: "回测框架使用指南",
			mode: "coding",
			updatedAt: "2026-04-07T17:00:00Z",
			messageCount: 5,
		},
	] as const,
	recentOutputs: [
		{
			id: "output-001",
			sessionId: "session-001",
			type: "factor_analysis",
			summary: "动量因子 60 日 IC 序列 + 衰减趋势可视化",
			createdAt: "2026-04-08T09:18:00Z",
		},
		{
			id: "output-002",
			sessionId: "session-002",
			type: "trading_plan",
			summary: "基于当前持仓的 3 档调仓方案对比",
			createdAt: "2026-04-08T08:25:00Z",
		},
	] as const,
	savedNotes: [
		{
			id: "note-001",
			title: "因子衰减应对策略",
			content: "短期降低动量因子权重，增加价值因子配置；长期考虑引入机器学习因子替换",
			createdAt: "2026-04-08T09:22:00Z",
		},
	] as const,
} as const satisfies GetCopilotQuickViewResponse;

// === Copilot 会话列表 ===

export const mockCopilotSessions: GetCopilotSessionsResponse = {
	sessions: [
		{
			id: "session-001",
			title: "因子衰减分析讨论",
			mode: "research",
			messages: [],
			createdAt: "2026-04-08T08:00:00Z",
			updatedAt: "2026-04-08T09:20:00Z",
		},
		{
			id: "session-002",
			title: "调仓建议方案",
			mode: "trading",
			messages: [],
			createdAt: "2026-04-08T07:30:00Z",
			updatedAt: "2026-04-08T08:30:00Z",
		},
		{
			id: "session-003",
			title: "回测框架使用指南",
			mode: "coding",
			messages: [],
			createdAt: "2026-04-07T16:00:00Z",
			updatedAt: "2026-04-07T17:00:00Z",
		},
	] as const,
} as const satisfies GetCopilotSessionsResponse;

// === Copilot 消息 ===

export const mockCopilotMessages: readonly CopilotMessage[] = [
	{
		id: "msg-001",
		role: "user",
		content: "最近动量因子的 IC 表现怎么样？有没有衰减趋势？",
		createdAt: "2026-04-08T09:00:00Z",
	},
	{
		id: "msg-002",
		role: "assistant",
		content:
			"根据最近 60 个交易日的 IC 序列分析，动量因子的 IC 均值从 0.058 下降至 0.028，降幅约 52%。趋势线斜率为 -0.0005/日，已连续 3 周低于 0.04 的有效阈值。\n\n建议关注以下方面：\n1. 短期降低动量因子权重至 15% 以下\n2. 增加价值因子和质量因子的配置比例\n3. 考虑引入反转因子作为对冲",
		createdAt: "2026-04-08T09:01:00Z",
	},
	{
		id: "msg-003",
		role: "user",
		content: "有没有可视化图表可以展示这个衰减趋势？",
		createdAt: "2026-04-08T09:05:00Z",
	},
	{
		id: "msg-004",
		role: "assistant",
		content:
			"已生成分因子 IC 趋势图，包含 60 日滚动 IC 序列及线性回归趋势线。从图中可以看到：\n- 3 月中旬起 IC 开始系统性下降\n- 近两周下降速度加快\n- 当前 IC 值处于近 1 年 10% 分位",
		createdAt: "2026-04-08T09:06:00Z",
	},
	{
		id: "msg-005",
		role: "user",
		content: "把这个分析保存为笔记，标题用「因子衰减应对策略」",
		createdAt: "2026-04-08T09:10:00Z",
	},
] as const satisfies readonly CopilotMessage[];

// === Agent 计划 ===

export const mockAgentPlans: GetAgentPlansResponse = {
	items: [
		{
			id: "plan-001",
			name: "因子池优化扫描",
			objective: "评估当前因子池中 45 个因子的有效性，淘汰 IC 持续低于阈值的因子",
			scope: ["全市场 A 股", "近 3 年日线数据", "45 个候选因子"],
			constraints: ["单因子测试时间不超过 10 分钟", "IC 阈值 0.04"],
			status: "running",
			createdAt: "2026-04-08T08:00:00Z",
			updatedAt: "2026-04-08T09:15:00Z",
		},
		{
			id: "plan-002",
			name: "风控参数调优",
			objective: "基于近期市场波动率变化，优化止损阈值和仓位上限参数",
			scope: ["当前持仓组合", "近 6 个月行情数据", "波动率模型"],
			constraints: ["最大回撤不超过 8%", "调整幅度不超过当前值 20%"],
			status: "pending",
			createdAt: "2026-04-08T09:00:00Z",
			updatedAt: "2026-04-08T09:00:00Z",
		},
		{
			id: "plan-003",
			name: "组合权重再平衡",
			objective: "根据最新因子评估结果和风险预算，重新分配策略权重",
			scope: ["5 个活跃策略", "风险预算模型", "相关性矩阵"],
			constraints: ["单策略权重上限 40%", "行业暴露偏差不超过 5%"],
			status: "completed",
			createdAt: "2026-04-07T14:00:00Z",
			updatedAt: "2026-04-07T18:30:00Z",
		},
	] as const,
	total: 3,
	page: 1,
	pageSize: 20,
} as const satisfies GetAgentPlansResponse;

// === Agent 运行 ===

export const mockAgentRuns: GetAgentRunsResponse = {
	items: [
		{
			id: "run-001",
			planId: "plan-001",
			planName: "因子池优化扫描",
			status: "running",
			stage: "因子回测",
			progress: 68,
			startTime: "2026-04-08T08:05:00Z",
			findingsCount: 2,
		},
		{
			id: "run-002",
			planId: "plan-002",
			planName: "风控参数调优",
			status: "pending",
			stage: "排队中",
			progress: 0,
			startTime: "2026-04-08T09:00:00Z",
			findingsCount: 0,
		},
		{
			id: "run-003",
			planId: "plan-003",
			planName: "组合权重再平衡",
			status: "completed",
			stage: "已完成",
			progress: 100,
			startTime: "2026-04-07T14:10:00Z",
			endTime: "2026-04-07T18:30:00Z",
			findingsCount: 3,
		},
	] as const,
	total: 3,
	page: 1,
	pageSize: 20,
} as const satisfies GetAgentRunsResponse;

// === Agent 发现 ===

export const mockAgentFindings: GetAgentFindingsResponse = {
	items: [
		{
			id: "finding-001",
			runId: "run-001",
			text: "动量因子 IC 连续 3 周下降至 0.028，低于有效阈值 0.04，建议降权或替换",
			confidence: 0.92,
			evidence: [
				"60 日滚动 IC 均值: 0.028",
				"IC_IR 从 0.45 降至 0.18",
				"因子收益 t 统计量降至 1.2",
			],
			impact: "high",
			status: "pending",
			createdAt: "2026-04-08T09:15:00Z",
		},
		{
			id: "finding-002",
			runId: "run-001",
			text: "低波动因子在当前市场环境下表现优异，IC 达到 0.065，建议提升权重",
			confidence: 0.88,
			evidence: [
				"60 日滚动 IC 均值: 0.065",
				"多空组合年化收益 12.3%",
				"最大回撤仅 -3.2%",
			],
			impact: "medium",
			status: "approved",
			createdAt: "2026-04-08T09:10:00Z",
		},
		{
			id: "finding-003",
			runId: "run-003",
			text: "科技板块与消费板块相关性从 0.3 升至 0.65，分散化效果减弱",
			confidence: 0.85,
			evidence: [
				"90 日滚动相关系数: 0.65",
				"历史均值: 0.35",
				"板块轮动频率下降 40%",
			],
			impact: "medium",
			status: "rejected",
			createdAt: "2026-04-07T17:00:00Z",
		},
	] as const,
	total: 3,
	page: 1,
	pageSize: 20,
} as const satisfies GetAgentFindingsResponse;

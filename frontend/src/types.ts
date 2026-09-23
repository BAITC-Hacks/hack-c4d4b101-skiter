export type Measure = { id: string; name: string; direction: string; type: "city" | "district"; cost: number; lag: number; realized_share: number; effects: Record<string, number>; description: string; risks: string };
export type District = { id: string; name: string; pop_share: number; profile: string; key_issues: string[]; indicators: Record<string, number>; raw_indicators: Record<string, number>; passport: Record<string, number>; context_indicators: Record<string, number> };
export type PlanItem = { measure: string; district: string | null };
export type Slot = { measureId: string; district: string };
export type City = {
  rules: { budget: number; decisions_exact: number; max_per_direction: number; critical_threshold: number };
  directions: Record<string, string>; measures: Measure[]; districts: District[];
  indicators: { code: string; name: string; weight: number; raw: { unit: string } }[];
  incompatibilities: { pair: [string, string]; scope: "any" | "same_district"; why: string }[];
  events: { id: string; name: string; description: string; response: { name: string; cost: number } }[];
  base_score: number; baseline: Simulation;
};
export type Validation = { valid: boolean; error: string | null; cost: number; remaining: number };
export type Simulation = {
  score: number; d_avg: number; district_scores: Record<string, number>; weakest_district: string;
  critical: [string, string][]; indicators_before: Record<string, Record<string, number>>;
  indicators_after: Record<string, Record<string, number>>;
  natural_units: Record<string, Record<string, { name: string; before: number; after: number; unit: string }>>;
  cost: number; remaining: number; contributions: { source: string; district: string; indicator: string; delta: number }[];
};
export type Submission = Simulation & { stress_test: Stress; team_name: string; percentile: number; rank: number; valid_plans: number; gap: number; best_single_swap: { plan: PlanItem[]; score: number; improvement: number } };
export type Explanation = { summary: string; strengths: string[]; risks: string[]; consequences: string[]; main_tradeoff: string; verified: boolean; ai: AiUsage };
export type Advice = { search_ai: AiUsage; comparison: {label: string; before: number; after: number}[]; removed: PlanItem[]; added: PlanItem[]; best_plan: PlanItem[]; best_score: number; improvement: number; trace: { source: string; score?: number; error?: string }[]; explanation: Explanation };
export type Stress = { average: number; worst: number; events: { id: string; name: string; score: number; delta: number; n_critical: number }[] };
export type BoardRow = { team_name: string; score: number; percentile: number; resilience_average: number };

export type AiUsage = { mode: string };

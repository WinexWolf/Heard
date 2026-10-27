export interface Caps { perception_mode: string; models: Record<string, string | null>; live_ready: boolean; rate_limit_per_hour: number }
export interface Session { id: string; site: string; label: string; duration: number; steps: number; has_cache: boolean; video: string }
export interface Finding { id: string; t_start: number; t_end: number; announced_text: string; visible_text_or_description: string;
  issue_type: string; severity: string; wcag_guess: string; evidence: string }
export interface Edit { file: string; old_str: string; new_str: string }
export interface Attempt { model: string; role: string; passed: boolean; reason: string; edits: Edit[]; rationale?: string;
  verification?: { checks: string[]; after_announcement: string; new_violations: string[] } }
export interface FindingResult { finding: Finding; step?: { selector: string; announcement: string }; citations: { title: string; url: string }[];
  attempts: Attempt[]; fixed: boolean; model_used: string | null; final: Attempt | null; before_audio: string | null; after_audio: string | null }
export interface CostAgg { calls: number; input_tokens: number; output_tokens: number; latency_s: number; cost_usd: number; cost_known?: boolean }
export interface Result { session_id: string; source: string; perception_mode: string; models: Record<string, string>; findings: FindingResult[];
  rejected_unsupported: { finding: Finding; reason: string }[]; raw_finding_count: number;
  cost: { total: CostAgg & { tavily_calls: number }; by_stage: Record<string, CostAgg>; by_model: Record<string, CostAgg> } }
export interface Bench { source: string[]; perception_mode: string[]; total_bugs: number; axe_detected: number; heard_detected: number;
  fixes_verified: number; rejected_unsupported: number; matching_rule: string;
  bugs: { id: string; site: string; category: string; description: string; axe_detected: boolean; heard_detected: boolean; fix_verified: boolean }[] }

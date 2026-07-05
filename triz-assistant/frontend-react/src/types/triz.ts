/** TypeScript-зеркало Pydantic-схем backend/schemas.py и backend/llm/models.py */

export interface SystemContext {
  system: string
  supersystem: string
  subsystems: string[]
  useful_functions: string[]
  harmful_effects: string[]
  constraints: string[]
  resources: string[]
}

export interface AnalysisBlock {
  causal_chains: string
  functional_analysis: string
  resources_analysis: string
  contradiction_zones: string
}

export interface TrizToolRow {
  tool: string
  why_applied: string
  insight: string
  practical_value: string
}

export interface SolutionConcept {
  id: number
  title: string
  triz_principle: string
  mechanism: string
  applicability: string
  risks: string
  effectiveness_score: number
  complexity_score: number
  cost_score: number
  scalability_score: number
  total_score?: number
}

export interface RecommendationsBlock {
  priorities: string[]
  priority_solution_id: number
  quick_checks: string[]
  mvp_pilots: string[]
  critical_risks: string[]
  experiments: string[]
  metrics: string[]
}

export interface FinalConclusionBlock {
  recommended_solution: string
  key_risk: string
  next_step: string
}

/** Полный TRIZ-отчёт (TRIZAnalysisResult / SolveResponse) */
export interface TRIZAnalysisResult {
  problem_description: string
  assumptions: string[]
  system_context: SystemContext
  technical_contradiction: string
  physical_contradiction: string
  contradiction_type: string
  ideal_final_result: string
  root_cause: string
  analysis: AnalysisBlock
  triz_tools: TrizToolRow[]
  solution_concepts: SolutionConcept[]
  recommendations: RecommendationsBlock
  final_conclusion: FinalConclusionBlock
  recommended_principles: string[]
  executive_summary: string
  /** Legacy fields */
  contradiction?: string
  solutions?: string[]
  reasoning?: string
}

export type ChatSessionStatus = 'interview' | 'ready' | 'analyzed'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatSession {
  id: string
  status: ChatSessionStatus
  title: string | null
  messages: ChatMessage[]
  brief: string | null
  created_at: string
  updated_at: string
}

export interface ChatSessionSummary {
  id: string
  status: ChatSessionStatus
  title: string
  message_count: number
  brief: string | null
  created_at: string
  updated_at: string
}

export interface ChatSessionsListResponse {
  items: ChatSessionSummary[]
  limit: number
}

export interface ChatAnalyzeResponse {
  session_id: string
  brief: string
  result: TRIZAnalysisResult
}

export interface AnalyzeProgressResponse {
  session_id: string
  progress: number
  stage: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  error: string | null
}

export interface AuthUser {
  id: string
  username: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

export interface ActiveChatStateResponse {
  session_id: string | null
}

export interface ChatSessionsDeleteResponse {
  deleted: number
}

export interface HistoryEntry {
  id: string
  problem: string
  result: TRIZAnalysisResult | Record<string, unknown>
  time: string
  created_at: string | null
  chat_session_id: string | null
}

export interface SolveRequest {
  problem: string
  chat_session_id?: string | null
  force?: boolean
}

export interface SolveJobCreateResponse {
  job_id: string
  status: 'running'
}

export interface SolveJobProgress {
  pct: number
  stage: string
}

export interface SolveJobStatusResponse {
  status: 'running' | 'done' | 'error'
  progress: SolveJobProgress
  result: SolveResponse | null
  error: string | null
}

export interface SolveResponse extends TRIZAnalysisResult {}

export interface HealthResponse {
  status: string
  server: string
  llm_model: string
  openai_configured: boolean
  openai_base_url: string | null
  proxy_enabled: boolean
  message: string | null
}

export interface ErrorResponse {
  detail: string
}

export function computeTotalScore(solution: SolutionConcept): number {
  if (solution.total_score != null) return solution.total_score
  return Math.round(
    (solution.effectiveness_score +
      solution.scalability_score -
      (solution.complexity_score + solution.cost_score) / 2) *
      10,
  ) / 10
}

export interface RuntimeStatus {
  status: 'starting' | 'ready' | 'stopped'
  label?: string
  detail?: string | null
}

export interface DataDirectoryAttachment {
  id: string
  path: string
  enabled: boolean
  label?: string | null
}

export interface DataDirectoryEntry {
  name: string
  path: string
  is_dir: boolean
}

export interface DataDirectoryBrowserPayload {
  current_path: string
  parent_path?: string | null
  home_path: string
  cwd_path: string
  entries: DataDirectoryEntry[]
}

export interface RecentDataDirectoriesPayload {
  items: DataDirectoryAttachment[]
}

export interface BoundingBox {
  min_x: number
  min_y: number
  max_x: number
  max_y: number
  crs: string
}

export interface RuntimeRole {
  id: string
  title: string
  responsibility: string
}

export interface RuntimeProfile {
  bundle_id: string
  label: string
  roles: RuntimeRole[]
  tools: string[]
}

export interface HealthPayload {
  app: 'ready'
  runtime: RuntimeStatus
  geospatial_environment?: {
    status: 'ready' | 'provisioning' | 'not_ready' | 'failed'
    progress?: number
    logs?: string[]
    command?: string[]
    package_readiness?: Record<string, unknown>
    detail?: string | null
  }
  default_data_directories?: DataDirectoryAttachment[]
}

export interface PlanEntry {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
}

export interface PlanGroup {
  id: string
  agent: string
  label: string
  entries: PlanEntry[]
  updated_at: string
}

export interface GeospatialLayer {
  id: string
  label: string
  path: string
  geometry_type: 'point' | 'line' | 'polygon' | 'raster'
  crs: string
  feature_count?: number | null
  bbox?: BoundingBox | null
}

export interface GeospatialPreprocessing {
  target_crs: string
  clip_to_study_area: boolean
  clip_operation: 'clip' | 'mask'
}

export interface OperatorMetadata {
  name: 'kde' | 'spatial_interpolation' | 'spatial_hotspot' | 'buffer' | 'interpolation' | 'clustering' | 'regression'
  stage: 'planned' | 'preprocessing' | 'analysis' | 'completed' | 'blocked' | 'failed'
  parameters: Record<string, string | number | boolean>
}

export interface VerificationEntry {
  id: string
  code: string
  title: string
  status: 'pending' | 'passed' | 'warning' | 'failed'
  detail: string
}

export interface GeospatialTask {
  id: string
  prompt: string
  analysis_type: 'kde' | 'spatial_interpolation' | 'spatial_hotspot' | 'buffer' | 'interpolation' | 'clustering' | 'regression'
  stage: 'planned' | 'preprocessing' | 'analysis' | 'completed' | 'blocked' | 'failed'
  runtime: RuntimeProfile
  input_layers: GeospatialLayer[]
  study_area: GeospatialLayer | null
  prepared_layers: GeospatialLayer[]
  preprocessing: GeospatialPreprocessing
  operator: OperatorMetadata
  expected_outputs: string[]
}

export interface TimelineEntry {
  id: string
  kind: 'status' | 'message' | 'plan' | 'question' | 'artifact' | 'evidence'
  text: string
  created_at: string
  record_type?: string | null
  title?: string | null
  detail?: string | null
  category?: string | null
  evidence_record_id?: string | null
  data?: Record<string, unknown>
  provenance?: Record<string, unknown>
}

export interface SessionIssue {
  id: string
  type: 'user_interrupt' | 'runtime_error' | 'runtime_crash' | 'runtime_connection_lost' | 'tool_failure' | 'frontend_connection_lost'
  severity: 'info' | 'warning' | 'error'
  source: 'backend' | 'runtime' | 'opencode' | 'mcp' | 'frontend'
  title: string
  detail: string
  created_at: string
  runtime_session_id?: string | null
  trace_path?: string | null
  recoverable?: boolean | null
}

export interface QuestionOption {
  label: string
  description?: string | null
}

export interface QuestionItem {
  header: string
  question: string
  options: QuestionOption[]
}

export interface Question {
  id: string
  prompt: string
  source?: 'workflow' | 'runtime'
  questions?: QuestionItem[]
}

export type QuestionReplyPayload = string | { answers: string[] }

export interface Artifact {
  id: string
  title: string
  path: string
  kind?: 'manifest' | 'map' | 'raster' | 'report' | 'metadata' | 'prepared' | 'verification' | 'table' | 'dataset' | 'image' | 'html' | 'json' | 'text' | 'archive' | 'other' | null
  task_id?: string | null
  analysis_type?: GeospatialTask['analysis_type'] | null
  description?: string | null
  format?: string | null
  artifact_stage?: 'intermediate' | 'final' | null
  display_hint?: 'image' | 'map' | 'table' | 'markdown' | 'json' | 'text' | 'html' | 'download' | 'other' | null
  evidence_record_id?: string | null
  provenance?: Record<string, unknown>
}

export interface ChatMessagePart {
  type: string
  text?: string | null
  tool?: string | null
  state?: Record<string, unknown> | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  agent?: string | null
  created_at: string
  parts: ChatMessagePart[]
}

export interface Session {
  id: string
  title: string
  status: 'idle' | 'running' | 'waiting_for_input' | 'completed' | 'failed'
  workspace_path?: string | null
  runtime_session_id?: string | null
  runtime_trace_path?: string | null
  read_only?: boolean
  archive_metadata?: Record<string, unknown>
  attached_data_directories: DataDirectoryAttachment[]
  messages: ChatMessage[]
  timeline: TimelineEntry[]
  artifacts: Artifact[]
  plan: PlanEntry[]
  plan_groups?: PlanGroup[]
  issues?: SessionIssue[]
  question: Question | null
  geospatial_task: GeospatialTask | null
  verification: VerificationEntry[]
}

export interface SessionSummary {
  id: string
  title: string
  status: Session['status']
  created_at: string
  updated_at: string
  workspace_path?: string | null
  runtime_session_id?: string | null
  runtime_trace_path?: string | null
  read_only?: boolean
  archive_metadata?: Record<string, unknown>
  attached_data_directories?: DataDirectoryAttachment[]
}

export interface EventEnvelope<T> {
  type: string
  payload: T
}

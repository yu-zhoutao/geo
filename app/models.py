from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AnalysisType = Literal[
    'kde',
    'spatial_interpolation',
    'spatial_hotspot',
    'buffer',
    'interpolation',
    'clustering',
    'regression',
    'land_cover_change',
    'spatiotemporal_pattern',
    'time_series_trend',
    'terrain_analysis',
    'unsupervised_clustering',
]
GeometryType = Literal['point', 'line', 'polygon', 'raster']
TaskStage = Literal['planned', 'preprocessing', 'analysis', 'completed', 'blocked', 'failed']
VerificationStatus = Literal['pending', 'passed', 'warning', 'failed']
SessionStatus = Literal['idle', 'running', 'waiting_for_input', 'completed', 'failed']
WorkflowDecision = Literal['proceed', 'clarify', 'repair', 'stop']
QuestionSource = Literal['runtime']
SessionIssueType = Literal[
    'user_interrupt',
    'runtime_error',
    'runtime_crash',
    'runtime_connection_lost',
    'tool_failure',
    'frontend_connection_lost',
]
SessionIssueSeverity = Literal['info', 'warning', 'error']
SessionIssueSource = Literal['backend', 'runtime', 'opencode', 'mcp', 'frontend']


class RuntimeStatus(BaseModel):
    status: Literal['starting', 'ready', 'stopped']
    label: str
    pid: int | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    app: Literal['ready'] = 'ready'
    runtime: RuntimeStatus
    storage: dict[str, object]
    workspace: dict[str, object]
    provider: dict[str, object]
    mcp: dict[str, object]
    geospatial_environment: dict[str, object] = Field(default_factory=dict)
    default_data_directories: list['DataDirectoryAttachment'] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    id: str
    kind: Literal['status', 'message', 'plan', 'question', 'artifact', 'evidence']
    text: str
    created_at: datetime
    record_type: str | None = None
    title: str | None = None
    detail: str | None = None
    category: str | None = None
    evidence_record_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SessionIssue(BaseModel):
    id: str
    type: SessionIssueType
    severity: SessionIssueSeverity
    source: SessionIssueSource
    title: str
    detail: str
    created_at: datetime
    runtime_session_id: str | None = None
    trace_path: str | None = None
    recoverable: bool | None = None


class PlanEntry(BaseModel):
    id: str
    label: str
    status: Literal['pending', 'in_progress', 'completed', 'blocked']


class PlanGroup(BaseModel):
    id: str
    agent: str
    label: str
    entries: list[PlanEntry] = Field(default_factory=list)
    updated_at: datetime


class QuestionOption(BaseModel):
    label: str
    description: str | None = None


class QuestionItem(BaseModel):
    header: str
    question: str
    options: list[QuestionOption] = Field(default_factory=list)


class Question(BaseModel):
    id: str
    prompt: str
    source: QuestionSource = 'runtime'
    questions: list[QuestionItem] = Field(default_factory=list)


class DataDirectoryAttachment(BaseModel):
    id: str
    path: str
    enabled: bool = True
    label: str | None = None


class DataDirectoryEntry(BaseModel):
    name: str
    path: str
    is_dir: bool = True


class DataDirectoryBrowserResponse(BaseModel):
    current_path: str
    parent_path: str | None = None
    home_path: str
    cwd_path: str
    entries: list[DataDirectoryEntry] = Field(default_factory=list)


class RecentDataDirectoriesResponse(BaseModel):
    items: list[DataDirectoryAttachment] = Field(default_factory=list)


class BoundingBox(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    crs: str


class RuntimeRole(BaseModel):
    id: str
    title: str
    responsibility: str


class RuntimeProfile(BaseModel):
    bundle_id: str
    label: str
    roles: list[RuntimeRole] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class RuntimeActivity(BaseModel):
    role: str
    status: Literal['completed', 'warning', 'failed']
    detail: str


class GeospatialLayer(BaseModel):
    id: str
    label: str
    path: str
    geometry_type: GeometryType
    crs: str
    feature_count: int | None = None
    bbox: BoundingBox | None = None


class GeospatialPreprocessing(BaseModel):
    target_crs: str
    clip_to_study_area: bool = True
    clip_operation: Literal['clip', 'mask'] = 'mask'


class OperatorMetadata(BaseModel):
    name: AnalysisType
    stage: TaskStage
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class VerificationEntry(BaseModel):
    id: str
    code: str
    title: str
    status: VerificationStatus
    detail: str
    decision: WorkflowDecision | None = None
    reason_code: str | None = None
    blocking_evidence: list[str] = Field(default_factory=list)


class GeospatialTask(BaseModel):
    id: str
    prompt: str
    analysis_type: AnalysisType
    stage: TaskStage
    runtime: RuntimeProfile
    input_layers: list[GeospatialLayer] = Field(default_factory=list)
    study_area: GeospatialLayer | None = None
    prepared_layers: list[GeospatialLayer] = Field(default_factory=list)
    preprocessing: GeospatialPreprocessing
    operator: OperatorMetadata
    expected_outputs: list[str] = Field(default_factory=list)
    activity_trace: list[RuntimeActivity] = Field(default_factory=list)


class Artifact(BaseModel):
    id: str
    title: str
    path: str
    kind: Literal['manifest', 'map', 'raster', 'report', 'metadata', 'prepared', 'verification', 'table', 'dataset', 'image', 'html', 'json', 'text', 'archive', 'other'] | None = None
    task_id: str | None = None
    analysis_type: AnalysisType | None = None
    description: str | None = None
    format: str | None = None
    artifact_stage: Literal['intermediate', 'final'] | None = None
    display_hint: Literal['image', 'map', 'table', 'markdown', 'json', 'text', 'html', 'download', 'other'] | None = None
    evidence_record_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class GeospatialSessionContext(BaseModel):
    id: str
    session_id: str
    runtime_session_id: str | None = None
    mcp_session_id: str | None = None
    prompt: str
    answer: str | None = None
    workspace_path: str
    request_snapshot_path: str | None = None
    prepared_input_path: str | None = None
    manifest_path: str | None = None
    attached_data_directories: list[DataDirectoryAttachment] = Field(default_factory=list)
    geospatial_task: GeospatialTask | None = None
    verification: list[VerificationEntry] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatMessagePart(BaseModel):
    type: str
    text: str | None = None
    tool: str | None = None
    state: dict[str, object] | None = None


class ChatMessage(BaseModel):
    id: str
    role: Literal['user', 'assistant', 'system']
    agent: str | None = None
    created_at: datetime
    parts: list[ChatMessagePart] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    title: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    workspace_path: str | None = None
    geospatial_context_id: str | None = None
    runtime_session_id: str | None = None
    runtime_trace_path: str | None = None
    attached_data_directories: list[DataDirectoryAttachment] = Field(default_factory=list)
    read_only: bool = False
    archive_metadata: dict[str, Any] = Field(default_factory=dict)


class Session(SessionSummary):
    messages: list[ChatMessage] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    plan: list[PlanEntry] = Field(default_factory=list)
    plan_groups: list[PlanGroup] = Field(default_factory=list)
    issues: list[SessionIssue] = Field(default_factory=list)
    question: Question | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    geospatial_task: GeospatialTask | None = None
    verification: list[VerificationEntry] = Field(default_factory=list)


class MessageRequest(BaseModel):
    text: str


class RenameSessionRequest(BaseModel):
    title: str


class AnswerRequest(BaseModel):
    answer: str | None = None
    answers: list[str] = Field(default_factory=list)


class UpdateAttachedDataDirectoriesRequest(BaseModel):
    items: list[DataDirectoryAttachment]


class OpenDataDirectoryRequest(BaseModel):
    path: str


class SessionArchiveImportRequest(BaseModel):
    archive: dict[str, Any]


class MessageAccepted(BaseModel):
    accepted: bool = True
    question: Question | None = None


class AnswerAccepted(BaseModel):
    accepted: bool = True


class EventEnvelope(BaseModel):
    type: str
    payload: object

import toolIdentity from './toolIdentity.json'

export interface RuntimeToolIdentity {
  label: string
  family: string
  summary: string
  icon: string
}

export interface ResolvedToolIdentity extends RuntimeToolIdentity {
  name: string
  rawName: string
  known: boolean
}

const TOOL_IDENTITIES: Record<string, RuntimeToolIdentity> = toolIdentity
const EVIDENCE_RECORD_LABELS: Record<string, string> = {
  dataset_profile: '记录数据画像',
  verification_fact: '记录验证事实',
  parameter_snapshot: '记录参数快照',
  claim_trace: '记录声明追踪',
}

export function canonicalToolName(toolName: string | null | undefined): string {
  let normalized = (toolName ?? '').trim()
  if (normalized.startsWith('mcp__geospatial__')) {
    normalized = normalized.slice('mcp__geospatial__'.length)
  }

  while (normalized.startsWith('geospatial_geospatial_')) {
    normalized = normalized.slice('geospatial_'.length)
  }

  if (TOOL_IDENTITIES[normalized]) {
    return normalized
  }

  if (normalized.startsWith('geospatial_')) {
    const stripped = normalized.slice('geospatial_'.length)
    if (TOOL_IDENTITIES[stripped]) {
      return stripped
    }
  }

  return normalized
}

export function resolveToolIdentity(toolName: string | null | undefined): ResolvedToolIdentity {
  const rawName = toolName ?? ''
  const name = canonicalToolName(rawName)
  const identity = TOOL_IDENTITIES[name]
  if (identity) {
    return {
      name,
      rawName,
      known: true,
      ...identity,
    }
  }

  return {
    name,
    rawName,
    known: false,
    label: '运行时工具',
    family: 'tool',
    summary: '未在当前应用工具映射中注册的运行时工具。',
    icon: 'wrench',
  }
}

export function resolveToolIdentityForState(toolName: string | null | undefined, state: Record<string, unknown> | null | undefined): ResolvedToolIdentity {
  const identity = resolveToolIdentity(toolName)
  if (identity.name !== 'record_run_evidence') {
    return identity
  }

  return {
    ...identity,
    label: evidenceToolLabel(state) ?? identity.label,
  }
}

function evidenceToolLabel(state: Record<string, unknown> | null | undefined): string | null {
  const input = state?.input
  if (!input || typeof input !== 'object') {
    return null
  }
  const payload = input as Record<string, unknown>
  const recordType = typeof payload.record_type === 'string' ? payload.record_type : ''
  if (recordType === 'artifact') {
    const artifactStage = typeof payload.artifact_stage === 'string' ? payload.artifact_stage : ''
    if (artifactStage === 'final') return '记录最终产物'
    if (artifactStage === 'intermediate') return '记录中间产物'
    return '记录产物'
  }
  return EVIDENCE_RECORD_LABELS[recordType] ?? null
}

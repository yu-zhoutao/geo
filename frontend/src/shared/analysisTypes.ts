import type { Artifact, GeospatialTask, TimelineEntry } from '../types'

export type AnalysisType = GeospatialTask['analysis_type']

const ANALYSIS_TYPE_LABELS: Record<AnalysisType, string> = {
  kde: 'KDE 密度',
  spatial_interpolation: 'IDW 插值',
  spatial_hotspot: 'Gi* 热点',
  buffer: '缓冲区',
  interpolation: '空间插值',
  clustering: '空间聚类',
  regression: '空间回归',
}

export function analysisTypeLabel(analysisType: AnalysisType | null | undefined): string | null {
  return analysisType ? ANALYSIS_TYPE_LABELS[analysisType] ?? null : null
}

export function artifactAnalysisTypeLabel(artifact: Artifact): string | null {
  return analysisTypeLabel(artifact.analysis_type)
}

export function evidenceAnalysisTypeLabel(entry: TimelineEntry): string | null {
  const candidates = [entry.data?.analysis_type, entry.provenance?.analysis_type]
  const analysisType = candidates.find((value): value is AnalysisType => (
    typeof value === 'string' && value in ANALYSIS_TYPE_LABELS
  ))
  return analysisTypeLabel(analysisType)
}

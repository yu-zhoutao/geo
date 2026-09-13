import type { Artifact } from '../../types'
import { artifactContentUrl } from '../../api'

export type ArtifactPreviewKind = 'image' | 'html' | 'markdown' | 'text' | 'table' | 'other'

const TEXT_PREVIEW_KINDS = new Set<ArtifactPreviewKind>(['markdown', 'text', 'table'])
const IMAGE_FORMATS = new Set(['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'])
const MARKDOWN_FORMATS = new Set(['md', 'markdown'])
const TEXT_FORMATS = new Set(['txt', 'log'])
const TABLE_FORMATS = new Set(['csv', 'tsv'])
const OPEN_ONLY_FORMATS = new Set([
  'json',
  'geojson',
  'gpkg',
  'shp',
  'tif',
  'tiff',
  'parquet',
  'zip',
  'gz',
  'tar',
])

const previewTextCache = new Map<string, Promise<string>>()

function extension(path: string | null | undefined): string {
  const name = path?.split('/').pop() ?? ''
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index + 1).toLowerCase() : ''
}

export function artifactFormat(artifact: Artifact): string {
  return (artifact.format ?? extension(artifact.path)).toLowerCase()
}

export function artifactPreviewKind(artifact: Artifact): ArtifactPreviewKind {
  const format = artifactFormat(artifact)
  const displayHint = artifact.display_hint ?? null

  if (displayHint === 'download' || displayHint === 'other' || OPEN_ONLY_FORMATS.has(format)) {
    return 'other'
  }
  if ((displayHint === 'image' || displayHint === 'map') && IMAGE_FORMATS.has(format)) {
    return 'image'
  }
  if (displayHint === 'html' || format === 'html' || format === 'htm') {
    return 'html'
  }
  if (displayHint === 'markdown' || MARKDOWN_FORMATS.has(format)) {
    return 'markdown'
  }
  if (displayHint === 'table' || TABLE_FORMATS.has(format)) {
    return 'table'
  }
  if (displayHint === 'text' || TEXT_FORMATS.has(format)) {
    return 'text'
  }
  return 'other'
}

export function canPreviewArtifact(artifact: Artifact): boolean {
  return artifactPreviewKind(artifact) !== 'other'
}

export function previewContentUrl(sessionId: string | null | undefined, artifact: Artifact): string {
  return sessionId ? artifactContentUrl(sessionId, artifact.id) : ''
}

export function artifactPreviewCacheKey(sessionId: string, artifact: Artifact): string {
  return [
    sessionId,
    artifact.id,
    artifact.path,
    artifact.format ?? '',
    artifact.display_hint ?? '',
    artifact.evidence_record_id ?? '',
  ].join(':')
}

export async function loadTextArtifactPreview(sessionId: string, artifact: Artifact): Promise<string> {
  const kind = artifactPreviewKind(artifact)
  if (!TEXT_PREVIEW_KINDS.has(kind)) {
    return ''
  }

  const key = artifactPreviewCacheKey(sessionId, artifact)
  const existing = previewTextCache.get(key)
  if (existing) {
    return existing
  }

  const request = fetch(artifactContentUrl(sessionId, artifact.id))
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      return response.text()
    })
    .catch((cause: unknown) => {
      previewTextCache.delete(key)
      throw cause
    })
  previewTextCache.set(key, request)
  return request
}

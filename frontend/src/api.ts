import type { DataDirectoryAttachment, DataDirectoryBrowserPayload, HealthPayload, QuestionReplyPayload, RecentDataDirectoriesPayload, Session, SessionSummary } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    let message = `Request failed: ${response.status}`
    if (typeof response.text === 'function') {
      const body = await response.text()
      if (body) {
        try {
          const parsed = JSON.parse(body) as { detail?: string }
          message = parsed.detail ?? message
        } catch {
          message = body
        }
      }
    }
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  if (typeof response.text === 'function') {
    const body = await response.text()
    if (!body) {
      return undefined as T
    }
    return JSON.parse(body) as T
  }

  return response.json() as Promise<T>
}

export function getHealth(): Promise<HealthPayload> {
  return request<HealthPayload>('/api/health')
}

export function listSessions(): Promise<SessionSummary[]> {
  return request<SessionSummary[]>('/api/sessions')
}

export function createSession(): Promise<Session> {
  return request<Session>('/api/sessions', { method: 'POST' })
}

export function getSession(sessionId: string): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}`)
}

export function renameSession(sessionId: string, title: string): Promise<SessionSummary> {
  return request<SessionSummary>(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(`/api/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}

export function submitMessage(sessionId: string, text: string): Promise<{ accepted: true }> {
  return request<{ accepted: true }>(`/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export function interruptSession(sessionId: string): Promise<void> {
  return request<void>(`/api/sessions/${sessionId}/interrupt`, {
    method: 'POST',
  })
}

export function answerQuestion(sessionId: string, questionId: string, answer: QuestionReplyPayload): Promise<{ accepted: true }> {
  return request<{ accepted: true }>(`/api/sessions/${sessionId}/questions/${questionId}/answers`, {
    method: 'POST',
    body: JSON.stringify(typeof answer === 'string' ? { answer } : answer),
  })
}

export function updateAttachedDataDirectories(sessionId: string, items: DataDirectoryAttachment[]): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}/data-directories`, {
    method: 'PUT',
    body: JSON.stringify({ items }),
  })
}

export function browseDataDirectories(path?: string): Promise<DataDirectoryBrowserPayload> {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  return request<DataDirectoryBrowserPayload>(`/api/data-directories/browser${query}`)
}

export function listRecentDataDirectories(): Promise<RecentDataDirectoriesPayload> {
  return request<RecentDataDirectoriesPayload>('/api/data-directories/recent')
}

export function openDataDirectory(path: string): Promise<void> {
  return request<void>('/api/data-directories/open', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export function openArtifact(sessionId: string, artifactId: string): Promise<void> {
  return request<void>(`/api/sessions/${sessionId}/artifacts/${artifactId}/open`, {
    method: 'POST',
  })
}

function filenameFromContentDisposition(value: string | null): string {
  const match = value?.match(/filename="?([^";]+)"?/i)
  return match?.[1] ?? 'geo-agent-session-archive.json'
}

export async function exportSessionArchive(sessionId: string): Promise<{ blob: Blob, filename: string }> {
  const response = await fetch(`/api/sessions/${sessionId}/archive`, {
    headers: {
      Accept: 'application/json',
    },
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(body || `Request failed: ${response.status}`)
  }
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get('content-disposition')),
  }
}

export function importSessionArchive(archive: unknown): Promise<Session> {
  return request<Session>('/api/session-archives/import', {
    method: 'POST',
    body: JSON.stringify({ archive }),
  })
}

export function artifactContentUrl(sessionId: string, artifactId: string): string {
  return `/api/sessions/${sessionId}/artifacts/${artifactId}/content`
}

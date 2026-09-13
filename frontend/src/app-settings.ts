export interface AppSettings {
  showThinking: boolean
}

export const APP_SETTINGS_STORAGE_KEY = 'geo-agent:app-settings'

export const DEFAULT_APP_SETTINGS: AppSettings = {
  showThinking: false,
}

function normalizeAppSettings(value: unknown): AppSettings {
  if (!value || typeof value !== 'object') {
    return { ...DEFAULT_APP_SETTINGS }
  }

  const candidate = value as Partial<AppSettings>

  return {
    showThinking: typeof candidate.showThinking === 'boolean' ? candidate.showThinking : DEFAULT_APP_SETTINGS.showThinking,
  }
}

export function loadAppSettings(): AppSettings {
  if (typeof localStorage === 'undefined') {
    return { ...DEFAULT_APP_SETTINGS }
  }

  try {
    const raw = localStorage.getItem(APP_SETTINGS_STORAGE_KEY)
    if (!raw) {
      return { ...DEFAULT_APP_SETTINGS }
    }

    return normalizeAppSettings(JSON.parse(raw))
  } catch {
    return { ...DEFAULT_APP_SETTINGS }
  }
}

export function saveAppSettings(settings: AppSettings): void {
  if (typeof localStorage === 'undefined') {
    return
  }

  try {
    localStorage.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(normalizeAppSettings(settings)))
  } catch {
    return
  }
}

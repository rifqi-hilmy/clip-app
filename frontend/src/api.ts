// Typed API client for the FastAPI backend (proxied by Vite at /api).

export type HeatPoint = { start_time: number; end_time: number; value: number }

export type Video = {
  id: number
  youtube_id: string
  url: string
  title: string
  channel: string
  duration: number
  thumbnail: string
  path: string | null
  media_url: string | null
  heatmap: HeatPoint[] | null
  chapters: { start_time: number; end_time: number; title: string }[] | null
}

export type Reframe = 'blur' | 'center' | 'face'
export type Aspect = '9:16' | 'original'

export type Clip = {
  id: number
  project_id: number
  start: number
  end: number
  title: string
  score: number | null
  reason: string
  source: string
  aspect: Aspect
  reframe: Reframe
  crop_x: number
  caption_style: string | null
  export_path: string | null
  export_url: string | null
  srt_url: string | null
}

export type Job = {
  id: number
  project_id: number | null
  clip_id: number | null
  type: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: number
  message: string
  error: string | null
}

export type ProjectSummary = {
  id: number
  name: string
  status: string
  created_at: string
  video: Video
  clip_count: number
}

export type ProjectDetail = ProjectSummary & {
  clips: Clip[]
  jobs: Job[]
  language: string | null
  transcript: { language: string; model: string; segments: number } | null
}

export type VideoInfo = {
  youtube_id: string
  url: string
  title: string
  channel: string
  duration: number
  thumbnail: string
  has_heatmap: boolean
  chapters_count: number
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    let msg = `HTTP ${r.status}`
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  health: () => req<{ status: string; tools: Record<string, any> }>('GET', '/health'),
  videoInfo: (url: string) => req<VideoInfo>('POST', '/videos/info', { url }),
  listProjects: () => req<ProjectSummary[]>('GET', '/projects'),
  createProject: (url: string, language?: string | null) =>
    req<ProjectSummary>('POST', '/projects', { url, language: language || null }),
  getProject: (id: number) => req<ProjectDetail>('GET', `/projects/${id}`),
  deleteProject: (id: number) => req('DELETE', `/projects/${id}`),
  retryDownload: (id: number) => req<Job>('POST', `/projects/${id}/download`),
  createClip: (pid: number, c: Partial<Clip>) => req<Clip>('POST', `/projects/${pid}/clips`, c),
  updateClip: (id: number, c: Partial<Clip>) => req<Clip>('PATCH', `/clips/${id}`, c),
  deleteClip: (id: number) => req('DELETE', `/clips/${id}`),
  renderClip: (id: number) => req<Job>('POST', `/clips/${id}/render`),
  renderAll: (pid: number) => req<Job[]>('POST', `/projects/${pid}/render-all`),
  whisperModels: () => req<{ models: string[]; default: string }>('GET', '/whisper/models'),
  captionPresets: () => req<{ id: string; label: string }[]>('GET', '/captions/presets'),
  transcribe: (pid: number, model: string, language: string | null, force = false) =>
    req<Job>('POST', `/projects/${pid}/transcribe`, { model, language, force }),
  getTranscript: (pid: number) => req<Transcript>('GET', `/projects/${pid}/transcript`),
  // Phase 3: AI highlight
  highlightStatus: () => req<HighlightStatus>('GET', '/highlight/status'),
  getHighlightSettings: () => req<HighlightSettings>('GET', '/settings/highlight'),
  updateHighlightSettings: (s: Partial<HighlightSettings>) =>
    req<HighlightSettings>('PUT', '/settings/highlight', s),
  startHighlight: (pid: number, opts: {
    provider?: string; model?: string | null;
    max_clips?: number; target_durations?: number[]; min_score?: number
  }) => req<Job>('POST', `/projects/${pid}/highlight`, opts),
  // Phase 5: local import, generate meta, presets
  importLocal: (path: string, title?: string, language?: string | null) =>
    req<ProjectSummary>('POST', '/projects/import-local', { path, title, language: language || null }),
  generateMeta: (clipId: number, provider = 'ollama', model?: string | null) =>
    req<{ title: string; description: string; hashtags: string[] }>('POST', `/clips/${clipId}/generate-meta`, { provider, model }),
  listPresets: () => req<Preset[]>('GET', '/presets'),
  savePreset: (preset: Partial<Preset>) => req<Preset[]>('POST', '/presets', preset),
  deletePreset: (id: string) => req<Preset[]>('DELETE', `/presets/${id}`),
}

export type Word = { start: number; end: number; word: string }
export type Segment = { id: number; start: number; end: number; text: string; words: Word[] }
export type Transcript = { language: string; model: string; duration: number; segments: Segment[] }
export type TranscriptMeta = { language: string; model: string; segments: number } | null

export function fmtTime(sec: number, withMs = false): string {
  if (!isFinite(sec) || sec < 0) sec = 0
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  const ms = Math.floor((sec % 1) * 10)
  const base = `${h > 0 ? h + ':' : ''}${String(m).padStart(h > 0 ? 2 : 1, '0')}:${String(s).padStart(2, '0')}`
  return withMs ? `${base}.${ms}` : base
}

/** Parses "1:23", "01:02:03.5" or "83.2" into seconds. */
export function parseTime(text: string): number | null {
  const t = text.trim()
  if (!t) return null
  const parts = t.split(':').map(Number)
  if (parts.some((p) => isNaN(p))) return null
  return parts.reduce((acc, p) => acc * 60 + p, 0)
}

// Phase 3: AI highlight types
export type HighlightSettings = {
  provider: 'ollama' | 'openai'
  ollama_model: string
  ollama_url: string
  openai_base_url: string
  openai_api_key: string
  openai_model: string
}

export type HighlightStatus = {
  ollama: { available: boolean; models: string[] }
  openai: { configured: boolean }
  default_provider: string
}

export type Preset = {
  id: string
  name: string
  aspect: string
  reframe: string
  caption_style: string | null
}

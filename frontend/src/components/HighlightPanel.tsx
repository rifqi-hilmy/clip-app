import { useEffect, useState } from 'react'
import { api, type HighlightStatus, type Job, type ProjectDetail } from '../api'

type Props = {
  project: ProjectDetail
  job: Job | undefined
  onComplete: () => void
}

const DURATIONS = [15, 30, 60, 90]

export default function HighlightPanel({ project, job, onComplete }: Props) {
  const [status, setStatus] = useState<HighlightStatus | null>(null)
  const [provider, setProvider] = useState<'ollama' | 'openai'>('ollama')
  const [model, setModel] = useState('')
  const [maxClips, setMaxClips] = useState(10)
  const [minScore, setMinScore] = useState(40)
  const [durations, setDurations] = useState<number[]>([15, 30, 60])
  const [showSettings, setShowSettings] = useState(false)
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [apiModel, setApiModel] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const running = job && (job.status === 'queued' || job.status === 'running')
  const hasTranscript = !!project.transcript
  const aiClips = project.clips.filter((c) => c.source === 'ai')

  // Load status + settings on mount
  useEffect(() => {
    api.highlightStatus().then((s) => {
      setStatus(s)
      setProvider(s.default_provider as 'ollama' | 'openai')
    }).catch(() => {})
    api.getHighlightSettings().then((s) => {
      setProvider(s.provider)
      setModel(s.provider === 'ollama' ? s.ollama_model : s.openai_model)
      setOllamaUrl(s.ollama_url)
      setApiKey(s.openai_api_key)
      setApiBase(s.openai_base_url)
      setApiModel(s.openai_model)
    }).catch(() => {})
  }, [])

  // Refresh when highlight job finishes
  useEffect(() => {
    if (job?.status === 'done') onComplete()
  }, [job?.status, onComplete])

  const toggleDuration = (d: number) => {
    setDurations((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b),
    )
  }

  const startHighlight = async () => {
    setErr(null)
    try {
      await api.startHighlight(project.id, {
        provider,
        model: model || null,
        max_clips: maxClips,
        target_durations: durations.length ? durations : [30],
        min_score: minScore,
      })
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const saveSettings = async () => {
    setSaving(true)
    try {
      await api.updateHighlightSettings({
        provider,
        ollama_model: model,
        ollama_url: ollamaUrl,
        openai_api_key: apiKey,
        openai_base_url: apiBase,
        openai_model: apiModel,
      })
      // Refresh status
      const s = await api.highlightStatus()
      setStatus(s)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const refreshStatus = async () => {
    try {
      const s = await api.highlightStatus()
      setStatus(s)
    } catch {}
  }

  const ollamaOk = status?.ollama?.available ?? false
  const openaiOk = status?.openai?.configured ?? false
  const providerReady = provider === 'ollama' ? ollamaOk : openaiOk
  const canStart = hasTranscript && providerReady && !running

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50">
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-4 py-2.5">
        <h3 className="font-semibold">✨ AI Auto-Clip</h3>
        {aiClips.length > 0 && (
          <span className="text-xs text-zinc-500">
            {aiClips.length} klip AI ditemukan
          </span>
        )}
        <button
          onClick={() => setShowSettings((s) => !s)}
          className="ml-auto text-xs text-zinc-500 hover:text-zinc-300"
          title="Pengaturan AI"
        >
          ⚙ Pengaturan
        </button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="space-y-3 border-b border-zinc-800 px-4 py-3 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-zinc-400">Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                const p = e.target.value as 'ollama' | 'openai'
                setProvider(p)
                if (p === 'ollama') setModel(status?.ollama?.models?.[0] || 'qwen2.5:3b')
                else setModel(apiModel || 'gemini-2.0-flash')
              }}
              className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1"
            >
              <option value="ollama">
                Ollama (Lokal) {ollamaOk ? '✓' : '✗'}
              </option>
              <option value="openai">
                Cloud API {openaiOk ? '✓' : ''}
              </option>
            </select>
            <button onClick={refreshStatus} className="rounded bg-zinc-800 px-2 py-1 hover:bg-zinc-700" title="Refresh status">
              ↻
            </button>
          </div>

          {provider === 'ollama' ? (
            <>
              <div className="flex items-center gap-2">
                <label className="w-20 text-zinc-400">URL Ollama</label>
                <input
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="w-20 text-zinc-400">Model</label>
                {ollamaOk && status?.ollama?.models?.length ? (
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1"
                  >
                    {status.ollama.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="qwen2.5:3b"
                    className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
                  />
                )}
              </div>
              {!ollamaOk && (
                <p className="text-amber-400">
                  ⚠ Ollama tidak terdeteksi di {ollamaUrl}. Pastikan Ollama berjalan dan model sudah di-pull.
                </p>
              )}
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <label className="w-20 text-zinc-400">Base URL</label>
                <input
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder="https://generativelanguage.googleapis.com/v1beta/openai"
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="w-20 text-zinc-400">API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-... atau AIza..."
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="w-20 text-zinc-400">Model</label>
                <input
                  value={apiModel}
                  onChange={(e) => { setApiModel(e.target.value); setModel(e.target.value) }}
                  placeholder="gemini-2.0-flash"
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
                />
              </div>
            </>
          )}

          <button
            onClick={saveSettings}
            disabled={saving}
            className="rounded bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700 disabled:opacity-50"
          >
            {saving ? 'Menyimpan…' : 'Simpan pengaturan'}
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="px-4 py-4">
        {running ? (
          <div>
            <p className="text-sm text-zinc-300">{job!.status === 'queued' ? 'Menunggu antrian…' : job!.message}</p>
            <div className="mt-2 h-2 overflow-hidden rounded bg-zinc-800">
              <div className="h-full bg-rose-500 transition-all" style={{ width: `${job!.progress * 100}%` }} />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              {provider === 'ollama'
                ? 'Berjalan di CPU lokal — mungkin butuh beberapa menit.'
                : 'Mengirim ke cloud API…'}
            </p>
          </div>
        ) : !hasTranscript ? (
          <p className="text-sm text-zinc-400">
            ⚠ Memerlukan transkrip — jalankan transkripsi di panel di atas terlebih dahulu.
          </p>
        ) : (
          <div className="space-y-3">
            {/* Controls */}
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div className="flex items-center gap-1.5">
                <span className="text-zinc-400">Durasi target:</span>
                {DURATIONS.map((d) => (
                  <button
                    key={d}
                    onClick={() => toggleDuration(d)}
                    className={`rounded px-2 py-1 ${durations.includes(d) ? 'bg-rose-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}
                  >
                    {d}s
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs">
              <label className="flex items-center gap-1.5">
                <span className="text-zinc-400">Maks klip</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxClips}
                  onChange={(e) => setMaxClips(Math.max(1, Math.min(20, Number(e.target.value))))}
                  className="w-14 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-center"
                />
              </label>
              <label className="flex flex-1 items-center gap-1.5">
                <span className="text-zinc-400">Skor min</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="flex-1 accent-rose-500"
                />
                <span className="w-8 text-right font-mono text-zinc-300">{minScore}</span>
              </label>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={startHighlight}
                disabled={!canStart}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold hover:bg-rose-500 disabled:opacity-50"
              >
                🔍 Cari Highlight Otomatis
              </button>
              <span className="text-xs text-zinc-500">
                via {provider === 'ollama' ? `Ollama (${model || 'qwen2.5:3b'})` : `API (${model || apiModel || 'gemini-2.0-flash'})`}
              </span>
            </div>
          </div>
        )}

        {job?.status === 'done' && (
          <p className="mt-2 text-sm text-emerald-400">
            ✓ {job.message}
          </p>
        )}
        {job?.status === 'error' && (
          <p className="mt-2 break-words text-xs text-red-400">
            Gagal: {job.error}
          </p>
        )}
        {err && <p className="mt-2 text-xs text-red-400">{err}</p>}
      </div>
    </section>
  )
}

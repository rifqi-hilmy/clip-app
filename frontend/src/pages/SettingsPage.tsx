import { useEffect, useState } from 'react'
import { api, type HighlightSettings } from '../api'

export default function SettingsPage() {
  const [hl, setHl] = useState<HighlightSettings | null>(null)
  const [encoder, setEncoder] = useState('h264_amf')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [tools, setTools] = useState<Record<string, any> | null>(null)

  useEffect(() => {
    api.getHighlightSettings().then(setHl).catch(() => {})
    api.health().then((h) => {
      setTools(h.tools)
      if (h.tools?.ffmpeg?.h264_amf) setEncoder('h264_amf')
      else setEncoder('libx264')
    }).catch(() => {})
  }, [])

  const save = async () => {
    if (!hl) return
    setSaving(true)
    setMsg(null)
    try {
      await api.updateHighlightSettings(hl)
      setMsg('✓ Tersimpan')
    } catch (e) {
      setMsg(`Error: ${(e as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <a href="#/" className="text-xs text-zinc-500 hover:text-zinc-300">← Kembali</a>
        <h1 className="mt-1 text-2xl font-bold">⚙ Pengaturan</h1>
      </div>

      {/* System info */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3">
        <h2 className="font-semibold">Sistem</h2>
        {tools && (
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <div className="flex justify-between rounded bg-zinc-800/50 px-3 py-2">
              <span className="text-zinc-400">FFmpeg</span>
              <span className={tools.ffmpeg?.ok ? 'text-emerald-400' : 'text-red-400'}>
                {tools.ffmpeg?.ok ? tools.ffmpeg.version?.split(' ').slice(0, 3).join(' ') : '✗ Tidak ditemukan'}
              </span>
            </div>
            <div className="flex justify-between rounded bg-zinc-800/50 px-3 py-2">
              <span className="text-zinc-400">AMD AMF (GPU)</span>
              <span className={tools.ffmpeg?.h264_amf ? 'text-emerald-400' : 'text-zinc-500'}>
                {tools.ffmpeg?.h264_amf ? '✓ Tersedia' : '✗ Tidak ada'}
              </span>
            </div>
            <div className="flex justify-between rounded bg-zinc-800/50 px-3 py-2">
              <span className="text-zinc-400">yt-dlp</span>
              <span className={tools.yt_dlp?.ok ? 'text-emerald-400' : 'text-red-400'}>
                {tools.yt_dlp?.ok ? `v${tools.yt_dlp.version}` : '✗'}
              </span>
            </div>
            <div className="flex justify-between rounded bg-zinc-800/50 px-3 py-2">
              <span className="text-zinc-400">JS Runtime</span>
              <span className={tools.js_runtime?.ok ? 'text-emerald-400' : 'text-red-400'}>
                {tools.js_runtime?.ok ? `${tools.js_runtime.name} ${tools.js_runtime.version}` : '✗'}
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-3 text-sm">
          <span className="text-zinc-400">Video Encoder</span>
          <select
            value={encoder}
            onChange={(e) => setEncoder(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1"
          >
            <option value="h264_amf">h264_amf (GPU AMD — cepat)</option>
            <option value="libx264">libx264 (CPU — kompatibel)</option>
          </select>
        </div>
      </section>

      {/* AI / LLM settings */}
      {hl && (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
          <h2 className="font-semibold">🤖 AI / LLM</h2>

          <div className="flex items-center gap-3 text-sm">
            <label className="w-32 text-zinc-400">Provider default</label>
            <select
              value={hl.provider}
              onChange={(e) => setHl({ ...hl, provider: e.target.value as 'ollama' | 'openai' })}
              className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1"
            >
              <option value="ollama">Ollama (Lokal)</option>
              <option value="openai">Cloud API</option>
            </select>
          </div>

          <fieldset className="rounded-lg border border-zinc-800 p-4 space-y-2">
            <legend className="px-2 text-xs font-semibold text-zinc-400">Ollama (Lokal)</legend>
            <div className="flex items-center gap-3 text-sm">
              <label className="w-24 text-zinc-400">URL</label>
              <input
                value={hl.ollama_url}
                onChange={(e) => setHl({ ...hl, ollama_url: e.target.value })}
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex items-center gap-3 text-sm">
              <label className="w-24 text-zinc-400">Model</label>
              <input
                value={hl.ollama_model}
                onChange={(e) => setHl({ ...hl, ollama_model: e.target.value })}
                placeholder="qwen2.5:3b"
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
              />
            </div>
          </fieldset>

          <fieldset className="rounded-lg border border-zinc-800 p-4 space-y-2">
            <legend className="px-2 text-xs font-semibold text-zinc-400">Cloud API (OpenAI-compatible)</legend>
            <div className="flex items-center gap-3 text-sm">
              <label className="w-24 text-zinc-400">Base URL</label>
              <input
                value={hl.openai_base_url}
                onChange={(e) => setHl({ ...hl, openai_base_url: e.target.value })}
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex items-center gap-3 text-sm">
              <label className="w-24 text-zinc-400">API Key</label>
              <input
                type="password"
                value={hl.openai_api_key}
                onChange={(e) => setHl({ ...hl, openai_api_key: e.target.value })}
                placeholder="sk-... atau AIza..."
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex items-center gap-3 text-sm">
              <label className="w-24 text-zinc-400">Model</label>
              <input
                value={hl.openai_model}
                onChange={(e) => setHl({ ...hl, openai_model: e.target.value })}
                placeholder="gemini-2.0-flash"
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 outline-none focus:border-rose-500"
              />
            </div>
          </fieldset>

          <div className="flex items-center gap-3">
            <button
              onClick={save}
              disabled={saving}
              className="rounded-lg bg-rose-600 px-5 py-2 font-semibold hover:bg-rose-500 disabled:opacity-50"
            >
              {saving ? 'Menyimpan…' : 'Simpan'}
            </button>
            {msg && <span className={`text-sm ${msg.startsWith('✓') ? 'text-emerald-400' : 'text-red-400'}`}>{msg}</span>}
          </div>
        </section>
      )}

      {/* Keyboard shortcuts reference */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
        <h2 className="font-semibold">⌨ Keyboard Shortcuts</h2>
        <div className="grid gap-1 text-sm sm:grid-cols-2">
          {[
            ['Space', 'Play / Pause'],
            ['I', 'Set IN point'],
            ['O', 'Set OUT point'],
            ['Enter', 'Tambah klip'],
            ['← / →', 'Seek 1s (Shift = 5s)'],
            [', / .', 'Seek per frame'],
            ['Esc', 'Reset IN/OUT'],
          ].map(([key, desc]) => (
            <div key={key} className="flex gap-2 rounded bg-zinc-800/50 px-3 py-1.5">
              <kbd className="rounded bg-zinc-700 px-2 py-0.5 font-mono text-xs text-zinc-200">{key}</kbd>
              <span className="text-zinc-400">{desc}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

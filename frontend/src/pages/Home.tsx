import { useEffect, useState } from 'react'
import { api, fmtTime, type ProjectSummary, type StorageUsage, type VideoInfo } from '../api'
import { useServerEvents } from '../useServerEvents'

// Sprint 1/T3: storage usage bar + per-project cleanup
function StorageBar({ onChanged }: { onChanged: () => void }) {
  const [usage, setUsage] = useState<StorageUsage | null>(null)
  const [open, setOpen] = useState(false)
  const load = () => api.storageUsage().then(setUsage).catch(() => {})
  useEffect(() => { load() }, [])
  useServerEvents((e) => {
    if (e.type === 'project' || (e.type === 'job' && e.job.status !== 'running')) load()
  })
  if (!usage) return null
  const gb = (mb: number) => (mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(0)} MB`)
  const del = async (pid: number, name: string) => {
    if (!confirm(`Hapus file video sumber project "${name}"? Klip & transkrip tetap ada, bisa download ulang.`)) return
    try { await api.deleteSource(pid); onChanged(); load() } catch (e) { alert((e as Error).message) }
  }
  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between text-left">
        <span className="text-sm font-semibold">💾 Penyimpanan: {gb(usage.total_mb)}</span>
        <span className="text-xs text-zinc-500">
          video {gb(usage.videos_mb)} · hasil {gb(usage.exports_mb)} {open ? '▴' : '▾'}
        </span>
      </button>
      <div className="mt-2 h-2 overflow-hidden rounded bg-zinc-800">
        <div className="h-full bg-sky-500" style={{ width: `${usage.total_mb > 0 ? Math.min(100, (usage.videos_mb / usage.total_mb) * 100) : 0}%` }} />
      </div>
      {open && (
        <div className="mt-3 space-y-1">
          {usage.by_project.map((p) => (
            <div key={p.project_id} className="flex items-center gap-2 text-xs">
              <span className="flex-1 truncate text-zinc-300">{p.name}</span>
              <span className="font-mono text-zinc-500">{gb(p.mb)}</span>
              <button
                onClick={() => del(p.project_id, p.name)}
                className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-400 hover:bg-red-600 hover:text-white"
                title="Hapus file video sumber (hemat disk)"
              >
                🗑 source
              </button>
            </div>
          ))}
          {usage.by_project.length === 0 && <p className="text-xs text-zinc-500">Kosong.</p>}
        </div>
      )}
    </section>
  )
}

const STATUS_STYLE: Record<string, string> = {
  ready: 'bg-emerald-500/15 text-emerald-400',
  downloading: 'bg-sky-500/15 text-sky-400',
  created: 'bg-zinc-700/40 text-zinc-300',
  error: 'bg-red-500/15 text-red-400',
}

function SystemStatus() {
  const [tools, setTools] = useState<Record<string, any> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    api.health().then((h) => setTools(h.tools)).catch((e) => setErr(String(e)))
  }, [])
  if (err) return <p className="text-sm text-red-400">Backend tidak terjangkau. Jalankan start.bat.</p>
  if (!tools) return null
  const items = Object.entries(tools).filter(([, v]) => typeof v === 'object')
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {items.map(([k, v]) => (
        <span key={k} className={`rounded px-2 py-0.5 ${v.ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {k} {v.ok ? '✓' : '✗'}
        </span>
      ))}
      {tools.ffmpeg?.h264_amf && <span className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-400">AMF GPU encode ✓</span>}
    </div>
  )
}

export default function Home() {
  const [url, setUrl] = useState('')
  const [language, setLanguage] = useState('')
  const [info, setInfo] = useState<VideoInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])

  const load = () => api.listProjects().then(setProjects).catch(() => {})
  useEffect(() => {
    load()
  }, [])
  useServerEvents((e) => {
    if (e.type === 'project' || (e.type === 'job' && e.job.status !== 'running')) load()
  })

  const preview = async () => {
    setError(null)
    setInfo(null)
    setBusy(true)
    try {
      setInfo(await api.videoInfo(url))
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const p = await api.createProject(url, language)
      location.hash = `#/project/${p.id}`
    } catch (e) {
      setError(String((e as Error).message))
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Hapus project ini? (video sumber tetap tersimpan di cache)')) return
    await api.deleteProject(id)
    load()
  }

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6">
        <h1 className="text-2xl font-bold">Buat klip baru</h1>
        <p className="mb-4 mt-1 text-sm text-zinc-400">Tempel link YouTube, lalu potong jadi klip vertikal 9:16.</p>

        <form
          className="flex flex-col gap-3 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) preview()
          }}
        >
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 outline-none focus:border-rose-500"
          />
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5"
            title="Bahasa konten (dipakai saat transkripsi di Fase 2)"
          >
            <option value="">Bahasa: Auto</option>
            <option value="id">Indonesia</option>
            <option value="en">English</option>
          </select>
          <button
            disabled={busy || !url.trim()}
            className="rounded-lg bg-zinc-800 px-5 py-2.5 font-medium hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy && !info ? 'Memuat…' : 'Preview'}
          </button>
        </form>

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        {info && (
          <div className="mt-5 flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-900/70 p-4 sm:flex-row">
            <img src={info.thumbnail} alt="" className="aspect-video w-full rounded-lg object-cover sm:w-64" />
            <div className="flex flex-1 flex-col">
              <h3 className="font-semibold">{info.title}</h3>
              <p className="text-sm text-zinc-400">{info.channel}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-400">
                <span className="rounded bg-zinc-800 px-2 py-0.5">⏱ {fmtTime(info.duration)}</span>
                <span className="rounded bg-zinc-800 px-2 py-0.5">
                  🔥 Most Replayed: {info.has_heatmap ? 'ada' : 'tidak ada'}
                </span>
                <span className="rounded bg-zinc-800 px-2 py-0.5">📑 {info.chapters_count} chapters</span>
              </div>
              <button
                onClick={create}
                disabled={busy}
                className="mt-auto self-start rounded-lg bg-rose-600 px-5 py-2 font-semibold hover:bg-rose-500 disabled:opacity-50"
              >
                {busy ? 'Membuat…' : 'Buat Project & Download'}
              </button>
            </div>
          </div>
        )}

        <div className="mt-5">
          <SystemStatus />
        </div>
      </section>

      {/* Local file import */}
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">📁 Import Video Lokal</h2>
            <p className="mt-1 text-sm text-zinc-400">Gunakan file video dari komputer (MP4, MKV, WEBM, AVI, MOV).</p>
          </div>
          <a href="#/settings" className="rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700">
            ⚙ Settings
          </a>
        </div>
        <div className="mt-3 flex gap-3">
          <input
            id="local-path"
            placeholder="D:\Videos\my-video.mp4"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 outline-none focus:border-rose-500"
          />
          <button
            onClick={async () => {
              const input = document.getElementById('local-path') as HTMLInputElement
              const p = input?.value?.trim()
              if (!p) return
              setError(null)
              setBusy(true)
              try {
                const proj = await api.importLocal(p, '', language)
                location.hash = `#/project/${proj.id}`
              } catch (e) {
                setError((e as Error).message)
              } finally {
                setBusy(false)
              }
            }}
            disabled={busy}
            className="rounded-lg bg-rose-600 px-5 py-2.5 font-semibold hover:bg-rose-500 disabled:opacity-50"
          >
            Import
          </button>
        </div>
      </section>

      <StorageBar onChanged={load} />

      <section>
        <h2 className="mb-3 text-lg font-semibold">Project</h2>
        {projects.length === 0 && <p className="text-sm text-zinc-500">Belum ada project.</p>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <div key={p.id} className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
              <a href={`#/project/${p.id}`}>
                <img src={p.video.thumbnail} alt="" className="aspect-video w-full object-cover" />
              </a>
              <div className="p-3">
                <a href={`#/project/${p.id}`} className="line-clamp-2 font-medium hover:text-rose-400">
                  {p.name}
                </a>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <div className="flex gap-2">
                    <span className={`rounded px-2 py-0.5 ${STATUS_STYLE[p.status] ?? STATUS_STYLE.created}`}>{p.status}</span>
                    <span className="text-zinc-500">
                      {fmtTime(p.video.duration)} · {p.clip_count} klip
                    </span>
                  </div>
                  <button onClick={() => remove(p.id)} className="text-zinc-500 opacity-0 hover:text-red-400 group-hover:opacity-100">
                    Hapus
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fmtTime, type Job, type ProjectDetail, type Segment, type Transcript } from '../api'

type Props = {
  project: ProjectDetail
  job: Job | undefined
  current: number
  onSeek: (t: number) => void
  onCreateClip: (start: number, end: number, title: string) => void
}

const LANG_LABEL: Record<string, string> = { id: 'Indonesia', en: 'English' }

/**
 * Transcript panel: run Whisper, follow playback, click a line to seek,
 * shift+click to select a range of lines and turn it into a clip.
 */
export default function TranscriptPanel({ project, job, current, onSeek, onCreateClip }: Props) {
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [models, setModels] = useState<string[]>(['small'])
  const [model, setModel] = useState('small')
  const [language, setLanguage] = useState<string>(project.language ?? '')
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState<{ a: number; b: number } | null>(null)
  const [follow, setFollow] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const meta = project.transcript
  const running = job && (job.status === 'queued' || job.status === 'running')

  useEffect(() => {
    api.whisperModels().then((m) => {
      setModels(m.models)
      setModel(m.default)
    }).catch(() => {})
  }, [])

  // (re)load transcript when metadata changes (e.g. after a transcription job)
  useEffect(() => {
    if (!meta) {
      setTranscript(null)
      return
    }
    api.getTranscript(project.id).then(setTranscript).catch(() => setTranscript(null))
  }, [project.id, meta?.model, meta?.language, meta?.segments])

  const segments = transcript?.segments ?? []
  const activeIdx = useMemo(() => {
    // last segment that started before the playhead
    let lo = 0, hi = segments.length - 1, ans = -1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (segments[mid].start <= current) {
        ans = mid
        lo = mid + 1
      } else hi = mid - 1
    }
    return ans
  }, [segments, current])

  useEffect(() => {
    if (!follow || activeIdx < 0 || query) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${activeIdx}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [activeIdx, follow, query])

  const q = query.trim().toLowerCase()
  const visible = q ? segments.filter((s) => s.text.toLowerCase().includes(q)) : segments
  const range = sel ? { a: Math.min(sel.a, sel.b), b: Math.max(sel.a, sel.b) } : null
  const selDuration = range ? segments[range.b].end - segments[range.a].start : 0

  const start = async (force: boolean) => {
    setErr(null)
    try {
      await api.transcribe(project.id, model, language || null, force)
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const clickSeg = (s: Segment, e: React.MouseEvent) => {
    if (e.shiftKey && sel) setSel({ a: sel.a, b: s.id })
    else {
      setSel({ a: s.id, b: s.id })
      onSeek(s.start)
    }
  }

  const highlight = (text: string) => {
    if (!q) return text
    const i = text.toLowerCase().indexOf(q)
    if (i < 0) return text
    return (
      <>
        {text.slice(0, i)}
        <mark className="rounded bg-amber-400/40 text-inherit">{text.slice(i, i + q.length)}</mark>
        {text.slice(i + q.length)}
      </>
    )
  }

  const controls = (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <select value={model} onChange={(e) => setModel(e.target.value)} className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1" title="Model lebih besar = lebih akurat tapi lebih lambat">
        {models.map((m) => (
          <option key={m} value={m}>Whisper {m}</option>
        ))}
      </select>
      <select value={language} onChange={(e) => setLanguage(e.target.value)} className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1">
        <option value="">Bahasa: Auto</option>
        <option value="id">Indonesia</option>
        <option value="en">English</option>
      </select>
    </div>
  )

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50">
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-4 py-2.5">
        <h3 className="font-semibold">Transkrip</h3>
        {meta && (
          <span className="text-xs text-zinc-500">
            {LANG_LABEL[meta.language] ?? meta.language} · {meta.segments} baris · whisper {meta.model}
          </span>
        )}
        {meta && !running && (
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cari kata…"
            className="ml-auto w-44 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs outline-none focus:border-rose-500"
          />
        )}
      </div>

      {running ? (
        <div className="px-4 py-6">
          <p className="text-sm text-zinc-300">{job!.status === 'queued' ? 'Antri…' : job!.message}</p>
          <div className="mt-2 h-2 overflow-hidden rounded bg-zinc-800">
            <div className="h-full bg-rose-500 transition-all" style={{ width: `${job!.progress * 100}%` }} />
          </div>
          <p className="mt-2 text-xs text-zinc-500">Berjalan di CPU. Model "small": kira-kira 1/4–1/3 durasi video.</p>
        </div>
      ) : !meta ? (
        <div className="space-y-3 px-4 py-6">
          <p className="text-sm text-zinc-400">
            Belum ada transkrip. Transkrip dipakai untuk caption otomatis, pencarian kata, dan (nanti) AI highlight.
          </p>
          {controls}
          <button onClick={() => start(false)} className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold hover:bg-rose-500">
            Mulai transkripsi
          </button>
          {job?.status === 'error' && <p className="break-words text-xs text-red-400">Gagal: {job.error}</p>}
          {err && <p className="text-xs text-red-400">{err}</p>}
        </div>
      ) : (
        <>
          <div ref={listRef} className="max-h-72 overflow-y-auto px-2 py-2" onWheel={() => setFollow(false)}>
            {visible.length === 0 && <p className="px-2 py-4 text-sm text-zinc-500">Tidak ada yang cocok.</p>}
            {visible.map((s) => {
              const inSel = range && s.id >= range.a && s.id <= range.b
              const active = s.id === activeIdx
              return (
                <div
                  key={s.id}
                  data-idx={s.id}
                  onClick={(e) => clickSeg(s, e)}
                  className={`flex cursor-pointer gap-3 rounded px-2 py-1 text-sm ${
                    inSel ? 'bg-emerald-500/15' : active ? 'bg-zinc-800' : 'hover:bg-zinc-800/60'
                  }`}
                >
                  <span className="w-12 shrink-0 pt-0.5 font-mono text-[11px] text-zinc-500">{fmtTime(s.start)}</span>
                  <span className={active ? 'text-white' : 'text-zinc-300'}>{highlight(s.text)}</span>
                </div>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 px-4 py-2 text-xs">
            {range ? (
              <>
                <span className="text-zinc-400">
                  {range.b - range.a + 1} baris · {selDuration.toFixed(1)}s
                </span>
                <button
                  onClick={() => {
                    const a = segments[range.a], b = segments[range.b]
                    const title = a.text.split(/\s+/).slice(0, 6).join(' ')
                    onCreateClip(Math.max(0, a.start - 0.15), b.end + 0.25, title)
                    setSel(null)
                  }}
                  className="rounded bg-rose-600 px-2.5 py-1 font-semibold hover:bg-rose-500"
                >
                  + Jadikan klip
                </button>
                <button onClick={() => setSel(null)} className="text-zinc-500 hover:text-zinc-300">batal</button>
              </>
            ) : (
              <span className="text-zinc-500">Klik baris = lompat · Shift+klik = pilih rentang → jadikan klip</span>
            )}
            {!follow && (
              <button onClick={() => setFollow(true)} className="rounded bg-zinc-800 px-2 py-1 hover:bg-zinc-700">
                ⤓ Ikuti playback
              </button>
            )}
            <details className="ml-auto">
              <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">Transkrip ulang</summary>
              <div className="mt-2 flex items-center gap-2">
                {controls}
                <button onClick={() => start(true)} className="rounded bg-zinc-800 px-2.5 py-1 hover:bg-zinc-700">Jalankan</button>
              </div>
            </details>
          </div>
          {err && <p className="px-4 pb-2 text-xs text-red-400">{err}</p>}
        </>
      )}
    </section>
  )
}

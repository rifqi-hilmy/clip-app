import { useEffect, useState } from 'react'
import { api, fmtTime, parseTime, type Clip, type Job } from '../api'

function TimeInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [text, setText] = useState(fmtTime(value, true))
  useEffect(() => setText(fmtTime(value, true)), [value])
  const commit = () => {
    const v = parseTime(text)
    if (v !== null && Math.abs(v - value) > 0.01) onCommit(v)
    else setText(fmtTime(value, true))
  }
  return (
    <input
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      className="w-20 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 font-mono text-xs"
    />
  )
}

type Props = {
  clip: Clip
  job: Job | undefined
  selected: boolean
  current: number
  hasTranscript: boolean
  captionPresets: { id: string; label: string }[]
  onSelect: () => void
  onPreview: () => void
  onChange: (patch: Partial<Clip>) => Promise<void>
  onDelete: () => void
}

export default function ClipCard({
  clip, job, selected, current, hasTranscript, captionPresets, onSelect, onPreview, onChange, onDelete,
}: Props) {
  const [err, setErr] = useState<string | null>(null)
  const [showExport, setShowExport] = useState(false)
  const [genMeta, setGenMeta] = useState<{ title: string; description: string; hashtags: string[] } | null>(null)
  const [generating, setGenerating] = useState(false)
  const busy = job && (job.status === 'queued' || job.status === 'running')

  const patch = async (p: Partial<Clip>) => {
    setErr(null)
    try {
      await onChange(p)
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const render = async () => {
    setErr(null)
    try {
      await api.renderClip(clip.id)
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  return (
    <div
      onClick={onSelect}
      className={`rounded-xl border p-3 transition ${selected ? 'border-amber-400/70 bg-zinc-900' : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700'}`}
    >
      <div className="flex items-center gap-2">
        {clip.source === 'ai' && (
          <span className="shrink-0 rounded bg-violet-600/30 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">
            🤖 AI
          </span>
        )}
        {clip.source === 'ai' && clip.score != null && (
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
              clip.score >= 70 ? 'bg-emerald-600/30 text-emerald-300'
              : clip.score >= 40 ? 'bg-amber-600/30 text-amber-300'
              : 'bg-zinc-700 text-zinc-400'
            }`}
          >
            {Math.round(clip.score)}
          </span>
        )}
        <input
          defaultValue={clip.title}
          key={clip.title}
          onBlur={(e) => e.target.value !== clip.title && patch({ title: e.target.value })}
          className="flex-1 truncate rounded bg-transparent px-1 font-medium outline-none focus:bg-zinc-950"
        />
        <span className="font-mono text-xs text-zinc-400">{(clip.end - clip.start).toFixed(1)}s</span>
        <button onClick={(e) => (e.stopPropagation(), onDelete())} className="text-xs text-zinc-500 hover:text-red-400" title="Hapus klip">
          ✕
        </button>
      </div>
      {clip.source === 'ai' && clip.reason && !selected && (
        <p className="mt-1 truncate text-[11px] text-zinc-500 italic">{clip.reason}</p>
      )}

      {selected && (
        <div className="mt-3 space-y-3 text-xs" onClick={(e) => e.stopPropagation()}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-zinc-500">Start</span>
            <TimeInput value={clip.start} onCommit={(v) => patch({ start: v })} />
            <button onClick={() => patch({ start: current })} className="rounded bg-zinc-800 px-1.5 py-0.5 hover:bg-zinc-700" title="Set start = posisi sekarang">
              ⇤ now
            </button>
            <span className="ml-2 text-zinc-500">End</span>
            <TimeInput value={clip.end} onCommit={(v) => patch({ end: v })} />
            <button onClick={() => patch({ end: current })} className="rounded bg-zinc-800 px-1.5 py-0.5 hover:bg-zinc-700" title="Set end = posisi sekarang">
              now ⇥
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={clip.aspect}
              onChange={(e) => patch({ aspect: e.target.value as Clip['aspect'] })}
              className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1"
            >
              <option value="9:16">9:16 (Shorts/TikTok)</option>
              <option value="original">Rasio asli</option>
            </select>
            {clip.aspect === '9:16' && (
              <select
                value={clip.reframe}
                onChange={(e) => patch({ reframe: e.target.value as Clip['reframe'] })}
                className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1"
              >
                <option value="blur">Blur background</option>
                <option value="face">🎯 Face tracking</option>
                <option value="center">Crop (geser manual)</option>
              </select>
            )}
            <select
              value={clip.caption_style ?? ''}
              disabled={!hasTranscript}
              onChange={(e) => patch({ caption_style: e.target.value || null })}
              title={hasTranscript ? 'Gaya caption' : 'Jalankan transkripsi dulu untuk caption'}
              className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 disabled:opacity-50"
            >
              <option value="">Tanpa caption</option>
              {captionPresets.map((p) => (
                <option key={p.id} value={p.id}>Caption: {p.label}</option>
              ))}
            </select>
          </div>

          {clip.aspect === '9:16' && clip.reframe === 'center' && (
            <label className="flex items-center gap-2">
              <span className="text-zinc-500">Posisi crop</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                defaultValue={clip.crop_x}
                key={clip.crop_x}
                onMouseUp={(e) => patch({ crop_x: Number((e.target as HTMLInputElement).value) })}
                onKeyUp={(e) => patch({ crop_x: Number((e.target as HTMLInputElement).value) })}
                className="flex-1 accent-amber-400"
              />
              <span className="w-8 text-right font-mono">{Math.round(clip.crop_x * 100)}%</span>
            </label>
          )}

          <div className="flex items-center gap-2">
            <button onClick={onPreview} className="rounded-md bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700">
              ▶ Preview
            </button>
            <button onClick={render} disabled={busy} className="rounded-md bg-rose-600 px-3 py-1.5 font-semibold hover:bg-rose-500 disabled:opacity-50">
              {busy ? 'Rendering…' : clip.export_url ? 'Render ulang' : 'Render'}
            </button>
            {clip.export_url && (
              <>
                <button onClick={() => setShowExport((s) => !s)} className="rounded-md bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700">
                  {showExport ? 'Tutup' : 'Lihat hasil'}
                </button>
                <a href={clip.export_url} download className="rounded-md bg-emerald-600 px-3 py-1.5 font-semibold hover:bg-emerald-500">
                  ⬇
                </a>
                {clip.srt_url && (
                  <a href={clip.srt_url} download className="rounded-md bg-zinc-800 px-2 py-1.5 hover:bg-zinc-700" title="Download subtitle SRT">
                    SRT
                  </a>
                )}
              </>
            )}
          </div>

          {/* Generate title/hashtags via AI */}
          {hasTranscript && (
            <div className="space-y-2 border-t border-zinc-800 pt-2">
              <button
                onClick={async () => {
                  setGenerating(true)
                  setErr(null)
                  try {
                    const meta = await api.generateMeta(clip.id)
                    setGenMeta(meta)
                    // Auto-apply the title
                    await patch({ title: meta.title })
                  } catch (e) {
                    setErr((e as Error).message)
                  } finally {
                    setGenerating(false)
                  }
                }}
                disabled={generating}
                className="rounded bg-violet-600/80 px-2.5 py-1 text-violet-100 hover:bg-violet-600 disabled:opacity-50"
              >
                {generating ? '✨ Generating…' : '✨ Generate judul & hashtag'}
              </button>
              {genMeta && (
                <div className="space-y-1 rounded bg-zinc-800/50 p-2 text-[11px]">
                  <p className="text-zinc-300"><strong>Deskripsi:</strong> {genMeta.description}</p>
                  <p className="text-zinc-400">
                    {genMeta.hashtags.map((h) => `#${h.replace(/^#/, '')}`).join(' ')}
                  </p>
                  <button
                    onClick={() => navigator.clipboard.writeText(
                      `${genMeta.description}\n\n${genMeta.hashtags.map(h => `#${h.replace(/^#/, '')}`).join(' ')}`
                    )}
                    className="rounded bg-zinc-700 px-2 py-0.5 text-zinc-300 hover:bg-zinc-600"
                  >
                    📋 Copy
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {job && (job.status === 'running' || job.status === 'queued') && (
        <div className="mt-2">
          <div className="h-1.5 overflow-hidden rounded bg-zinc-800">
            <div className="h-full bg-rose-500 transition-all" style={{ width: `${job.progress * 100}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-zinc-500">{job.status === 'queued' ? 'Antri…' : job.message}</p>
        </div>
      )}
      {job?.status === 'error' && <p className="mt-2 break-words text-[11px] text-red-400">Render gagal: {job.error}</p>}
      {err && <p className="mt-2 text-[11px] text-red-400">{err}</p>}
      {!selected && clip.export_url && <p className="mt-1 text-[11px] text-emerald-400">✓ sudah dirender</p>}

      {selected && showExport && clip.export_url && (
        <video
          key={clip.export_url + (job?.id ?? '')}
          src={`${clip.export_url}?v=${job?.id ?? 0}`}
          controls
          className="mx-auto mt-3 max-h-[480px] rounded-lg bg-black"
          onClick={(e) => e.stopPropagation()}
        />
      )}
    </div>
  )
}

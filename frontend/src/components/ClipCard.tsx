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
        {/* Sprint 1/T4: review badge */}
        {clip.review_state === 'pending' && (
          <span className="shrink-0 rounded bg-amber-600/30 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
            ⏳ Perlu review
          </span>
        )}
        {clip.review_state === 'rejected' && (
          <span className="shrink-0 rounded bg-red-600/30 px-1.5 py-0.5 text-[10px] font-semibold text-red-300">
            ✕ Ditolak
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
              <option value="1:1">1:1 (Feed)</option>
              <option value="4:5">4:5 (Feed IG/FB)</option>
              <option value="original">Rasio asli</option>
            </select>
            {clip.aspect !== 'original' && (
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
            {/* Sprint 1/T5: safe zone */}
            <select
              value={clip.safe_zone ?? ''}
              onChange={(e) => patch({ safe_zone: e.target.value || null })}
              title="Zona aman platform (caption & teks tidak tertutup UI)"
              className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1"
            >
              <option value="">Safe-zone: off</option>
              <option value="tiktok">📱 TikTok</option>
              <option value="reels">📸 Reels</option>
              <option value="shorts">▶ Shorts</option>
            </select>
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

          {clip.aspect !== 'original' && clip.reframe === 'center' && (
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

          {/* Sprint 1: audio & silence controls */}
          <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-950/50 p-2">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={clip.loudnorm}
                onChange={(e) => patch({ loudnorm: e.target.checked })}
                className="accent-emerald-500"
              />
              <span className="text-zinc-300">🔊 Normalisasi volume</span>
              <span className="text-[10px] text-zinc-500">(-16 LUFS)</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={clip.remove_silence}
                onChange={(e) => patch({ remove_silence: e.target.checked })}
                className="accent-emerald-500"
              />
              <span className="text-zinc-300">✂️ Buang jeda diam</span>
            </label>
            {clip.remove_silence && (
              <div className="space-y-1.5 pl-6">
                <label className="flex items-center gap-2">
                  <span className="w-24 text-zinc-500">Threshold</span>
                  <input
                    type="range" min={-50} max={-20} step={1}
                    defaultValue={clip.silence_db} key={`db${clip.silence_db}`}
                    onMouseUp={(e) => patch({ silence_db: Number((e.target as HTMLInputElement).value) })}
                    className="flex-1 accent-amber-400"
                  />
                  <span className="w-12 text-right font-mono">{clip.silence_db} dB</span>
                </label>
                <label className="flex items-center gap-2">
                  <span className="w-24 text-zinc-500">Min. jeda</span>
                  <input
                    type="range" min={0.3} max={3} step={0.1}
                    defaultValue={clip.silence_min_dur} key={`md${clip.silence_min_dur}`}
                    onMouseUp={(e) => patch({ silence_min_dur: Number((e.target as HTMLInputElement).value) })}
                    className="flex-1 accent-amber-400"
                  />
                  <span className="w-12 text-right font-mono">{clip.silence_min_dur.toFixed(1)}s</span>
                </label>
              </div>
            )}
          </div>

          {/* Sprint 1/T4: quick review actions */}
          {clip.review_state === 'pending' && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-600/10 p-2">
              <span className="flex-1 text-amber-200">Klip AI ini perlu direview:</span>
              <button
                onClick={async () => {
                  setErr(null)
                  try { await api.reviewClip(clip.id, 'approved'); await onChange({}) } catch (e) { setErr((e as Error).message) }
                }}
                className="rounded bg-emerald-600 px-2.5 py-1 font-semibold hover:bg-emerald-500"
              >
                ✓ Terima
              </button>
              <button
                onClick={async () => {
                  setErr(null)
                  try { await api.reviewClip(clip.id, 'rejected'); await onChange({}) } catch (e) { setErr((e as Error).message) }
                }}
                className="rounded bg-zinc-700 px-2.5 py-1 hover:bg-zinc-600"
              >
                Tolak
              </button>
            </div>
          )}

          <div className="flex items-center gap-2">
            <button onClick={onPreview} className="rounded-md bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700">
              ▶ Preview
            </button>
            <button
              onClick={render}
              disabled={busy || clip.review_state !== 'approved'}
              title={clip.review_state !== 'approved' ? 'Terima klip ini di review dulu' : undefined}
              className="rounded-md bg-rose-600 px-3 py-1.5 font-semibold hover:bg-rose-500 disabled:opacity-50"
            >
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

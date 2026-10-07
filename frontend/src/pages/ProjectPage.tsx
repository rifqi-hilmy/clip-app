import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, fmtTime, type Clip, type Job, type ProjectDetail } from '../api'
import ClipCard from '../components/ClipCard'
import HighlightPanel from '../components/HighlightPanel'
import Timeline from '../components/Timeline'
import TranscriptPanel from '../components/TranscriptPanel'
import { useServerEvents } from '../useServerEvents'

const FRAME = 1 / 30

export default function ProjectPage({ projectId }: { projectId: number }) {
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [jobs, setJobs] = useState<Record<number, Job>>({})
  const [presets, setPresets] = useState<{ id: string; label: string }[]>([])
  const [error, setError] = useState<string | null>(null)
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [markIn, setMarkIn] = useState<number | null>(null)
  const [markOut, setMarkOut] = useState<number | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [videoRatio, setVideoRatio] = useState(16 / 9)
  const videoRef = useRef<HTMLVideoElement>(null)
  const stopAt = useRef<number | null>(null)

  useEffect(() => {
    api.captionPresets().then(setPresets).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    try {
      const p = await api.getProject(projectId)
      setProject(p)
      setJobs((prev) => {
        const next = { ...prev }
        p.jobs.forEach((j) => (next[j.id] = j))
        return next
      })
    } catch (e) {
      setError((e as Error).message)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  useServerEvents((e) => {
    if (e.type === 'job' && e.job.project_id === projectId) {
      setJobs((prev) => ({ ...prev, [e.job.id]: e.job }))
      if (e.job.status === 'done' || e.job.status === 'error') load()
    } else if (e.type === 'project' && e.project_id === projectId) load()
  })

  const clips = project?.clips ?? []
  const selected = clips.find((c) => c.id === selectedId) ?? null
  const video = project?.video
  const duration = video?.duration ?? 0

  // latest job per clip + latest download / transcribe job
  const { clipJobs, downloadJob, transcribeJob, highlightJob } = useMemo(() => {
    const clipJobs: Record<number, Job> = {}
    let downloadJob: Job | undefined
    let transcribeJob: Job | undefined
    let highlightJob: Job | undefined
    Object.values(jobs)
      .sort((a, b) => a.id - b.id)
      .forEach((j) => {
        if (j.type === 'render' && j.clip_id) clipJobs[j.clip_id] = j
        if (j.type === 'download') downloadJob = j
        if (j.type === 'transcribe') transcribeJob = j
        if (j.type === 'highlight') highlightJob = j
      })
    return { clipJobs, downloadJob, transcribeJob, highlightJob }
  }, [jobs])

  // ---------- player controls ----------
  const seek = useCallback((t: number) => {
    const v = videoRef.current
    if (!v) return
    stopAt.current = null
    v.currentTime = Math.min(Math.max(t, 0), v.duration || duration)
    setCurrent(v.currentTime)
  }, [duration])

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) v.play()
    else v.pause()
  }, [])

  const previewClip = (c: Clip) => {
    const v = videoRef.current
    if (!v) return
    v.currentTime = c.start
    stopAt.current = c.end
    v.play()
  }

  const createClip = useCallback(async (start: number, end: number, title = '') => {
    setError(null)
    try {
      const c = await api.createClip(projectId, {
        start, end: Math.min(end, duration), title, aspect: '9:16', reframe: 'blur',
        caption_style: project?.transcript ? 'bold' : null,
      })
      setSelectedId(c.id)
      await load()
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    }
  }, [projectId, duration, project?.transcript, load])

  const addClip = useCallback(async () => {
    const start = markIn ?? current
    const end = markOut ?? Math.min(start + 30, duration)
    if (end - start < 1) {
      setError('Klip minimal 1 detik — set IN (I) dan OUT (O) dulu.')
      return
    }
    if (await createClip(start, end)) {
      setMarkIn(null)
      setMarkOut(null)
    }
  }, [markIn, markOut, current, duration, createClip])

  const updateClip = async (id: number, patch: Partial<Clip>) => {
    await api.updateClip(id, patch)
    await load()
  }

  const deleteClip = async (id: number) => {
    if (!confirm('Hapus klip ini?')) return
    await api.deleteClip(id)
    if (selectedId === id) setSelectedId(null)
    await load()
  }

  // keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      const v = videoRef.current
      if (!v) return
      const step = e.shiftKey ? 5 : 1
      switch (e.key) {
        case ' ':
          e.preventDefault()
          togglePlay()
          break
        case 'i':
        case 'I':
          setMarkIn(v.currentTime)
          break
        case 'o':
        case 'O':
          setMarkOut(v.currentTime)
          break
        case 'Enter':
          addClip()
          break
        case 'ArrowLeft':
          e.preventDefault()
          seek(v.currentTime - step)
          break
        case 'ArrowRight':
          e.preventDefault()
          seek(v.currentTime + step)
          break
        case ',':
          v.pause()
          seek(v.currentTime - FRAME)
          break
        case '.':
          v.pause()
          seek(v.currentTime + FRAME)
          break
        case 'Escape':
          setMarkIn(null)
          setMarkOut(null)
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePlay, seek, addClip])

  if (error && !project) return <p className="text-red-400">{error}</p>
  if (!project || !video) return <p className="text-zinc-400">Memuat…</p>

  const ready = project.status === 'ready' && video.media_url
  const showCrop = selected && selected.aspect === '9:16' && selected.reframe === 'center'
  const cropW = Math.min(1, (9 / 16) / videoRatio)

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <div className="min-w-0 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <a href="#/" className="text-xs text-zinc-500 hover:text-zinc-300">← Semua project</a>
            <h1 className="mt-1 text-xl font-bold leading-tight">{project.name}</h1>
            <p className="text-sm text-zinc-500">{video.channel} · {fmtTime(duration)}</p>
          </div>
          <a href={video.url} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-zinc-500 hover:text-rose-400">
            Buka di YouTube ↗
          </a>
        </div>

        {!ready ? (
          <div className="flex aspect-video flex-col items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900 p-8 text-center">
            <img src={video.thumbnail} alt="" className="mb-4 max-h-40 rounded-lg opacity-60" />
            {project.status === 'error' || downloadJob?.status === 'error' ? (
              <>
                <p className="text-red-400">Download gagal</p>
                <p className="mt-1 max-w-lg break-words text-xs text-zinc-500">{downloadJob?.error}</p>
                <button onClick={() => api.retryDownload(projectId)} className="mt-4 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold hover:bg-rose-500">
                  Coba lagi
                </button>
              </>
            ) : (
              <>
                <p className="text-zinc-300">{downloadJob?.message || 'Menyiapkan download…'}</p>
                <div className="mt-3 h-2 w-72 overflow-hidden rounded bg-zinc-800">
                  <div className="h-full bg-rose-500 transition-all" style={{ width: `${(downloadJob?.progress ?? 0) * 100}%` }} />
                </div>
              </>
            )}
          </div>
        ) : (
          <>
            <div className="relative overflow-hidden rounded-xl bg-black">
              <video
                ref={videoRef}
                src={video.media_url!}
                className="aspect-video w-full"
                onClick={togglePlay}
                onLoadedMetadata={(e) => setVideoRatio(e.currentTarget.videoWidth / e.currentTarget.videoHeight || 16 / 9)}
                onTimeUpdate={(e) => {
                  const t = e.currentTarget.currentTime
                  setCurrent(t)
                  if (stopAt.current !== null && t >= stopAt.current) {
                    e.currentTarget.pause()
                    stopAt.current = null
                  }
                }}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
              />
              {showCrop && (
                <div className="pointer-events-none absolute inset-0">
                  <div className="absolute inset-y-0 left-0 bg-black/60" style={{ width: `${(1 - cropW) * selected.crop_x * 100}%` }} />
                  <div
                    className="absolute inset-y-0 border-2 border-amber-400"
                    style={{ left: `${(1 - cropW) * selected.crop_x * 100}%`, width: `${cropW * 100}%` }}
                  />
                  <div className="absolute inset-y-0 right-0 bg-black/60" style={{ width: `${(1 - cropW) * (1 - selected.crop_x) * 100}%` }} />
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-sm">
              <button onClick={() => seek(current - 5)} className="rounded-md bg-zinc-800 px-2.5 py-1.5 hover:bg-zinc-700">−5s</button>
              <button onClick={togglePlay} className="w-20 rounded-md bg-zinc-100 px-3 py-1.5 font-semibold text-zinc-900 hover:bg-white">
                {playing ? '❚❚ Pause' : '▶ Play'}
              </button>
              <button onClick={() => seek(current + 5)} className="rounded-md bg-zinc-800 px-2.5 py-1.5 hover:bg-zinc-700">+5s</button>
              <span className="ml-1 font-mono text-zinc-300">
                {fmtTime(current, true)} / {fmtTime(duration)}
              </span>

              <div className="ml-auto flex items-center gap-2">
                <button onClick={() => setMarkIn(current)} className="rounded-md border border-emerald-500/50 px-2.5 py-1.5 text-emerald-300 hover:bg-emerald-500/10">
                  IN {markIn !== null ? fmtTime(markIn, true) : '(I)'}
                </button>
                <button onClick={() => setMarkOut(current)} className="rounded-md border border-orange-500/50 px-2.5 py-1.5 text-orange-300 hover:bg-orange-500/10">
                  OUT {markOut !== null ? fmtTime(markOut, true) : '(O)'}
                </button>
                <button onClick={addClip} className="rounded-md bg-rose-600 px-3 py-1.5 font-semibold hover:bg-rose-500">
                  + Tambah klip
                </button>
              </div>
            </div>

            <Timeline
              duration={duration}
              current={current}
              heatmap={video.heatmap}
              chapters={video.chapters}
              clips={clips}
              selectedId={selectedId}
              markIn={markIn}
              markOut={markOut}
              onSeek={seek}
              onSelectClip={(id) => {
                setSelectedId(id)
                const c = clips.find((x) => x.id === id)
                if (c) seek(c.start)
              }}
            />

            {error && <p className="text-sm text-red-400">{error}</p>}

            <p className="text-xs text-zinc-500">
              Shortcut: <kbd>Space</kbd> play/pause · <kbd>I</kbd>/<kbd>O</kbd> set IN/OUT · <kbd>Enter</kbd> tambah klip ·{' '}
              <kbd>←/→</kbd> 1s (Shift = 5s) · <kbd>,</kbd>/<kbd>.</kbd> per frame · <kbd>Esc</kbd> reset IN/OUT
              {video.heatmap && <> · <span className="text-rose-400">area merah</span> = Most Replayed</>}
            </p>

            <TranscriptPanel
              project={project}
              job={transcribeJob}
              current={current}
              onSeek={seek}
              onCreateClip={(s, e, t) => createClip(s, e, t)}
            />

            <HighlightPanel
              project={project}
              job={highlightJob}
              onComplete={load}
            />
          </>
        )}
      </div>

      <aside className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Klip ({clips.length})</h2>
          {clips.length > 0 && (
            <button onClick={() => api.renderAll(projectId)} className="rounded-md bg-zinc-800 px-3 py-1.5 text-sm hover:bg-zinc-700">
              Render semua
            </button>
          )}
        </div>
        {clips.length === 0 && (
          <p className="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">
            Belum ada klip. Putar video, tekan <kbd>I</kbd> di awal momen dan <kbd>O</kbd> di akhir, lalu <kbd>Enter</kbd>.
            Atau pilih baris di transkrip.
          </p>
        )}
        <div className="max-h-[calc(100vh-180px)] space-y-2 overflow-y-auto pr-1">
          {clips.map((c) => (
            <ClipCard
              key={c.id}
              clip={c}
              job={clipJobs[c.id]}
              selected={c.id === selectedId}
              current={current}
              hasTranscript={!!project.transcript}
              captionPresets={presets}
              onSelect={() => {
                if (selectedId !== c.id) {
                  setSelectedId(c.id)
                  seek(c.start)
                }
              }}
              onPreview={() => previewClip(c)}
              onChange={(p) => updateClip(c.id, p)}
              onDelete={() => deleteClip(c.id)}
            />
          ))}
        </div>
      </aside>
    </div>
  )
}

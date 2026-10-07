import { useCallback, useRef } from 'react'
import { fmtTime, type Clip, type HeatPoint } from '../api'

type Props = {
  duration: number
  current: number
  heatmap: HeatPoint[] | null
  chapters: { start_time: number; title: string }[] | null
  clips: Clip[]
  selectedId: number | null
  markIn: number | null
  markOut: number | null
  onSeek: (t: number) => void
  onSelectClip: (id: number) => void
}

/** Full-length timeline: Most-Replayed heatmap, chapters, clip regions, IN/OUT selection, playhead. */
export default function Timeline({
  duration, current, heatmap, chapters, clips, selectedId, markIn, markOut, onSeek, onSelectClip,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const pct = (t: number) => `${(Math.min(Math.max(t, 0), duration) / (duration || 1)) * 100}%`

  const seekFromEvent = useCallback(
    (clientX: number) => {
      const el = ref.current
      if (!el || !duration) return
      const r = el.getBoundingClientRect()
      onSeek(Math.min(Math.max((clientX - r.left) / r.width, 0), 1) * duration)
    },
    [duration, onSeek],
  )

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).dataset.clip) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    seekFromEvent(e.clientX)
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (e.buttons === 1 && !(e.target as HTMLElement).dataset.clip) seekFromEvent(e.clientX)
  }

  // SVG path for heatmap area (viewBox 0..1000 x 0..100)
  const heatPath =
    heatmap && heatmap.length && duration
      ? 'M0,100 ' +
        heatmap
          .map((h) => `L${((h.start_time + h.end_time) / 2 / duration) * 1000},${100 - h.value * 95}`)
          .join(' ') +
        ' L1000,100 Z'
      : null

  const ticks = Array.from({ length: 11 }, (_, i) => (duration * i) / 10)
  const selStart = markIn ?? null
  const selEnd = markOut ?? null

  return (
    <div className="select-none">
      <div
        ref={ref}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        className="relative h-24 cursor-pointer overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900"
      >
        {heatPath && (
          <svg viewBox="0 0 1000 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-x-0 top-0 h-14 w-full">
            <path d={heatPath} className="fill-rose-500/25 stroke-rose-400/60" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          </svg>
        )}

        {chapters?.map((c, i) => (
          <div key={i} className="pointer-events-none absolute top-0 h-full border-l border-dashed border-zinc-600/60" style={{ left: pct(c.start_time) }}>
            <span className="ml-1 whitespace-nowrap text-[10px] text-zinc-500">{c.title}</span>
          </div>
        ))}

        {/* clip regions */}
        {clips.map((c) => (
          <div
            key={c.id}
            data-clip="1"
            title={`${c.title} (${fmtTime(c.start)}–${fmtTime(c.end)})`}
            onClick={() => onSelectClip(c.id)}
            className={`absolute bottom-1 h-7 rounded border text-[10px] leading-7 ${
              c.id === selectedId ? 'border-amber-300 bg-amber-400/40 text-amber-100' : 'border-sky-400/60 bg-sky-500/25 text-sky-100'
            } overflow-hidden px-1`}
            style={{ left: pct(c.start), width: `calc(${pct(c.end)} - ${pct(c.start)})` }}
          >
            <span data-clip="1">{c.title}</span>
          </div>
        ))}

        {/* IN/OUT selection */}
        {selStart !== null && (
          <div className="pointer-events-none absolute top-0 h-full w-0.5 bg-emerald-400" style={{ left: pct(selStart) }} />
        )}
        {selEnd !== null && (
          <div className="pointer-events-none absolute top-0 h-full w-0.5 bg-orange-400" style={{ left: pct(selEnd) }} />
        )}
        {selStart !== null && selEnd !== null && selEnd > selStart && (
          <div
            className="pointer-events-none absolute top-0 h-full bg-emerald-400/10"
            style={{ left: pct(selStart), width: `calc(${pct(selEnd)} - ${pct(selStart)})` }}
          />
        )}

        {/* playhead */}
        <div className="pointer-events-none absolute top-0 h-full w-0.5 bg-white shadow-[0_0_6px_white]" style={{ left: pct(current) }} />
      </div>

      <div className="relative mt-1 h-4 text-[10px] text-zinc-500">
        {ticks.map((t, i) => (
          <span key={i} className="absolute -translate-x-1/2" style={{ left: pct(t) }}>
            {fmtTime(t)}
          </span>
        ))}
      </div>
    </div>
  )
}

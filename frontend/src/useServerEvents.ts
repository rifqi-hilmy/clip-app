import { useEffect, useRef } from 'react'
import type { Job } from './api'

export type ServerEvent = { type: 'job'; job: Job } | { type: 'project'; project_id: number }

/** Subscribes to backend WebSocket events, reconnecting automatically. */
export function useServerEvents(onEvent: (e: ServerEvent) => void) {
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let retry: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/ws`)
      ws.onmessage = (m) => {
        try {
          handler.current(JSON.parse(m.data))
        } catch {
          /* ignore malformed */
        }
      }
      ws.onclose = () => {
        if (!closed) retry = window.setTimeout(connect, 1500)
      }
    }
    connect()
    const ping = window.setInterval(() => ws?.readyState === 1 && ws.send('ping'), 20000)

    return () => {
      closed = true
      window.clearTimeout(retry)
      window.clearInterval(ping)
      ws?.close()
    }
  }, [])
}

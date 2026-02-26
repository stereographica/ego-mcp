import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchCurrent } from '@/api'
import type { CurrentResponse } from '@/types'

export type LogLine = {
  ts: string
  tool_name?: string
  ok: boolean
  level?: string
  logger?: string
  message?: string
}

type DashboardSocketState = {
  current: CurrentResponse | null
  logLines: LogLine[]
  connected: boolean
}

const WS_URL =
  (import.meta.env.VITE_DASHBOARD_WS_BASE ?? 'ws://localhost:8000') +
  '/ws/current'

const RECONNECT_INTERVAL = 3_000
const POLL_INTERVAL = 2_000
const MAX_LOG_LINES = 50

export const useDashboardSocket = (): DashboardSocketState => {
  const [current, setCurrent] = useState<CurrentResponse | null>(null)
  const [logLines, setLogLines] = useState<LogLine[]>([])
  const [connected, setConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const disposedRef = useRef(false)

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return
    const poll = async () => {
      if (disposedRef.current) return
      const data = await fetchCurrent()
      if (!disposedRef.current) setCurrent(data)
    }
    void poll()
    pollTimerRef.current = setInterval(poll, POLL_INTERVAL)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (disposedRef.current || wsRef.current) return

    try {
      const socket = new WebSocket(WS_URL)
      wsRef.current = socket

      socket.onopen = () => {
        if (disposedRef.current) {
          socket.close()
          return
        }
        setConnected(true)
        stopPolling()
      }

      socket.onmessage = (evt) => {
        if (disposedRef.current) return
        const msg = JSON.parse(evt.data) as {
          type: string
          data?: Record<string, unknown>
        }

        if (msg.type === 'current_snapshot' && msg.data) {
          setCurrent(msg.data as unknown as CurrentResponse)
        } else if (msg.type === 'log_line' && msg.data) {
          setLogLines((prev) => {
            const fields =
              typeof msg.data?.fields === 'object' && msg.data.fields !== null
                ? (msg.data.fields as Record<string, unknown>)
                : {}
            const level =
              typeof msg.data?.level === 'string' ? msg.data.level : undefined
            const message =
              typeof msg.data?.message === 'string'
                ? msg.data.message
                : undefined
            const toolName =
              typeof msg.data?.tool_name === 'string'
                ? msg.data.tool_name
                : typeof fields.tool_name === 'string'
                  ? fields.tool_name
                  : undefined
            const line: LogLine = {
              ts: (msg.data?.ts as string) ?? new Date().toISOString(),
              tool_name: toolName,
              ok:
                typeof msg.data?.ok === 'boolean'
                  ? msg.data.ok
                  : !(level === 'ERROR' || message === 'Tool execution failed'),
              level,
              logger:
                typeof msg.data?.logger === 'string'
                  ? msg.data.logger
                  : undefined,
              message,
            }
            const last = prev[prev.length - 1]
            if (
              last &&
              last.ts === line.ts &&
              last.logger === line.logger &&
              last.message === line.message &&
              last.tool_name === line.tool_name
            ) {
              return prev
            }
            const next = [...prev, line]
            return next.length > MAX_LOG_LINES
              ? next.slice(-MAX_LOG_LINES)
              : next
          })
        }
      }

      socket.onclose = () => {
        wsRef.current = null
        setConnected(false)
        if (!disposedRef.current) {
          startPolling()
          reconnectTimerRef.current = setTimeout(connect, RECONNECT_INTERVAL)
        }
      }

      socket.onerror = () => {
        socket.close()
      }
    } catch {
      wsRef.current = null
      if (!disposedRef.current) {
        startPolling()
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_INTERVAL)
      }
    }
  }, [startPolling, stopPolling])

  useEffect(() => {
    disposedRef.current = false

    // Initial HTTP fetch for immediate data
    void fetchCurrent().then((data) => {
      if (!disposedRef.current) setCurrent(data)
    })

    // Try WS first
    connect()

    return () => {
      disposedRef.current = true
      stopPolling()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect, stopPolling])

  return { current, logLines, connected }
}

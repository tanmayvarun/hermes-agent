import { atom, computed } from 'nanostores'

import { formatDuration } from '@/lib/statusbar'
import {
  type PromptTaskStatus,
  isTerminalTaskStatus,
  normalizeTaskStatus,
  resolveErrorMessage,
  taskPhaseLabel,
  taskStatusLabel
} from '@/lib/task-status-vocab'

export type { PromptTaskStatus }

export interface PromptTask {
  durationMs?: number | null
  endedAt?: number | null
  error?: string
  errorCode?: string
  /** Resolved user-facing message (override or catalog default). */
  message?: string
  phase: string
  promptExcerpt?: string
  sessionId: string
  startedAt: number
  status: PromptTaskStatus
  summary?: string
  taskRequestId: string
  /** Assistant message id once the turn settles (for thread footer). */
  messageId?: string
  updatedAt: number
}

const HISTORY_LIMIT = 40

/** Active + recent prompt tasks by runtime session id. */
export const $promptTasksBySession = atom<Record<string, PromptTask[]>>({})

/** Active running/waiting task for the focused session (statusbar phase). */
export const $activePromptPhase = atom<string | null>(null)

export function promptTaskPhaseLabel(phase: string | null | undefined): string {
  return taskPhaseLabel(phase)
}

export function promptTaskStatusLabel(status: PromptTaskStatus): string {
  return taskStatusLabel(status)
}

export function formatPromptTaskDuration(durationMs: number | null | undefined): string {
  if (durationMs == null || !Number.isFinite(durationMs) || durationMs < 0) {
    return ''
  }
  return formatDuration(durationMs)
}

function upsertList(list: PromptTask[], task: PromptTask): PromptTask[] {
  const idx = list.findIndex(t => t.taskRequestId === task.taskRequestId)
  if (idx >= 0) {
    const next = list.slice()
    next[idx] = { ...list[idx], ...task, updatedAt: Date.now() }
    return next
  }
  return [...list, task].slice(-HISTORY_LIMIT)
}

export function upsertPromptTaskFromEvent(
  sessionId: string,
  payload: Record<string, unknown>
): PromptTask | null {
  const taskRequestId = String(payload.task_request_id || '').trim()
  if (!sessionId || !taskRequestId) {
    return null
  }
  const statusRaw = String(payload.status || 'running').trim().toLowerCase()
  const status = normalizeTaskStatus(statusRaw)
  const startedAt =
    typeof payload.started_at === 'number' && Number.isFinite(payload.started_at)
      ? payload.started_at * (payload.started_at < 1e12 ? 1000 : 1)
      : Date.now()
  const durationMs =
    typeof payload.duration_ms === 'number' && Number.isFinite(payload.duration_ms)
      ? Math.max(0, Math.round(payload.duration_ms))
      : null
  const errorCode =
    typeof payload.error_code === 'string' ? payload.error_code.trim() : ''
  const resolvedMessage =
    typeof payload.message === 'string' && payload.message.trim()
      ? payload.message.trim()
      : errorCode
        ? resolveErrorMessage(
            errorCode,
            typeof payload.summary === 'string' ? payload.summary : ''
          )
        : ''
  const task: PromptTask = {
    durationMs,
    endedAt:
      typeof payload.ended_at === 'number' && Number.isFinite(payload.ended_at)
        ? payload.ended_at * (payload.ended_at < 1e12 ? 1000 : 1)
        : null,
    error: typeof payload.error === 'string' ? payload.error : '',
    errorCode,
    message: resolvedMessage,
    phase: String(payload.phase || ''),
    promptExcerpt: typeof payload.prompt_excerpt === 'string' ? payload.prompt_excerpt : '',
    sessionId,
    startedAt,
    status,
    summary: typeof payload.summary === 'string' ? payload.summary : '',
    taskRequestId,
    updatedAt: Date.now()
  }

  const all = { ...$promptTasksBySession.get() }
  all[sessionId] = upsertList(all[sessionId] ?? [], task)
  $promptTasksBySession.set(all)

  if (status === 'running' || status === 'waiting_for_user') {
    $activePromptPhase.set(taskPhaseLabel(task.phase) || null)
  } else {
    const active = (all[sessionId] ?? []).find(
      t => t.status === 'running' || t.status === 'waiting_for_user'
    )
    $activePromptPhase.set(active ? taskPhaseLabel(active.phase) || null : null)
  }
  return task
}

export function finalizePromptTaskFromComplete(
  sessionId: string,
  payload: Record<string, unknown>,
  options?: { messageId?: string; turnStartedAt?: number | null }
): PromptTask | null {
  const messageId = options?.messageId
  const turnStartedAt = options?.turnStartedAt
  const taskRequestId = String(payload.task_request_id || '').trim()
  const finalStatusRaw = String(payload.final_status || payload.status || 'completed')
    .trim()
    .toLowerCase()
  let status = normalizeTaskStatus(finalStatusRaw)
  if (status === 'running') {
    status = payload.waiting_for_user ? 'waiting_for_user' : 'completed'
  }
  if (!isTerminalTaskStatus(status)) {
    status = 'completed'
  }

  let durationMs =
    typeof payload.duration_ms === 'number' && Number.isFinite(payload.duration_ms)
      ? Math.max(0, Math.round(payload.duration_ms))
      : null
  if (durationMs == null && turnStartedAt) {
    durationMs = Math.max(0, Date.now() - turnStartedAt)
  }

  const existing: PromptTask | undefined = taskRequestId
    ? ($promptTasksBySession.get()[sessionId] ?? []).find(t => t.taskRequestId === taskRequestId)
    : undefined

  const errorCode =
    typeof payload.error_code === 'string' && payload.error_code.trim()
      ? payload.error_code.trim()
      : existing?.errorCode || ''
  const summary =
    typeof payload.summary === 'string' ? payload.summary : existing?.summary || ''
  const message =
    typeof payload.message === 'string' && payload.message.trim()
      ? payload.message.trim()
      : errorCode
        ? resolveErrorMessage(errorCode, summary)
        : existing?.message || ''

  const task: PromptTask = {
    durationMs,
    endedAt: Date.now(),
    error: typeof payload.error === 'string' ? payload.error : existing?.error || '',
    errorCode,
    message,
    messageId,
    phase: String(payload.phase || existing?.phase || 'finishing'),
    promptExcerpt: existing?.promptExcerpt || '',
    sessionId,
    startedAt: existing?.startedAt || turnStartedAt || Date.now(),
    status,
    summary,
    taskRequestId: taskRequestId || existing?.taskRequestId || `local-${Date.now().toString(36)}`,
    updatedAt: Date.now()
  }

  const all = { ...$promptTasksBySession.get() }
  all[sessionId] = upsertList(all[sessionId] ?? [], task)
  $promptTasksBySession.set(all)
  $activePromptPhase.set(null)
  return task
}

export const $activePromptTaskForComposer = computed($promptTasksBySession, bySession => {
  // Consumers pick by session id; this atom is a bump trigger.
  return bySession
})

export function activePromptComposerItem(sessionId: string | null): {
  id: string
  state: 'done' | 'failed' | 'running'
  title: string
  type: 'prompt'
} | null {
  if (!sessionId) return null
  const tasks = $promptTasksBySession.get()[sessionId] ?? []
  const active = [...tasks]
    .reverse()
    .find(t => t.status === 'running' || t.status === 'waiting_for_user')
  if (!active) return null
  const label =
    active.status === 'waiting_for_user'
      ? 'Needs your input'
      : promptTaskPhaseLabel(active.phase) || 'Working'
  return {
    id: `prompt:${active.taskRequestId}`,
    state: active.status === 'waiting_for_user' ? 'running' : 'running',
    title: label,
    type: 'prompt'
  }
}

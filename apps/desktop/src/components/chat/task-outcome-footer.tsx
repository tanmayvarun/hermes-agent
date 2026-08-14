import { useAuiState } from '@assistant-ui/react'
import type { FC } from 'react'

import {
  formatPromptTaskDuration,
  promptTaskStatusLabel,
  type PromptTaskStatus
} from '@/store/prompt-tasks'
import { resolveErrorMessage } from '@/lib/task-status-vocab'
import { cn } from '@/lib/utils'

function isPromptTaskStatus(value: string): value is PromptTaskStatus {
  return (
    value === 'completed' ||
    value === 'failed' ||
    value === 'interrupted' ||
    value === 'running' ||
    value === 'waiting_for_user'
  )
}

function taskOutcomeBag(s: {
  message: { metadata?: { custom?: unknown } }
}): Record<string, unknown> | null {
  const custom = s.message.metadata?.custom as Record<string, unknown> | undefined
  const raw = custom?.taskOutcome
  if (!raw || typeof raw !== 'object') {
    return null
  }
  return raw as Record<string, unknown>
}

/** Frozen final status + duration under a settled assistant turn. */
export const TaskOutcomeFooter: FC = () => {
  // useAuiState compares with Object.is — selectors MUST return primitives /
  // stable refs. Returning a fresh `{...}` object each call causes React #185
  // (maximum update depth) on every settled assistant message.
  const finalStatus = useAuiState(s => {
    const rec = taskOutcomeBag(s)
    return typeof rec?.finalStatus === 'string' ? rec.finalStatus : ''
  })
  const durationMs = useAuiState(s => {
    const rec = taskOutcomeBag(s)
    return typeof rec?.durationMs === 'number' ? rec.durationMs : null
  })
  const errorCode = useAuiState(s => {
    const rec = taskOutcomeBag(s)
    return typeof rec?.errorCode === 'string' ? rec.errorCode : ''
  })
  const message = useAuiState(s => {
    const rec = taskOutcomeBag(s)
    return typeof rec?.message === 'string' ? rec.message : ''
  })
  const summary = useAuiState(s => {
    const rec = taskOutcomeBag(s)
    return typeof rec?.summary === 'string' ? rec.summary : ''
  })

  if (!finalStatus) {
    return null
  }

  const status = isPromptTaskStatus(finalStatus) ? finalStatus : 'completed'
  const label = promptTaskStatusLabel(status)
  const duration = formatPromptTaskDuration(durationMs)
  const detail =
    status === 'failed' || status === 'waiting_for_user' || status === 'interrupted'
      ? message || (errorCode ? resolveErrorMessage(errorCode, summary) : '')
      : ''
  const tone =
    status === 'failed'
      ? 'text-[color-mix(in_srgb,var(--dt-destructive)_78%,var(--ui-text-secondary))]'
      : status === 'waiting_for_user'
        ? 'text-[color-mix(in_srgb,var(--dt-warning,orange)_80%,var(--ui-text-secondary))]'
        : 'text-[color-mix(in_srgb,var(--dt-foreground)_55%,var(--ui-text-secondary))]'

  return (
    <div
      className={cn('mt-1.5 text-[0.72rem] leading-5', tone)}
      data-slot="task-outcome-footer"
      {...(errorCode ? { 'data-error-code': errorCode } : {})}
    >
      <span className="font-medium">{label}</span>
      {duration ? <span> · {duration}</span> : null}
      {detail ? <span className="block opacity-90">{detail}</span> : null}
    </div>
  )
}

/**
 * Canonical task status / phase vocabulary — must match
 * plugin/agent/runtime/schemas/task_status_vocab.json (Python task_facts.py).
 */
export const TASK_STATUSES = [
  'running',
  'waiting_for_user',
  'completed',
  'failed',
  'interrupted'
] as const

export type PromptTaskStatus = (typeof TASK_STATUSES)[number]

export const TERMINAL_TASK_STATUSES = [
  'waiting_for_user',
  'completed',
  'failed',
  'interrupted'
] as const

export const TASK_PHASES = [
  'interpreting',
  'selecting_method',
  'executing',
  'computer_use',
  'awaiting_user',
  'finishing'
] as const

export const HERMES_ERROR_CODES = [
  'setup_blocked',
  'auth_required',
  'provider_unavailable',
  'timeout',
  'interrupted',
  'execution_failed',
  'unknown'
] as const

export type HermesErrorCode = (typeof HERMES_ERROR_CODES)[number]

/** Defaults must match plugin/agent/runtime/error_codes.py */
export const ERROR_CODE_MESSAGES: Record<HermesErrorCode, string> = {
  setup_blocked: "Finish app setup on this device, then reply when you're ready.",
  auth_required: 'Link or sign in so I can continue with the preferred method.',
  provider_unavailable:
    "That service isn't available right now. Trying another approach if possible.",
  timeout: 'This step took too long and was stopped.',
  interrupted: 'Stopped before finishing.',
  execution_failed: 'Something went wrong while carrying out that step.',
  unknown: 'Something went wrong.'
}

const STATUS_LABELS: Record<PromptTaskStatus, string> = {
  waiting_for_user: 'Needs your input',
  failed: 'Failed',
  interrupted: 'Interrupted',
  completed: 'Completed',
  running: 'Running'
}

const PHASE_LABELS: Record<string, string> = {
  computer_use: 'computer use',
  selecting_method: 'selecting method',
  awaiting_user: 'needs input',
  interpreting: 'interpreting',
  executing: 'executing',
  finishing: 'finishing'
}

export function normalizeTaskStatus(raw: unknown): PromptTaskStatus {
  const s = String(raw || '')
    .trim()
    .toLowerCase()
  return (TASK_STATUSES as readonly string[]).includes(s)
    ? (s as PromptTaskStatus)
    : 'running'
}

export function isTerminalTaskStatus(status: string): boolean {
  return (TERMINAL_TASK_STATUSES as readonly string[]).includes(status)
}

export function taskStatusLabel(status: PromptTaskStatus): string {
  return STATUS_LABELS[status] ?? 'Running'
}

export function taskPhaseLabel(phase: string | null | undefined): string {
  const p = String(phase || '')
    .trim()
    .toLowerCase()
  if (!p) return ''
  if (PHASE_LABELS[p]) return PHASE_LABELS[p]
  return p.replace(/_/g, ' ')
}

/** ChargePe-style: non-blank override wins; else catalog default. */
export function resolveErrorMessage(
  code: string | null | undefined,
  override?: string | null
): string {
  const custom = String(override || '').trim()
  if (custom) return custom
  const key = String(code || '')
    .trim()
    .toLowerCase()
  if ((HERMES_ERROR_CODES as readonly string[]).includes(key)) {
    return ERROR_CODE_MESSAGES[key as HermesErrorCode]
  }
  return ERROR_CODE_MESSAGES.unknown
}

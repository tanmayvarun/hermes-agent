import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  ERROR_CODE_MESSAGES,
  HERMES_ERROR_CODES,
  TASK_PHASES,
  TASK_STATUSES,
  TERMINAL_TASK_STATUSES,
  resolveErrorMessage
} from './task-status-vocab'

const here = dirname(fileURLToPath(import.meta.url))
const schemaPath = join(
  here,
  '../../../../plugin/agent/runtime/schemas/task_status_vocab.json'
)

describe('task-status-vocab contract', () => {
  it('matches Python task_facts schema JSON', () => {
    const schema = JSON.parse(readFileSync(schemaPath, 'utf8')) as {
      task_statuses: string[]
      terminal_task_statuses: string[]
      task_phases: string[]
      error_codes: string[]
      error_code_messages: Record<string, string>
    }
    expect([...TASK_STATUSES]).toEqual(schema.task_statuses)
    expect([...TERMINAL_TASK_STATUSES].sort()).toEqual(schema.terminal_task_statuses)
    expect([...TASK_PHASES]).toEqual(schema.task_phases)
    expect([...HERMES_ERROR_CODES]).toEqual(schema.error_codes)
    expect(ERROR_CODE_MESSAGES).toEqual(schema.error_code_messages)
  })

  it('resolveErrorMessage prefers override then catalog default', () => {
    expect(resolveErrorMessage('setup_blocked')).toBe(ERROR_CODE_MESSAGES.setup_blocked)
    expect(resolveErrorMessage('setup_blocked', 'Custom ASK body')).toBe('Custom ASK body')
    expect(resolveErrorMessage('nope')).toBe(ERROR_CODE_MESSAGES.unknown)
  })
})

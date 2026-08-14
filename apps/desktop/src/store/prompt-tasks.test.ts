import { beforeEach, describe, expect, it } from 'vitest'

import {
  $activePromptPhase,
  $promptTasksBySession,
  finalizePromptTaskFromComplete,
  formatPromptTaskDuration,
  promptTaskStatusLabel,
  upsertPromptTaskFromEvent
} from './prompt-tasks'

describe('prompt-tasks store', () => {
  beforeEach(() => {
    $promptTasksBySession.set({})
    $activePromptPhase.set(null)
  })

  it('upsert + finalize preserves duration and clears active phase', () => {
    upsertPromptTaskFromEvent('sess-a', {
      task_request_id: 'tid1',
      status: 'running',
      phase: 'computer_use',
      started_at: Date.now() / 1000
    })
    expect($activePromptPhase.get()).toBe('computer use')

    const done = finalizePromptTaskFromComplete(
      'sess-a',
      {
        task_request_id: 'tid1',
        final_status: 'completed',
        duration_ms: 12500,
        phase: 'finishing'
      },
      { messageId: 'asst-1' }
    )
    expect(done?.status).toBe('completed')
    expect(done?.durationMs).toBe(12500)
    expect(done?.messageId).toBe('asst-1')
    expect($activePromptPhase.get()).toBeNull()
    expect(promptTaskStatusLabel('waiting_for_user')).toBe('Needs your input')
    expect(formatPromptTaskDuration(12500)).toBe('0:12')
  })
})

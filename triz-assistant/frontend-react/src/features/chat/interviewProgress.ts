/** Парсинг прогресса интервью из служебного сообщения __interview_state__ */

import type { ChatMessage } from '../../types/triz'

const STATE_PREFIX = '__interview_state__:'

const BLOCKS: { block: string; fields: string[] }[] = [
  { block: '1 — НЭ', fields: ['ne_fact', 'ne_where', 'ne_when', 'consequences', 'cause_hypothesis'] },
  { block: '2 — Система', fields: ['system_function', 'system_elements', 'system_object', 'supersystem'] },
  { block: '3 — Результаты', fields: ['expected_result', 'economic_result'] },
  { block: '4 — Ограничения/ресурсы', fields: ['constraints', 'resources'] },
  { block: '5 — Известные решения', fields: ['known_solutions', 'why_failed', 'unrealized_ideas'] },
  { block: '6 — Эксперты', fields: ['experts'] },
]

export interface InterviewBlockStatus {
  block: string
  closed: boolean
  missing_fields: string[]
}

interface InterviewState {
  confirmed?: Record<string, string>
}

function parseState(messages: ChatMessage[]): InterviewState | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (msg.role === 'system' && msg.content.startsWith(STATE_PREFIX)) {
      try {
        return JSON.parse(msg.content.slice(STATE_PREFIX.length)) as InterviewState
      } catch {
        return null
      }
    }
  }
  return null
}

export function getInterviewBlockStatus(messages: ChatMessage[]): InterviewBlockStatus[] | null {
  const state = parseState(messages)
  if (!state) return null

  const confirmed = state.confirmed ?? {}
  return BLOCKS.map(({ block, fields }) => {
    const missing = fields.filter((f) => !(f in confirmed))
    return {
      block,
      closed: missing.length === 0,
      missing_fields: missing,
    }
  })
}

export const INTERVIEW_BLOCK_NAMES = BLOCKS.map((b) => b.block)

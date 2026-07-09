/** Извлечение видимой части assistant-сообщений интервью (без служебных блоков). */

const CONTEXT_PREFIX = '[КОНТЕКСТ:'
const STATUS_HEADER = '[СТАТУС БЛОКОВ]'
const NEXT_QUESTION_PREFIX = 'Следующий вопрос:'
const INSTRUCTION_PREFIX = '[ИНСТРУКЦИЯ:'

function isEphemeralLine(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed) return true
  if (trimmed.startsWith(CONTEXT_PREFIX)) return true
  if (trimmed === STATUS_HEADER || trimmed.startsWith(STATUS_HEADER)) return true
  if (trimmed.startsWith('•')) return true
  if (trimmed.startsWith(INSTRUCTION_PREFIX)) return true
  return false
}

/**
 * Возвращает текст для отображения пользователю.
 * Сообщения с префиксом [КОНТЕКСТ:...] — только содержательная часть (вопрос).
 * Обычные сообщения — без изменений.
 */
export function extractVisibleAssistantContent(content: string): string {
  const trimmed = (content ?? '').trim()
  if (!trimmed.startsWith(CONTEXT_PREFIX)) {
    return trimmed
  }

  const lines = trimmed.split('\n')

  const nextQuestionIdx = lines.findIndex((line) => line.trim().startsWith(NEXT_QUESTION_PREFIX))
  if (nextQuestionIdx >= 0) {
    return lines.slice(nextQuestionIdx).join('\n').trim()
  }

  return lines.filter((line) => !isEphemeralLine(line)).join('\n').trim()
}

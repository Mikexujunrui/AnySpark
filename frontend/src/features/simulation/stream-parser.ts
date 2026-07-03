// SSE 叙事流解析器
// 参照 Nova 的 stream-parser.ts
// 处理流式叙事中的标签分割、缓冲区累积

const NARRATIVE_START = '<NARRATIVE>'
const NARRATIVE_END = '</NARRATIVE>'
const VISIBLE_TAGS = [NARRATIVE_START, NARRATIVE_END]
const TAG_PREFIXES = VISIBLE_TAGS.map(t => t.toLowerCase())

export function createNarrativeFilter() {
  let buffer = ''
  let stopped = false

  return {
    /** Push incoming chunk, return extracted narrative text. */
    push(chunk: string): string {
      if (!chunk || stopped) return ''
      buffer += chunk
      return drain(false)
    },

    /** Flush remaining buffer, return final narrative text. */
    flush(): string {
      if (stopped) return ''
      return drain(true)
    },

    isStopped(): boolean {
      return stopped
    },
  }

  function drain(flushAll: boolean): string {
    let output = ''
    while (buffer) {
      // Check for content before any tag
      const nextTag = findNextTag(buffer)
      if (nextTag > 0) {
        output += buffer.slice(0, nextTag)
        buffer = buffer.slice(nextTag)
        continue
      }
      if (nextTag === 0) {
        // At a tag boundary, skip known tags
        if (buffer.startsWith(NARRATIVE_START)) {
          buffer = buffer.slice(NARRATIVE_START.length)
          continue
        }
        if (buffer.startsWith(NARRATIVE_END)) {
          buffer = buffer.slice(NARRATIVE_END.length)
          buffer = buffer.trimStart()
          continue
        }
        // Unknown tag or partial — treat as content
        output += buffer[0]
        buffer = buffer.slice(1)
        continue
      }

      // No tag found in buffer
      const keep = flushAll ? 0 : partialTagSuffixLength(buffer)
      output += buffer.slice(0, buffer.length - keep)
      buffer = buffer.slice(buffer.length - keep)
      return output
    }
    return output
  }
}

function findNextTag(value: string): number {
  let next = -1
  for (const tag of VISIBLE_TAGS) {
    const index = value.indexOf(tag)
    if (index >= 0 && (next < 0 || index < next)) next = index
  }
  return next
}

function partialTagSuffixLength(value: string): number {
  const lower = value.toLowerCase()
  const max = Math.min(value.length, Math.max(...TAG_PREFIXES.map(t => t.length)) - 1)
  for (let len = max; len > 0; len--) {
    const suffix = lower.slice(lower.length - len)
    if (TAG_PREFIXES.some(t => t.startsWith(suffix))) return len
  }
  return 0
}

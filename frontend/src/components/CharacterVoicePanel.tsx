import { useState, useEffect } from 'react'
import Icon from './ui/Icon'

interface VoiceFingerprint {
  character_id: string
  character_name: string
  dialogue_count: number
  total_dialogue_chars: number
  top_words: { word: string; count: number }[]
  avg_sentence_length: number
  sentence_pattern_ratio: Record<string, number>
  catchphrases: string[]
  emotional_tendency: string
}

const TENDENCY_LABELS: Record<string, string> = {
  passionate: '热情奔放',
  cold: '冷淡简洁',
  irritable: '急躁易怒',
  gloomy: '阴沉压抑',
  neutral: '平稳中性',
}

export default function CharacterVoicePanel({ bookId, characterName }: { bookId: string; characterName: string }) {
  const [voice, setVoice] = useState<VoiceFingerprint | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (expanded && !voice) loadData()
  }, [expanded])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/characters/${encodeURIComponent(characterName)}/voice`)
      if (res.ok) setVoice(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  if (!expanded) {
    return (
      <div className="mb-6">
        <button
          onClick={() => setExpanded(true)}
          className="w-full flex items-center justify-between p-3 bg-zinc-800/30 border border-zinc-800 rounded-xl hover:border-zinc-700 transition-colors"
        >
          <span className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
            <Icon name="message-square" size={14} className="text-violet-400" /> 语言指纹
          </span>
          <Icon name="chevron-down" size={14} className="text-zinc-500" />
        </button>
      </div>
    )
  }

  return (
    <div className="mb-6">
      <button
        onClick={() => setExpanded(false)}
        className="w-full flex items-center justify-between p-3 bg-violet-950/20 border border-violet-900/30 rounded-xl hover:border-violet-700/40 transition-colors mb-3"
      >
        <span className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
          <Icon name="message-square" size={14} className="text-violet-400" /> 语言指纹
        </span>
        <Icon name="chevron-up" size={14} className="text-zinc-500" />
      </button>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-zinc-600 text-sm">
          <div className="w-4 h-4 border-2 border-zinc-700 border-t-violet-400 rounded-full animate-spin mr-2" /> 分析对话风格...
        </div>
      ) : !voice || voice.dialogue_count === 0 ? (
        <div className="text-center py-6 text-zinc-600 text-xs">
          该角色暂无对话数据。写完包含该角色的章节后即可分析语言风格。
        </div>
      ) : (
        <div className="bg-zinc-950/30 border border-zinc-800 rounded-xl p-4 space-y-3">
          {/* Core stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="text-center">
              <div className="text-[9px] text-zinc-500">对话句数</div>
              <div className="text-sm font-bold text-violet-300">{voice.dialogue_count}</div>
            </div>
            <div className="text-center">
              <div className="text-[9px] text-zinc-500">平均句长</div>
              <div className="text-sm font-bold text-sky-300">{voice.avg_sentence_length.toFixed(0)}字</div>
            </div>
            <div className="text-center">
              <div className="text-[9px] text-zinc-500">语气倾向</div>
              <div className="text-sm font-bold text-amber-300">{TENDENCY_LABELS[voice.emotional_tendency] || voice.emotional_tendency}</div>
            </div>
          </div>

          {/* Sentence patterns */}
          <div>
            <div className="text-[10px] text-zinc-500 mb-1.5">句式分布</div>
            <div className="flex gap-2">
              {Object.entries(voice.sentence_pattern_ratio).map(([type, ratio]) => (
                <div key={type} className="flex-1">
                  <div className="text-[9px] text-zinc-600 text-center mb-1">
                    {type === 'declarative' ? '陈述' : type === 'interrogative' ? '疑问' : type === 'exclamatory' ? '感叹' : type}
                  </div>
                  <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-violet-500/60 rounded" style={{ width: `${ratio * 100}%` }} />
                  </div>
                  <div className="text-[9px] text-zinc-500 text-center mt-0.5">{(ratio * 100).toFixed(0)}%</div>
                </div>
              ))}
            </div>
          </div>

          {/* Catchphrases */}
          {voice.catchphrases.length > 0 && (
            <div>
              <div className="text-[10px] text-zinc-500 mb-1.5">口头禅 / 高频短语</div>
              <div className="flex flex-wrap gap-1.5">
                {voice.catchphrases.map((phrase, i) => (
                  <span key={i} className="text-[10px] bg-violet-900/30 text-violet-300 border border-violet-800/40 px-2 py-0.5 rounded-full">
                    {phrase}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Top words */}
          {voice.top_words.length > 0 && (
            <div>
              <div className="text-[10px] text-zinc-500 mb-1.5">高频用词 Top 10</div>
              <div className="flex flex-wrap gap-1">
                {voice.top_words.slice(0, 10).map((w, i) => (
                  <span key={i} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                    {w.word} <span className="text-zinc-600">×{w.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

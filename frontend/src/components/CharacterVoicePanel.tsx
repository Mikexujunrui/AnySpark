import { useState, useEffect } from 'react'
import Icon from './ui/Icon'

interface VoiceFingerprint {
  character_id: string
  character_name: string
  dialogue_count: number
  total_dialogue_chars: number
  top_words: { word: string; count: number }[]
  avg_sentence_length: number
  sentence_length_std?: number
  sentence_pattern_ratio: Record<string, number>
  catchphrases: string[]
  emotional_tendency: string
  // New fields for classical novel analysis
  unique_markers?: Record<string, number>
  exclusive_vocabulary?: string[]
  address_terms?: Record<string, string>
  rhetorical_question_rate?: number
  classical_citation_rate?: number
  command_ratio?: number
  request_ratio?: number
  sarcasm_indicators?: number
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
          {voice?.catchphrases?.length > 0 && (
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
          {voice?.top_words?.length > 0 && (
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

          {/* Classical character traits */}
          {(voice?.unique_markers || voice?.address_terms || voice?.rhetorical_question_rate !== undefined) && (
            <div className="border-t border-violet-900/30 pt-3 mt-3">
              <div className="text-[10px] text-violet-400 mb-2 flex items-center gap-1">
                <Icon name="star" size={10} /> 古典角色特质
              </div>

              {/* Rhetorical metrics */}
              <div className="grid grid-cols-2 gap-2 mb-2">
                {voice.rhetorical_question_rate !== undefined && voice.rhetorical_question_rate > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">反问句占比</div>
                    <div className="text-xs font-bold text-violet-300">{(voice.rhetorical_question_rate * 100).toFixed(1)}%</div>
                  </div>
                )}
                {voice.classical_citation_rate !== undefined && voice.classical_citation_rate > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">引经据典</div>
                    <div className="text-xs font-bold text-amber-300">{voice.classical_citation_rate.toFixed(2)}/千字</div>
                  </div>
                )}
                {voice.command_ratio !== undefined && voice.command_ratio > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">命令式</div>
                    <div className="text-xs font-bold text-red-300">{(voice.command_ratio * 100).toFixed(1)}%</div>
                  </div>
                )}
                {voice.request_ratio !== undefined && voice.request_ratio > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">请求式</div>
                    <div className="text-xs font-bold text-emerald-300">{(voice.request_ratio * 100).toFixed(1)}%</div>
                  </div>
                )}
                {voice.sarcasm_indicators !== undefined && voice.sarcasm_indicators > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">反讽频率</div>
                    <div className="text-xs font-bold text-sky-300">{voice.sarcasm_indicators.toFixed(2)}</div>
                  </div>
                )}
                {voice.sentence_length_std !== undefined && voice.sentence_length_std > 0 && (
                  <div className="text-center bg-violet-950/30 rounded-lg p-1.5">
                    <div className="text-[9px] text-zinc-500">句长波动</div>
                    <div className="text-xs font-bold text-cyan-300">{voice.sentence_length_std.toFixed(1)}</div>
                  </div>
                )}
              </div>

              {/* Unique markers */}
              {voice.unique_markers && Object.keys(voice.unique_markers).length > 0 && (
                <div className="mb-2">
                  <div className="text-[9px] text-zinc-500 mb-1">独有标记词</div>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(voice.unique_markers).slice(0, 8).map(([word, freq]) => (
                      <span key={word} className="text-[9px] bg-violet-900/40 text-violet-300 border border-violet-800/30 px-1.5 py-0.5 rounded-full">
                        {word} <span className="text-violet-500">{freq.toFixed(2)}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Exclusive vocabulary */}
              {voice.exclusive_vocabulary && voice.exclusive_vocabulary.length > 0 && (
                <div className="mb-2">
                  <div className="text-[9px] text-zinc-500 mb-1">独有词汇</div>
                  <div className="flex flex-wrap gap-1">
                    {voice.exclusive_vocabulary.slice(0, 10).map((word, i) => (
                      <span key={i} className="text-[9px] bg-amber-900/30 text-amber-300 border border-amber-800/30 px-1.5 py-0.5 rounded">
                        {word}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Address terms */}
              {voice.address_terms && Object.keys(voice.address_terms).length > 0 && (
                <div>
                  <div className="text-[9px] text-zinc-500 mb-1">称呼模式</div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(voice.address_terms).slice(0, 6).map(([target, term]) => (
                      <span key={target} className="text-[9px] bg-emerald-900/30 text-emerald-300 border border-emerald-800/30 px-1.5 py-0.5 rounded">
                        {target}: <span className="text-emerald-400">{term}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

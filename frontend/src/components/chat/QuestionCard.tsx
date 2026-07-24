import { useState } from 'react'

export default function QuestionCard({ question, onReply, onReject }) {
  const [tabIdx, setTabIdx] = useState(0)
  const [answers, setAnswers] = useState({})
  const qs = question.questions || []
  const q = qs[tabIdx]
  const isLast = tabIdx === qs.length - 1

  function toggleOption(label) {
    setAnswers(prev => {
      const cur = prev[tabIdx] || []
      if (q.multiple) {
        const next = cur.includes(label) ? cur.filter(l => l !== label) : [...cur, label]
        return { ...prev, [tabIdx]: next }
      }
      return { ...prev, [tabIdx]: [label] }
    })
  }

  function handleConfirm() {
    const result = qs.map((_, i) => answers[i] || ['已跳过'])
    onReply(result)
  }

  if (!q) return null

  return (
    <div className="flex justify-start">
      <div className="bg-zinc-800 border border-zinc-600 rounded-xl max-w-lg w-full overflow-hidden">
        {/* Tabs */}
        {qs.length > 1 && (
          <div className="flex border-b border-zinc-700 bg-zinc-800/50">
            {qs.map((qi, i) => (
              <button key={i} onClick={() => setTabIdx(i)}
                className={`px-3 py-1.5 text-xs transition-colors ${tabIdx === i ? 'text-zinc-100 border-b-2 border-blue-500' : 'text-zinc-500 hover:text-zinc-300'}`}>
                {qi.header?.slice(0, 10) || `Q${i+1}`}
              </button>
            ))}
          </div>
        )}

        <div className="p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-zinc-200">{q.question}</p>
            {q.multiple && <p className="text-[10px] text-zinc-500 mt-0.5">可多选</p>}
          </div>

          <div className="space-y-1.5">
            {q.options?.map(opt => {
              const sel = (answers[tabIdx] || []).includes(opt.label)
              return (
                <button key={opt.label} onClick={() => toggleOption(opt.label)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors border ${
                    sel ? 'bg-blue-900/30 border-blue-700 text-blue-300' : 'bg-zinc-700/30 border-zinc-700 text-zinc-300 hover:border-zinc-500'
                  }`}>
                  <div className="flex items-center gap-2">
                    {q.multiple && <span className={`w-3 h-3 rounded border text-[8px] flex items-center justify-center ${sel ? 'bg-blue-500 border-blue-500' : 'border-zinc-600'}`}>{sel ? '✓' : ''}</span>}
                    <span className="font-medium">{opt.label}</span>
                  </div>
                  {opt.description && <p className="text-zinc-500 mt-0.5 ml-5">{opt.description}</p>}
                </button>
              )
            })}
            {q.custom !== false && (
              <div className="flex gap-2 pt-1">
                <input
                  placeholder="输入自定义答案..."
                  className="flex-1 bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-blue-500"
                  onKeyDown={e => {
                    const target = e.target as HTMLInputElement
                    if (e.key === 'Enter' && target.value.trim()) {
                      toggleOption(target.value.trim())
                      target.value = ''
                    }
                  }}
                />
              </div>
            )}
          </div>

          <div className="flex gap-2 justify-end pt-2 border-t border-zinc-700">
            <button onClick={onReject} className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1">跳过</button>
            {qs.length > 1 && tabIdx > 0 && (
              <button onClick={() => setTabIdx(i => i - 1)} className="text-xs text-zinc-400 hover:text-zinc-200 px-2 py-1">← 上一步</button>
            )}
            {!isLast ? (
              <button onClick={() => setTabIdx(i => i + 1)} className="text-xs bg-zinc-600 text-zinc-200 rounded px-3 py-1 hover:bg-zinc-500">下一步 →</button>
            ) : (
              <button onClick={handleConfirm} className="text-xs bg-blue-600 text-white rounded px-4 py-1 hover:bg-blue-500 font-medium">确认</button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import Icon from './ui/Icon'
import { showToast } from './ui/toast-utils'

interface PipelineLevel {
  event: string
  level?: number
  level_name?: string
  output?: string
  word_count?: number
  error?: string
  final_word_count?: number
}

export default function OutlinePipelinePanel({ bookId, onDone }: { bookId: string; onDone: () => void }) {
  const [seed, setSeed] = useState('')
  const [levels, setLevels] = useState(4)
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<PipelineLevel[]>([])

  async function runPipeline() {
    if (!seed.trim()) {
      showToast('请输入一句话设定', 'error')
      return
    }
    setRunning(true)
    setResults([])
    try {
      const res = await fetch(`/api/books/${bookId}/chapters`, {
        method: 'GET',
      })
      // Use the agent tool approach: call via chat SSE
      // For now, use the direct outline pipeline approach
      const pipelineRes = await fetch(`/api/books/${bookId}/outline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed: seed.trim(), levels }),
      })
      if (pipelineRes.ok) {
        const data = await pipelineRes.json()
        setResults(data.results || [])
        showToast('大纲展开完成', 'success')
      } else {
        showToast('大纲展开失败，请在对话中使用 expand_outline_pipeline 工具', 'error')
      }
    } catch (e) {
      showToast('网络错误', 'error')
    }
    setRunning(false)
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon name="sparkles" size={16} className="text-violet-400" />
        <h3 className="text-sm font-semibold text-zinc-200">大纲逐级展开</h3>
        <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">Pipeline</span>
      </div>

      <div className="space-y-3 mb-4">
        <div>
          <label className="text-[10px] text-zinc-400 mb-1 block">一句话故事设定</label>
          <textarea
            value={seed}
            onChange={e => setSeed(e.target.value)}
            placeholder="如：一个少年在乱世中觉醒逆天血脉，踏上修仙之路..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-violet-600/50 resize-none"
            rows={2}
            disabled={running}
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-[10px] text-zinc-400">展开层级</label>
          <select
            value={levels}
            onChange={e => setLevels(Number(e.target.value))}
            disabled={running}
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none"
          >
            <option value={1}>1级（仅总纲）</option>
            <option value={2}>2级（总纲+分卷）</option>
            <option value={3}>3级（+章节纲）</option>
            <option value={4}>4级（+细纲）</option>
          </select>
          <button
            onClick={runPipeline}
            disabled={running || !seed.trim()}
            className="ml-auto flex items-center gap-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white rounded-lg px-3 py-1.5 font-medium transition-colors"
          >
            {running ? (
              <><div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> 展开中...</>
            ) : (
              <><Icon name="play" size={12} /> 开始展开</>
            )}
          </button>
        </div>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((r, i) => {
            if (r.event === 'level_completed') {
              return (
                <div key={i} className="border border-zinc-800 rounded-lg p-3 bg-zinc-950/30">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-mono bg-violet-500/10 text-violet-400 px-1.5 py-0.5 rounded">
                      Level {r.level}
                    </span>
                    <span className="text-xs font-semibold text-zinc-200">{r.level_name}</span>
                    {r.word_count && (
                      <span className="text-[10px] text-zinc-600 ml-auto">{r.word_count} 字</span>
                    )}
                  </div>
                  {r.output && (
                    <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {r.output.length > 500 ? r.output.slice(0, 500) + '...' : r.output}
                    </p>
                  )}
                </div>
              )
            } else if (r.event === 'pipeline_complete') {
              return (
                <div key={i} className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-3">
                  <Icon name="check-circle" size={14} />
                  展开完成！总字数：{r.final_word_count}
                  <button onClick={onDone} className="ml-auto text-[10px] text-violet-400 hover:text-violet-300">
                    刷新大纲 →
                  </button>
                </div>
              )
            } else if (r.event === 'level_failed') {
              return (
                <div key={i} className="text-xs text-red-400 bg-red-950/20 border border-red-900/30 rounded-lg p-3">
                  Level {r.level} 失败：{r.error}
                </div>
              )
            }
            return null
          })}
        </div>
      )}

      {results.length === 0 && !running && (
        <div className="text-center py-6 text-zinc-600 text-xs">
          输入一句话设定，AI 将逐级展开为总纲 → 分卷纲 → 章节纲 → 细纲
        </div>
      )}
    </div>
  )
}

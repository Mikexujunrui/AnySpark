import { useState } from 'react'

export default function PlotCardSelector({ data, onSelect, onReject }) {
  const [customText, setCustomText] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const cards = data.cards || []

  const TONE_COLORS = {
    '热血': 'bg-red-900/40 text-red-300', '虐心': 'bg-purple-900/40 text-purple-300',
    '悬疑': 'bg-amber-900/40 text-amber-300', '治愈': 'bg-green-900/40 text-green-300',
    '反转': 'bg-cyan-900/40 text-cyan-300', '日常': 'bg-zinc-700/40 text-zinc-300',
    '搞笑': 'bg-yellow-900/40 text-yellow-300', '黑暗': 'bg-zinc-900/60 text-zinc-200',
  }

  function handleSelectCard(card) {
    setSelectedId(card.id)
    const text = `[${card.title}] ${card.description}\n关键事件: ${(card.key_events || []).join('、')}\n影响: ${card.impact || ''}`
    onSelect(text)
  }

  function handleCustom() {
    if (!customText.trim()) return
    onSelect(`[自定义方向] ${customText.trim()}`)
  }

  return (
    <div className="flex justify-start w-full">
      <div className="max-w-[90%] w-full space-y-3">
        {data.context_summary && (
          <div className="text-xs text-zinc-500 px-1 mb-1">当前状态: {data.context_summary}</div>
        )}
        <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
          {cards.map(card => {
            const toneClass = TONE_COLORS[card.tone] || 'bg-zinc-800/50 text-zinc-300'
            return (
              <div key={card.id}
                onClick={() => handleSelectCard(card)}
                className={`rounded-xl border p-4 cursor-pointer transition-all hover:scale-[1.01] ${
                  selectedId === card.id
                    ? 'border-cyan-500 bg-cyan-950/20 ring-1 ring-cyan-500/30'
                    : 'border-zinc-700 bg-zinc-900 hover:border-zinc-500'
                }`}>
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="text-sm font-semibold text-zinc-100 flex-1">{card.title}</h4>
                  {card.tone && <span className={`text-[10px] px-2 py-0.5 rounded-full ${toneClass}`}>{card.tone}</span>}
                </div>
                <p className="text-xs text-zinc-300 leading-relaxed mb-2">{card.description}</p>
                {card.key_events && card.key_events.length > 0 && (
                  <div className="mb-2">
                    <div className="text-[10px] text-zinc-500 mb-1">关键事件</div>
                    <div className="flex flex-wrap gap-1">
                      {card.key_events.map((ev, i) => (
                        <span key={i} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">{ev}</span>
                      ))}
                    </div>
                  </div>
                )}
                {card.impact && <p className="text-[10px] text-blue-400/80 mt-1">影响: {card.impact}</p>}
                {card.risk && <p className="text-[10px] text-amber-400/60 mt-0.5">风险: {card.risk}</p>}
              </div>
            )
          })}
        </div>
        <div className="border-t border-zinc-800 pt-3 space-y-2">
          <div className="flex gap-2">
            <input value={customText} onChange={e => setCustomText(e.target.value)}
              placeholder="自定义方向: 输入你想要的剧情走向..."
              onKeyDown={e => { if (e.key === 'Enter') handleCustom() }}
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-600" />
            <button onClick={handleCustom} disabled={!customText.trim()}
              className="text-xs bg-cyan-800 hover:bg-cyan-700 text-cyan-100 rounded-lg px-3 py-2 disabled:opacity-40">确认</button>
          </div>
          <button onClick={onReject}
            className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 transition-colors">
            全部不满意，我重新描述方向 →
          </button>
        </div>
      </div>
    </div>
  )
}

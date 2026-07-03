import { useState, useRef, useEffect } from 'react'

export default function SlashMenu({ items, selectedIdx, onSelect, onNavigate, onClose, allSkills }) {
  const menuRef = useRef(null)
  const [focus, setFocus] = useState('left')
  const [rightIdx, setRightIdx] = useState(0)
  const [fetchedStyles, setFetchedStyles] = useState(null)
  const selected = items[selectedIdx]
  const showRight = selected && (selected.cmd === '/skills' || selected.cmd === '/help' || selected.cmd === '/style')
  const rightItems = selected?.cmd === '/skills' ? allSkills : items

  useEffect(() => {
    if (selected?.cmd === '/style' && !fetchedStyles) {
      fetch('/api/styles')
        .then(r => r.json())
        .then(data => setFetchedStyles(Array.isArray(data?.styles) ? data.styles : []))
        .catch(() => {})
    }
  }, [selected?.cmd, fetchedStyles])

  useEffect(() => {
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  useEffect(() => {
    setFocus('left')
    setRightIdx(0)
  }, [selectedIdx])

  // Expose navigation handler for parent's onKeyDown via ref
  const navHandler = useRef(null)
  useEffect(() => {
    navHandler.current = (e) => {
      if (focus === 'left') {
        if (e.key === 'ArrowRight' && showRight) {
          e.preventDefault()
          setFocus('right')
          setRightIdx(0)
          return true
        }
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          if (selectedIdx < items.length - 1) onNavigate(selectedIdx + 1)
          return true
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          if (selectedIdx > 0) onNavigate(selectedIdx - 1)
          return true
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault()
          onSelect(items[selectedIdx])
          return true
        }
      } else {
        if (e.key === 'ArrowLeft') {
          e.preventDefault()
          setFocus('left')
          return true
        }
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setRightIdx(i => Math.min(i + 1, rightItems.length - 1))
          return true
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setRightIdx(i => Math.max(i - 1, 0))
          return true
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault()
          if (selected?.cmd === '/skills' && rightItems[rightIdx]) {
            onSelect(rightItems[rightIdx])
          }
          return true
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return true
      }
      return false
    }
    if (menuRef.current) {
      menuRef.current._slashNav = navHandler.current
    }
  })

  if (items.length === 0) return null

  const maxListHeight = Math.min(items.length * 40 + 28, 320)

  return (
    <div ref={menuRef} data-slash-menu
      className="absolute bottom-full left-0 mb-2 flex rounded-xl shadow-2xl overflow-hidden z-50">
      {/* Left column: built-in commands */}
      <div className={`bg-zinc-900 border border-zinc-700 overflow-hidden ${showRight ? 'rounded-l-xl' : 'rounded-xl'}`}
        style={{ width: showRight ? '260px' : '380px' }}>
        <div className={`px-3 py-2 text-[10px] border-b bg-zinc-950 flex items-center justify-between ${
          focus === 'left' ? 'text-blue-400 border-blue-800' : 'text-zinc-500 border-zinc-800'
        }`}>
          <span>命令</span>
          {showRight && <span className="text-[10px] text-zinc-600">→ 切换右列</span>}
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: maxListHeight }}>
          {items.map((s, i) => (
            <button key={s.cmd} onMouseDown={() => { onSelect(s); setFocus('left') }}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors flex items-center gap-2 ${
                i === selectedIdx
                  ? (focus === 'left'
                      ? 'bg-blue-900/40 text-blue-200 border-l-2 border-blue-500'
                      : 'bg-zinc-800/30 text-zinc-300 border-l-2 border-zinc-700')
                  : 'text-zinc-300 hover:bg-zinc-800 border-l-2 border-transparent'
              }`}>
              <span className="font-mono text-blue-400 shrink-0 text-xs w-14">{s.cmd}</span>
              <span className="text-zinc-400 text-xs truncate">{s.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Right column: skills list or help detail */}
      {showRight && (
        <div className="bg-zinc-900 border-y border-r border-zinc-700 rounded-r-xl overflow-hidden"
          style={{ width: '320px', maxHeight: maxListHeight + 28 }}>
          <div className={`px-3 py-2 text-[10px] border-b bg-zinc-950 sticky top-0 flex items-center justify-between ${
            focus === 'right' ? 'text-emerald-400 border-emerald-800' : 'text-zinc-500 border-zinc-800'
          }`}>
            <span>{selected.cmd === '/skills' ? '可用技能' : selected.cmd === '/style' ? '可用风格' : '命令说明'}</span>
            <span className="text-[10px] text-zinc-600">← 切回左列</span>
          </div>
          <div className="overflow-y-auto p-2" style={{ maxHeight: maxListHeight - 28 }}>
            {selected.cmd === '/skills' ? (
              allSkills.length === 0 ? (
                <div className="text-xs text-zinc-600 px-2 py-4 text-center">暂无可用技能</div>
              ) : (
                <div className="space-y-2">
                  {allSkills.map((sk, si) => (
                    <button key={sk.cmd} onMouseDown={() => onSelect(sk)}
                      className={`w-full text-left rounded-lg p-2.5 transition-colors ${
                        focus === 'right' && si === rightIdx
                          ? 'bg-emerald-900/30 ring-1 ring-emerald-700'
                          : 'bg-zinc-800/50 hover:bg-zinc-800'
                      }`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs text-emerald-400">{sk.cmd}</span>
                      </div>
                      <p className="text-xs text-zinc-400 leading-relaxed mb-1.5">{sk.desc}</p>
                      {sk.steps && sk.steps.length > 0 && (
                        <div className="space-y-0.5">
                          {sk.steps.map((step, stepIdx) => (
                            <div key={stepIdx} className="flex items-center gap-2 text-[11px]">
                              <span className="text-zinc-600 w-3 shrink-0">{stepIdx + 1}.</span>
                              <span className="text-emerald-500/60 font-mono">{step.tool || ''}</span>
                              <span className="text-zinc-500">{step.label || ''}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )
            ) : selected.cmd === '/help' ? (
              <div className="space-y-1">
                {items.map((s, si) => (
                  <div key={s.cmd}
                    className={`flex items-start gap-2.5 py-2 px-2 rounded-lg transition-colors ${
                      focus === 'right' && si === rightIdx ? 'bg-zinc-800/50' : ''
                    }`}>
                    <span className="font-mono text-xs text-blue-400 w-14 shrink-0">{s.cmd}</span>
                    <div className="min-w-0">
                      <p className="text-xs text-zinc-300">{s.desc}</p>
                      <p className="text-[11px] text-zinc-600 mt-0.5">用法: {s.usage}</p>
                    </div>
                  </div>
                ))}
                {allSkills.length > 0 && (
                  <>
                    <div className="border-t border-zinc-800 my-2" />
                    <p className="text-[10px] text-zinc-600 mb-1 px-2">可用技能（输入 /技能名 调用）:</p>
                    {allSkills.map(s => (
                      <div key={s.cmd} className="flex items-start gap-2.5 py-1 px-2">
                        <span className="font-mono text-xs text-emerald-500/70 w-20 shrink-0">{s.cmd}</span>
                        <span className="text-xs text-zinc-500">{s.desc}</span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            ) : selected.cmd === '/style' ? (
              <div className="space-y-2">
                {(fetchedStyles || []).map((st, si) => (
                  <div key={st.name}
                    className={`rounded-lg p-2.5 transition-colors ${
                      focus === 'right' && si === rightIdx ? 'bg-emerald-900/30 ring-1 ring-emerald-700' : 'bg-zinc-800/50'
                    }`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-amber-400">{st.name}</span>
                      {st.source === 'user' && (
                        <span className="text-[9px] bg-emerald-900/40 text-emerald-400 px-1 rounded">自定义</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 leading-relaxed mb-1">{st.description}</p>
                    {st.applies_to && st.applies_to.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {st.applies_to.map(t => (
                          <span key={t} className="text-[10px] bg-zinc-700 rounded px-1.5 py-0.5 text-zinc-500">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                <div className="border-t border-zinc-800 pt-2 mt-2">
                  <p className="text-[11px] text-zinc-600">输入 <span className="text-amber-400 font-mono">/style 风格名</span> 切换风格</p>
                  <p className="text-[11px] text-zinc-600 mt-0.5">AI 会根据场景自动推荐并切换风格</p>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

// ApprovalContext — 独立审批功能节点（全局，不耦合任何具体功能）
// 高负载操作通过 requestApproval 申请执行；自主模式开启时默认同意（不弹窗）。
// 使用：const { requestApproval } = useApproval()
//   const ok = await requestApproval({ title, desc, estSeconds, cost })
//   返回 true = 同意执行；false = 用户拒绝
import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { playAttention } from '../../lib/sound'

export interface ApprovalRequest {
  id: string
  title: string
  desc?: string
  estSeconds?: number      // 预估耗时（秒）
  cost?: 'low' | 'medium' | 'high'
  payload?: unknown        // 审批通过后回传给调用方
}

interface ApprovalContextValue {
  /** 申请审批。autoMode 开启时直接返回 true。返回 Promise<boolean> */
  requestApproval: (req: Omit<ApprovalRequest, 'id'>) => Promise<boolean>
  /** 自主模式开关（由宿主设置） */
  setAutoMode: (on: boolean) => void
  isAutoMode: () => boolean
}

const ApprovalContext = createContext<ApprovalContextValue | null>(null)

export function ApprovalProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<ApprovalRequest | null>(null)
  const resolverRef = useRef<((ok: boolean) => void) | null>(null)
  const autoModeRef = useRef(false)
  const [autoMode, setAutoModeState] = useState(false)

  const requestApproval = useCallback((req: Omit<ApprovalRequest, 'id'>) => {
    // 自主模式：默认同意，不打扰
    if (autoModeRef.current) return Promise.resolve(true)

    return new Promise<boolean>((resolve) => {
      const id = `appr-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      resolverRef.current = resolve
      setPending({ ...req, id })
      // S155：需要人类操作（授权/确认）→ 提示音（主循环内仅此场景响）
      playAttention()
    })
  }, [])

  const respond = useCallback((ok: boolean) => {
    if (resolverRef.current) {
      resolverRef.current(ok)
      resolverRef.current = null
    }
    setPending(null)
  }, [])

  const setAutoMode = useCallback((on: boolean) => {
    autoModeRef.current = on
    setAutoModeState(on)
  }, [])

  const isAutoMode = useCallback(() => autoModeRef.current, [])

  return (
    <ApprovalContext.Provider value={{ requestApproval, setAutoMode, isAutoMode }}>
      {children}
      {/* 独立审批弹窗节点（不耦合业务组件） */}
      {pending && (
        <ApprovalModal
          req={pending}
          autoMode={autoMode}
          onApprove={() => respond(true)}
          onReject={() => respond(false)}
        />
      )}
    </ApprovalContext.Provider>
  )
}

export function useApproval(): ApprovalContextValue {
  const ctx = useContext(ApprovalContext)
  if (!ctx) throw new Error('useApproval must be used within ApprovalProvider')
  return ctx
}

// 审批弹窗（独立节点 UI）
function ApprovalModal({ req, autoMode, onApprove, onReject }: {
  req: ApprovalRequest
  autoMode: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const costColor = req.cost === 'high' ? 'text-red-400 border-red-800/50 bg-red-900/30'
    : req.cost === 'medium' ? 'text-amber-400 border-amber-800/50 bg-amber-900/30'
    : 'text-sky-400 border-sky-800/50 bg-sky-900/30'

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onReject} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-start gap-3 mb-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border ${costColor}`}>
            <span className="text-base">⚡</span>
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-zinc-100">执行请求 · {req.title}</h3>
            {req.desc && <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{req.desc}</p>}
            <div className="flex gap-2 mt-2">
              {req.estSeconds != null && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                  约 {req.estSeconds}s
                </span>
              )}
              {req.cost && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${costColor}`}>
                  {req.cost === 'high' ? '高负载' : req.cost === 'medium' ? '中负载' : '低负载'}
                </span>
              )}
              {autoMode && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-400">
                  自主模式自动同意
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onReject} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors">
            拒绝
          </button>
          <button onClick={onApprove} className="px-5 py-2 text-sm font-medium text-white bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors">
            允许执行
          </button>
        </div>
      </div>
    </div>
  )
}

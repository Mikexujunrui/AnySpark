import { useState, useEffect } from 'react'
import CharacterDetail from './CharacterDetail'
import RelationGraph from './RelationGraph'
import CharacterHeatmap from './CharacterHeatmap'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import { SkeletonCharGrid } from './ui/Skeleton'
import { useRefreshKey, triggerRefresh } from '../store'
import { api } from '../api'

const SORT_OPTIONS = [
  { value: 'alpha', label: '按名称' },
  { value: 'relations', label: '按关系数' },
  { value: 'group', label: '按阵营/组织' },
]

export default function CharacterGallery({ bookId }) {
  const refreshKey = useRefreshKey()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedTime, setSelectedTime] = useState('all')
  const [selectedChar, setSelectedChar] = useState(null)
  const [viewMode, setViewMode] = useState('cards')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('alpha')
  const [deleteCharId, setDeleteCharId] = useState(null)

  useEffect(() => {
    loadData()
  }, [bookId, refreshKey])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/characters`)
      setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function confirmDeleteCharacter() {
    if (!deleteCharId) return
    try {
      await api.deleteEntity(bookId, deleteCharId)
      setDeleteCharId(null)
      loadData()
      triggerRefresh()
    } catch (e) {
      console.error(e)
    }
  }

  function getCharAtTime(char, timePoint) {
    if (timePoint === 'all') return char.data
    const snap = [...char.snapshots]
      .filter(s => s.timeOrder <= (getTimeOrder(timePoint)))
      .sort((a, b) => b.timeOrder - a.timeOrder)[0]
    if (snap) return { ...char.data, ...snap.data }
    return char.data
  }

  function getTimeOrder(tp) {
    const event = data?.timelineEvents?.find(e => e.timePoint === tp)
    return event?.timeOrder ?? 0
  }

  function getSortedFilteredChars() {
    let chars = data?.characters || []
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      chars = chars.filter(c =>
        c.name.toLowerCase().includes(q) ||
        (c.aliases || []).some(a => a.toLowerCase().includes(q)) ||
        Object.values(c.data || {}).some(v => typeof v === 'string' && v.toLowerCase().includes(q))
      )
    }
    if (sortBy === 'alpha') {
      chars = [...chars].sort((a, b) => a.name.localeCompare(b.name, 'zh'))
    } else if (sortBy === 'relations') {
      chars = [...chars].sort((a, b) => (b.relationCount || 0) - (a.relationCount || 0))
    } else if (sortBy === 'group') {
      chars = [...chars].sort((a, b) => {
        const ga = a.data?.organization || a.data?.origin || a.data?.faction || ''
        const gb = b.data?.organization || b.data?.origin || b.data?.faction || ''
        if (ga !== gb) return ga.localeCompare(gb, 'zh')
        return a.name.localeCompare(b.name, 'zh')
      })
    }
    return chars
  }

  if (loading) return <SkeletonCharGrid count={8} />
  if (!data || !data.characters || data.characters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-zinc-600">
        <Icon name="users" size={36} className="mb-3 text-zinc-700" />
        <p>暂无角色数据</p>
        <p className="text-sm mt-1">先在对话中用 /s 添加角色设定</p>
      </div>
    )
  }

  const timelineOptions = [
    { value: 'all', label: '全部时间' },
    ...(data.timelineEvents || []).map(e => ({ value: e.timePoint, label: e.label })),
  ]

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-4 px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0">
        <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
          <button
            onClick={() => setViewMode('cards')}
            className={`px-4 py-1.5 text-xs rounded-md transition-colors ${viewMode === 'cards' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Icon name="layout-grid" size={12} className="inline" /> 卡片
          </button>
          <button
            onClick={() => setViewMode('graph')}
            className={`px-4 py-1.5 text-xs rounded-md transition-colors ${viewMode === 'graph' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Icon name="link" size={12} className="inline" /> 关系网
          </button>
          <button
            onClick={() => setViewMode('heatmap')}
            className={`px-4 py-1.5 text-xs rounded-md transition-colors ${viewMode === 'heatmap' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Icon name="bar-chart" size={12} className="inline" /> 戏份
          </button>
        </div>

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索角色..."
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 w-36 focus:outline-none focus:border-zinc-500 focus:w-48 transition-all"
        />

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={selectedTime}
          onChange={(e) => setSelectedTime(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
        >
          {timelineOptions.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <span className="text-xs text-zinc-500 ml-auto">{data.characters.length} 个角色</span>
      </div>

      {viewMode === 'heatmap' ? (
        <div className="flex-1 overflow-hidden"><CharacterHeatmap bookId={bookId} /></div>
      ) : viewMode === 'graph' ? (
        <RelationGraph bookId={bookId} characters={data.characters}
          timelineEvents={data.timelineEvents} selectedTime={selectedTime}
          onSelectChar={setSelectedChar} />
      ) : (
        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {getSortedFilteredChars().map(char => {
              const snapData = getCharAtTime(char, selectedTime)
              return (
                <div
                  key={char.id}
                  onClick={() => setSelectedChar(char)}
                  className="bg-zinc-800/40 border border-zinc-800 rounded-xl p-4 cursor-pointer hover:border-zinc-600 hover:bg-zinc-800/60 transition-all group relative"
                >
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteCharId(char.id) }}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 bg-zinc-900/50 hover:bg-red-950/50 w-7 h-7 rounded-md flex items-center justify-center transition-all z-10"
                    aria-label={`删除角色 ${char.name}`}
                  >
                    <Icon name="trash" size={12} />
                  </button>
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-zinc-600 to-zinc-800 flex items-center justify-center text-xl mb-3 mx-auto group-hover:scale-110 transition-transform">
                    {char.name[0]}
                  </div>
                  <h4 className="text-sm font-semibold text-zinc-200 text-center mb-1">{char.name}</h4>
                  {char.aliases?.length > 0 && (
                    <p className="text-[10px] text-zinc-500 text-center mb-2">{char.aliases.join(' / ')}</p>
                  )}
                  <div className="space-y-1 text-[11px]">
                    {snapData.appearance && (
                      <p className="text-zinc-400"><span className="text-zinc-600">外貌：</span>{snapData.appearance.slice(0, 30)}{snapData.appearance.length > 30 ? '...' : ''}</p>
                    )}
                    {snapData.personality && (
                      <p className="text-zinc-400"><span className="text-zinc-600">性格：</span>{snapData.personality.slice(0, 30)}{snapData.personality.length > 30 ? '...' : ''}</p>
                    )}
                    {snapData.abilities && (
                      <p className="text-zinc-400"><span className="text-zinc-600">能力：</span>{snapData.abilities.slice(0, 30)}{snapData.abilities.length > 30 ? '...' : ''}</p>
                    )}
                  </div>
                  <div className="flex gap-2 mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-600">
                    <span>{char.relationCount} 关系</span>
                    {char.snapshotCount > 0 && <span>{char.snapshotCount} 快照</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {deleteCharId && (() => {
        const char = data?.characters?.find(c => c.id === deleteCharId)
        return (
          <ConfirmModal
            open={true}
            title="删除角色"
            message={`确定删除「${char?.name || '此角色'}」？该角色的所有阶段、快照、关系都会一并删除，此操作不可撤销。`}
            danger
            confirmText="删除角色"
            onConfirm={confirmDeleteCharacter}
            onCancel={() => setDeleteCharId(null)}
          />
        )
      })()}

      {selectedChar && (
        <CharacterDetail
          character={selectedChar}
          timelineEvents={data.timelineEvents}
          bookId={bookId}
          onClose={() => setSelectedChar(null)}
          onUpdated={() => { loadData(); triggerRefresh() }}
        />
      )}
    </div>
  )
}

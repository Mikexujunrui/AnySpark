import { useState, useEffect, useRef } from 'react'
import ConfirmModal from './ui/ConfirmModal'
import Icon from './ui/Icon'
import { showToast } from './ui/Toast'
import { SkeletonSidebar } from './ui/Skeleton'
import { useRefreshKey, triggerRefresh } from "../store"
import MarkdownEditor from './editor/MarkdownEditor'
import { useTabs, openTab, closeTab, setActiveTab } from "../stores/tabStore"

export default function ChaptersPanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [chapters, setChapters] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const tabs = useTabs()
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [showChapterOutline, setShowChapterOutline] = useState(false)
  const [chapterOutlineData, setChapterOutlineData] = useState(null)
  const [chapterDetailOutlineData, setChapterDetailOutlineData] = useState(null)
  const [outlineLoading, setOutlineLoading] = useState(false)
  const [outlineViewMode, setOutlineViewMode] = useState('outline')
  const [previewVersion, setPreviewVersion] = useState(null)
  const [previewContent, setPreviewContent] = useState('')
  const [previewOriginal, setPreviewOriginal] = useState(null)
  const [previewPatches, setPreviewPatches] = useState([])
  const [diffMode, setDiffMode] = useState('after')
  const [commitMsg, setCommitMsg] = useState('')
  const [deleteChapter, setDeleteChapter] = useState(false)
  const [deleteVersion, setDeleteVersion] = useState(null)
  const [autoSaved] = useState(false)
  const [revertVersionId, setRevertVersionId] = useState(null)
  const [showCreateMenu, setShowCreateMenu] = useState(false)
  const [chapterSearch, setChapterSearch] = useState('')
  const createMenuRef = useRef(null)
  const [recentlyEdited] = useState(new Set())
  const editorInstanceRef = useRef(null)

  // Find-replace state
  const [showFindReplace, setShowFindReplace] = useState(false)
  const [findText, setFindText] = useState('')
  const [replaceText, setReplaceText] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [matches, setMatches] = useState([])
  const findInputRef = useRef(null)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadChapters() }, [bookId, refreshKey])

  // Close create menu on outside click
  useEffect(() => {
    if (!showCreateMenu) return
    function handleClick(e) {
      if (createMenuRef.current && !createMenuRef.current.contains(e.target)) {
        setShowCreateMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showCreateMenu])

  // 移除自动保存：用户只能通过 Ctrl+S 手动保存，避免点击编辑5秒后自动创建版本

  // Ctrl+S 快捷键保存 - 使用 ref 避免闭包陈旧问题
  const handleSaveRef = useRef(null)
  useEffect(() => {
    handleSaveRef.current = () => {
      if (!editing || saving) return
      handleSave()
    }
  })

  useEffect(() => {
    function handleKeyDown(e) {
      // Ctrl+S save
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        if (handleSaveRef.current) handleSaveRef.current()
      }
      // Ctrl+F open find-replace (only in editing mode)
      if ((e.ctrlKey || e.metaKey) && e.key === 'f' && editing) {
        e.preventDefault()
        setShowFindReplace(true)
        setTimeout(() => findInputRef.current?.focus(), 0)
      }
      // F3 or Ctrl+G: next match
      if (editing && showFindReplace && (
        (e.key === 'F3') || ((e.ctrlKey || e.metaKey) && e.key === 'g' && !e.shiftKey)
      )) {
        e.preventDefault()
        doFindNext()
      }
      // Shift+F3 or Ctrl+Shift+G: previous match
      if (editing && showFindReplace && (
        (e.key === 'F3' && e.shiftKey) || ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'G')
      )) {
        e.preventDefault()
        doFindPrev()
      }
      // Escape: close find-replace
      if (e.key === 'Escape' && showFindReplace) {
        e.preventDefault()
        setShowFindReplace(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [editing, showFindReplace]) // 不再需要依赖 saving，但需要 showFindReplace 和 editing

  // 查找替换核心函数
  useEffect(() => {
    // findText 或 caseSensitive 变化时重新计算匹配
    if (!findText) {
      setMatches([])
      setMatchIndex(0)
      return
    }
    const needle = caseSensitive ? findText : findText.toLowerCase()
    const haystack = caseSensitive ? editContent : editContent.toLowerCase()
    const newMatches = []
    let pos = 0
    while (pos < haystack.length) {
      const idx = haystack.indexOf(needle, pos)
      if (idx === -1) break
      newMatches.push({ start: idx, end: idx + findText.length })
      pos = idx + 1
    }
    setMatches(newMatches)
    setMatchIndex(prev => newMatches.length > 0 ? Math.min(prev, newMatches.length - 1) : 0)
  }, [findText, editContent, caseSensitive])

  function doFindNext() {
    setMatchIndex(prev => matches.length === 0 ? 0 : (prev + 1) % matches.length)
  }

  function doFindPrev() {
    setMatchIndex(prev => matches.length === 0 ? 0 : (prev - 1 + matches.length) % matches.length)
  }

  function doReplace() {
    if (matches.length === 0) return
    const match = matches[matchIndex]
    if (!match) return
    const newContent = editContent.slice(0, match.start) + replaceText + editContent.slice(match.end)
    setEditContent(newContent)
  }

  function doReplaceAll() {
    if (!findText || matches.length === 0) return
    const needle = caseSensitive ? findText : findText.toLowerCase()
    let result = ''
    const pos = 0
    const haystack = editContent
    if (!caseSensitive) {
      let searchPos = 0
      const lowerHaystack = haystack.toLowerCase()
      while (searchPos < lowerHaystack.length) {
        const idx = lowerHaystack.indexOf(needle, searchPos)
        if (idx === -1) {
          result += haystack.slice(searchPos)
          break
        }
        result += haystack.slice(searchPos, idx) + replaceText
        searchPos = idx + findText.length
      }
    } else {
      result = haystack.split(findText).join(replaceText)
    }
    setEditContent(result)
    setMatches([])
    setMatchIndex(0)
    showToast(`已替换 ${matches.length} 处`, 'success')
  }

  // 跳转到匹配位置时 
  useEffect(() => {
    if (!showFindReplace || matches.length === 0) return
    const match = matches[matchIndex]
    if (!match) return
    // 在WYSIWYG模式下无法精确定位，但匹配计数仍然可用
  }, [matchIndex, matches, showFindReplace])

  // 进入编辑时（不操作DOM，由MarkdownEditor内部管理滚动）
  useEffect(() => {
    // 滚动位置由 MarkdownEditor 内部管理
  }, [editing, selectedId])

  async function loadChapters() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/chapters`)
      const data = await res.json()
      const arr = Array.isArray(data) ? data : []
      setChapters(arr)
      if (!selectedId && arr.length > 0) {
        setSelectedId(data[0].id)
        setEditTitle(data[0].title || '')
        setEditContent(data[0].content || '')
      } else if (selectedId) {
        const current = arr.find(c => c.id === selectedId)
        if (current) {
          setEditTitle(current.title || '')
          setEditContent(current.content || '')
        }
      }
    } catch (e) { showToast('加载章节失败', 'error') }
    setLoading(false)
  }

  function selectChapter(ch) {
    setEditing(false)
    setShowHistory(false)
    setShowChapterOutline(false)
    setShowFindReplace(false)
    setFindText('')
    setReplaceText('')
    setMatches([])
    setMatchIndex(0)
    setChapterOutlineData(null)
    setChapterDetailOutlineData(null)
    setPreviewVersion(null)
    setPreviewOriginal(null)
    setPreviewPatches([])
    setSelectedId(ch.id)
    setEditTitle(ch.title || '')
    setEditContent(ch.content || '')
    setCommitMsg('')
    openTab(ch.id, ch.title, bookId)
  }

  async function handleCreate(isExtra = false) {
    const regularCount = chapters.filter(c => !c.is_extra).length
    const extraCount = chapters.filter(c => c.is_extra).length
    const title = isExtra ? `番外${extraCount + 1}` : `第${regularCount + 1}章`
    try {
      const res = await fetch(`/api/books/${bookId}/chapters`, {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content: '', is_extra: isExtra }),
      })
      const newCh = await res.json()
      setChapters(prev => [...prev, newCh])
      selectChapter(newCh)
      triggerRefresh()
      showToast(isExtra ? '番外已创建' : '章节已创建', 'success')
    } catch (e) {
      showToast('创建失败', 'error')
    }
    setShowCreateMenu(false)
  }

  async function handleSave() {
    if (!selectedId) return
    setSaving(true)
    try {
      await fetch(`/api/books/${bookId}/chapters/${selectedId}`, {
        method: 'PUT',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: editTitle,
          content: editContent,
          message: commitMsg || '手动编辑',
        }),
      })
      setEditing(false)
      setCommitMsg('')
      loadChapters()
      showToast('已保存', 'success')
    } catch (e) {
      showToast('保存失败', 'error')
    }
    setSaving(false)
  }

  async function handleExport() {
    try {
      const bookRes = await fetch(`/api/books/${bookId}`)
      const book = await bookRes.json()

      const res = await fetch(`/api/books/${bookId}/export?format=txt`)
      if (!res.ok) throw new Error('导出请求失败')
      const blob = await res.blob()

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${book.title || '未命名'}.txt`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      showToast('导出成功', 'success')
    } catch (e) {
      showToast('导出失败', 'error')
      console.error('Export error:', e)
    }
  }

  async function handlePromote() {
    if (!selectedId) return
    try {
      const res = await fetch(`/api/books/${bookId}/chapters/${selectedId}/promote`, { method: 'POST' })
      const data = await res.json()
      setChapters(prev => prev.map(c => c.id === selectedId ? { ...c, status: data.status } : c))
      showToast('已提升为定稿', 'success')
    } catch (e) { showToast('操作失败', 'error') }
  }

  async function handleDemote() {
    if (!selectedId) return
    try {
      const res = await fetch(`/api/books/${bookId}/chapters/${selectedId}/demote`, { method: 'POST' })
      const data = await res.json()
      setChapters(prev => prev.map(c => c.id === selectedId ? { ...c, status: data.status } : c))
      showToast('已降级为草稿', 'success')
    } catch (e) { showToast('操作失败', 'error') }
  }

  async function handleDelete() {
    if (!deleteChapter || !selectedId) return
    try {
      await fetch(`/api/books/${bookId}/chapters/${selectedId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
      setChapters(prev => prev.filter(c => c.id !== selectedId))
      setSelectedId(null)
      setEditTitle('')
      setEditContent('')
      setShowHistory(false)
      setDeleteChapter(false)
      triggerRefresh()
      showToast('章节已删除', 'success')
    } catch (e) {
      showToast('删除失败', 'error')
    }
  }

  function handleCancel() {
    setEditing(false)
    setCommitMsg('')
    const current = chapters.find(c => c.id === selectedId)
    if (current) {
      setEditTitle(current.title || '')
      setEditContent(current.content || '')
    }
  }

  async function loadChapterOutline() {
    if (!selectedId) return
    setOutlineLoading(true)
    setShowChapterOutline(true)
    setShowHistory(false)
    try {
      const [outlineRes, detailRes] = await Promise.all([
        fetch(`/api/books/${bookId}/outline`),
        fetch(`/api/books/${bookId}/detailed-outline`),
      ])
      const outline = await outlineRes.json()
      const detail = await detailRes.json()

      const chIdx = chapters.findIndex(c => c.id === selectedId)
      if (chIdx >= 0 && chIdx < (outline?.chapters || []).length) {
        setChapterOutlineData(outline.chapters[chIdx])
      } else {
        setChapterOutlineData(null)
      }

      if (detail?.chapters) {
        const detailMatch = detail.chapters.find(c => c.chapter_id === selectedId)
        if (detailMatch) {
          setChapterDetailOutlineData(detailMatch)
        } else if (chIdx >= 0 && chIdx < detail.chapters.length) {
          setChapterDetailOutlineData(detail.chapters[chIdx])
        } else {
          setChapterDetailOutlineData(null)
        }
      } else {
        setChapterDetailOutlineData(null)
      }
    } catch (e) { showToast('加载大纲失败', 'error') }
    setOutlineLoading(false)
  }

  async function loadHistory() {
    if (!selectedId) return
    setHistoryLoading(true)
    setShowHistory(true)
    setPreviewVersion(null)
    try {
      const res = await fetch(`/api/books/${bookId}/chapters/${selectedId}/history`)
      const data = await res.json()
      setHistory(data)
    } catch (e) { showToast('加载历史失败', 'error') }
    setHistoryLoading(false)
  }

  async function loadVersionContent(versionId) {
    try {
      const res = await fetch(`/api/books/${bookId}/chapters/${selectedId}/versions/${versionId}`)
      const data = await res.json()
      setPreviewVersion(versionId)
      setPreviewContent(data.content || '')
      setPreviewOriginal(data.original_content || null)
      setPreviewPatches(data.patches_summary || [])
      setDiffMode('after')
    } catch (e) { showToast('加载版本失败', 'error') }
  }

  async function handleRevert(versionId) {
    setRevertVersionId(versionId)
  }

  async function confirmRevert() {
    const versionId = revertVersionId
    try {
      await fetch(`/api/books/${bookId}/chapters/${selectedId}/revert`, {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ version_id: versionId }),
      })
      setPreviewVersion(null)
      setShowHistory(false)
      loadChapters()
      showToast('已回退', 'success')
    } catch (e) {
      showToast('回退失败', 'error')
    }
    setRevertVersionId(null)
  }

  async function handleDeleteVersionConfirm() {
    if (!deleteVersion) return
    try {
      await fetch(`/api/books/${bookId}/chapters/${selectedId}/versions/${deleteVersion}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
      loadHistory()
      if (previewVersion === deleteVersion) setPreviewVersion(null)
      loadChapters()
      showToast('版本已删除', 'success')
    } catch (e) {
      showToast('删除失败', 'error')
    }
    setDeleteVersion(null)
  }

  function closeHistory() {
    setShowHistory(false)
    setPreviewVersion(null)
    setPreviewOriginal(null)
    setPreviewPatches([])
  }

  const wordCount = editContent.replace(/\s/g, '').length
  const lineCount = editContent.split('\n').length
  const currentChapter = chapters.find(c => c.id === selectedId)
  const versionCount = currentChapter?.version_count || 0
  const versionLabel = currentChapter?.version_label || `v${versionCount || 1}`
  const regularChapters = chapters.filter(c => !c.is_extra)
  const extraChapters = chapters.filter(c => c.is_extra)

  if (loading) return <SkeletonSidebar count={8} />

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-56 border-r border-zinc-800 bg-zinc-950/50 flex flex-col shrink-0">
        <div className="p-3 border-b border-zinc-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
              <Icon name="file-text" size={14} /> 章节 ({regularChapters.length})
            </span>
            <div className="relative" ref={createMenuRef}>
              <button
                onClick={() => setShowCreateMenu(!showCreateMenu)}
                className="text-xs text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-0.5 transition-colors flex items-center gap-1"
              >
                <Icon name="plus" size={12} /> 新建
              </button>
              {showCreateMenu && (
                <div className="absolute right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden min-w-28">
                  <button
                    onClick={() => handleCreate(false)}
                    className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors flex items-center gap-2"
                  >
                    <Icon name="file-text" size={12} /> 新建章节
                  </button>
                  <button
                    onClick={() => handleCreate(true)}
                    className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors flex items-center gap-2 border-t border-zinc-700"
                  >
                    <Icon name="star" size={12} /> 新建番外
                  </button>
                </div>
              )}
            </div>
          </div>
          {/* Search input */}
          <div className="relative">
            <Icon name="search" size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={chapterSearch}
              onChange={(e) => setChapterSearch(e.target.value)}
              placeholder="搜索章节..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {(() => {
            const filteredRegular = chapterSearch
              ? regularChapters.filter(c =>
                  c.title.toLowerCase().includes(chapterSearch.toLowerCase()) ||
                  (c.content || '').toLowerCase().includes(chapterSearch.toLowerCase())
                )
              : regularChapters;
            const filteredExtra = chapterSearch
              ? extraChapters.filter(c =>
                  c.title.toLowerCase().includes(chapterSearch.toLowerCase()) ||
                  (c.content || '').toLowerCase().includes(chapterSearch.toLowerCase())
                )
              : extraChapters;

            if (filteredRegular.length === 0 && filteredExtra.length === 0) {
              return (
                <p className="text-xs text-zinc-600 text-center py-8">
                  {chapterSearch ? '未找到匹配的章节' : '暂无章节'}
                </p>
              );
            }

            return (
              <>
                {filteredRegular.map((ch, i) => (
                  <button
                    key={ch.id}
                    onClick={() => selectChapter(ch)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-all relative ${
                      selectedId === ch.id
                        ? 'bg-zinc-700 text-zinc-100 shadow-sm'
                        : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
                    }`}
                  >
                    {selectedId === ch.id && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-r bg-sky-400" />
                    )}
                    <div className="flex items-center gap-1.5">
                      <p className="font-medium truncate flex-1">{ch.title || '无标题'}</p>
                      {recentlyEdited.has(ch.id) && (
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shrink-0" title="刚刚编辑" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-zinc-600 text-[10px] mt-0.5">
                      <span className="text-zinc-700 font-mono">#{i + 1}</span>
                      <span>{(ch.content || '').replace(/\s/g, '').length || 0} 字</span>
                      <span className={`px-1 rounded font-mono ${
                        ch.version_label?.includes('.')
                          ? 'bg-sky-900/50 text-sky-400'
                          : ch.version_count > 1 ? 'bg-zinc-700 text-zinc-300' : 'bg-zinc-800/50 text-zinc-600'
                      }`}>{ch.version_label || `v${ch.version_count || 1}`}</span>
                      {ch.status === 'final' && (
                        <span className="text-[10px] bg-emerald-900/40 text-emerald-400 px-1 rounded ml-1" title="定稿">✓</span>
                      )}
                    </div>
                  </button>
                ))}
                {filteredExtra.length > 0 && (
                  <>
                    <div className="flex items-center gap-2 px-2 py-2 mt-2">
                      <div className="flex-1 h-px bg-zinc-800" />
                      <span className="text-[10px] text-zinc-600 font-medium">番外 ({filteredExtra.length})</span>
                      <div className="flex-1 h-px bg-zinc-800" />
                    </div>
                    {filteredExtra.map((ch, i) => (
                      <button
                        key={ch.id}
                        onClick={() => selectChapter(ch)}
                        className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-all relative ${
                          selectedId === ch.id
                            ? 'bg-violet-900/40 text-zinc-100 border border-violet-700/30 shadow-sm'
                            : 'text-zinc-500 hover:text-zinc-300 hover:bg-violet-950/30'
                        }`}
                      >
                        {selectedId === ch.id && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-r bg-violet-400" />
                        )}
                        <div className="flex items-center gap-1.5">
                          <p className="font-medium truncate flex items-center gap-1.5 flex-1">
                            <span className="text-violet-400 text-[10px]">✦</span>
                            {ch.title || '无标题'}
                          </p>
                          {recentlyEdited.has(ch.id) && (
                            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shrink-0" title="刚刚编辑" />
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-zinc-600 text-[10px] mt-0.5">
                          <span className="text-violet-700 font-mono">番外{i + 1}</span>
                          <span>{(ch.content || '').replace(/\s/g, '').length || 0} 字</span>
                          <span className={`px-1 rounded font-mono ${
                            ch.version_label?.includes('.')
                              ? 'bg-sky-900/50 text-sky-400'
                              : ch.version_count > 1 ? 'bg-zinc-700 text-zinc-300' : 'bg-zinc-800/50 text-zinc-600'
                          }`}>{ch.version_label || `v${ch.version_count || 1}`}</span>
                          {ch.status === 'final' && (
                            <span className="text-[10px] bg-emerald-900/40 text-emerald-400 px-1 rounded ml-1" title="定稿">✓</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </>
                )}
              </>
            );
          })()}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-zinc-600 gap-3">
            <Icon name="file-text" size={32} className="text-zinc-700" />
            <span className="text-sm">选择一个章节或创建新章节</span>
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="flex items-center gap-3 px-6 py-3 border-b border-zinc-800 bg-zinc-950/50 shrink-0">
              {editing ? (
                <>
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
                    placeholder="章节标题"
                  />
                  {saving && (
                    <span className="text-xs text-blue-400 flex items-center gap-1 animate-pulse">
                      <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-ping" />
                      保存中...
                    </span>
                  )}
                  {autoSaved && !saving && (
                    <span className="text-xs text-emerald-500 flex items-center gap-1">
                      <Icon name="check-circle" size={12} />
                      已保存
                    </span>
                  )}
                </>
              ) : (
                <h2 className="flex-1 text-sm font-semibold text-zinc-200">{editTitle || '无标题'}</h2>
              )}

              {!editing && (
                 <>
                   <button
                     onClick={loadChapterOutline}
                     className={`text-xs px-2 py-1 rounded transition-colors flex items-center gap-1 ${
                       showChapterOutline ? 'bg-amber-900/40 text-amber-300' : 'text-zinc-500 hover:text-zinc-300 bg-zinc-800/50 hover:bg-zinc-700'
                     }`}
                   >
                     <Icon name="list" size={12} /> 大纲
                   </button>
                   <button
                     onClick={loadHistory}
                     className={`text-xs px-2 py-1 rounded transition-colors flex items-center gap-1 ${
                       showHistory ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300 bg-zinc-800/50 hover:bg-zinc-700'
                     }`}
                   >
                     <Icon name="clock" size={12} /> {versionLabel} · {versionCount} 版本
                   </button>
                 </>
               )}

              {editing ? (
                <>
                  <input
                    value={commitMsg}
                    onChange={(e) => setCommitMsg(e.target.value)}
                    className="w-36 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
                    placeholder="版本说明（可选）"
                  />
                  <button onClick={handleCancel}
                    className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg transition-colors">取消</button>
                  <button onClick={() => { setShowFindReplace(v => !v); setTimeout(() => findInputRef.current?.focus(), 0) }}
                    className={`text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1 ${
                      showFindReplace ? 'bg-blue-900/40 text-blue-300' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700'
                    }`}
                    title="查找替换 (Ctrl+F)">
                    <Icon name="search" size={12} /> 查找
                  </button>
                  <button onClick={handleSave}
                    disabled={saving}
                    className="text-xs bg-zinc-200 text-zinc-900 rounded-lg px-4 py-1.5 font-medium hover:bg-white transition-colors disabled:opacity-40 flex items-center gap-1">
                    <Icon name="save" size={12} /> {saving ? '保存中...' : '保存'}
                  </button>
                </>
              ) : (
                 <>
                   {currentChapter?.status === 'final' ? (
                     <button onClick={handleDemote}
                       className="text-xs text-emerald-500 hover:text-amber-400 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1 bg-emerald-900/20"
                       title="降级为草稿">
                       <Icon name="check-circle" size={12} /> 定稿
                     </button>
                   ) : (
                     <button onClick={handlePromote}
                       className="text-xs text-zinc-500 hover:text-emerald-400 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1"
                       title="提升为定稿">
                       <Icon name="check-circle" size={12} /> 定稿
                     </button>
                   )}
                   <button onClick={() => setEditing(true)}
                     className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1">
                     <Icon name="edit" size={12} /> 编辑
                   </button>
                   <button onClick={() => setDeleteChapter(true)}
                     className="text-xs text-zinc-600 hover:text-red-400 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1">
                     <Icon name="trash" size={12} /> 删除
                   </button>
                   <button
                     onClick={handleExport}
                     className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1">
                     <Icon name="download" size={12} /> 导出
                   </button>
                 </>
              )}
            </div>

            {/* Tab Bar */}
            {tabs.length > 0 && (
              <div className="flex items-center border-b border-zinc-800 bg-zinc-950/30 shrink-0 overflow-x-auto">
                {tabs.map(tab => {
                  const ch = chapters.find(c => c.id === tab.id)
                  const displayTitle = ch?.title || tab.title || '无标题'
                  return (
                    <button
                      key={tab.id}
                      onClick={() => {
                        if (tab.id !== selectedId) {
                          const chapter = chapters.find(c => c.id === tab.id)
                          if (chapter) selectChapter(chapter)
                          else setActiveTab(tab.id)
                        }
                      }}
                      className={`group flex items-center gap-1 px-3 py-1.5 text-xs whitespace-nowrap border-r border-zinc-800 transition-colors ${
                        tab.id === selectedId
                          ? 'bg-zinc-800 text-zinc-200 border-t-2 border-t-sky-400 -mt-[1px]'
                          : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
                      }`}
                    >
                      <span className="max-w-32 truncate">{displayTitle}</span>
                      <span
                        onClick={(e) => {
                          e.stopPropagation()
                          closeTab(tab.id)
                          if (tab.id === selectedId && tabs.length > 1) {
                            const nextTab = tabs.find(t => t.id !== tab.id)
                            if (nextTab) {
                              const nextCh = chapters.find(c => c.id === nextTab.id)
                              if (nextCh) selectChapter(nextCh)
                            }
                          }
                        }}
                        className="ml-1 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-zinc-600 text-zinc-500 hover:text-zinc-200 transition-all"
                        title="关闭"
                      >
                        <Icon name="x" size={10} />
                      </span>
                    </button>
                  )
                })}
              </div>
            )}

            {/* Chapter Outline Panel */}
            {showChapterOutline && (
              <div className="border-b border-zinc-800 bg-zinc-900/80 max-h-80 overflow-y-auto">
                <div className="flex items-center justify-between px-6 py-2 border-b border-zinc-800/50">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-zinc-400">
                      本章大纲: {chapters.find(c => c.id === selectedId)?.title || ''}
                    </span>
                    <div className="flex gap-0.5">
                      <button
                        onClick={() => setOutlineViewMode('outline')}
                        className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                          outlineViewMode === 'outline' ? 'bg-amber-900/40 text-amber-300' : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        大纲
                      </button>
                      <button
                        onClick={() => setOutlineViewMode('detailed')}
                        className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                          outlineViewMode === 'detailed' ? 'bg-blue-900/40 text-blue-300' : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        细纲
                      </button>
                    </div>
                  </div>
                  <button onClick={() => setShowChapterOutline(false)} className="text-xs text-zinc-600 hover:text-zinc-300 flex items-center gap-1">
                    <Icon name="x" size={12} /> 关闭
                  </button>
                </div>
                {outlineLoading ? (
                  <div className="p-4 text-xs text-zinc-600 text-center">加载中...</div>
                ) : outlineViewMode === 'detailed' ? (
                  <div className="p-4 space-y-3">
                    {chapterDetailOutlineData ? (
                      <>
                        {chapterDetailOutlineData.chapter_function && (
                          <div className="bg-blue-900/20 border border-blue-900/30 rounded-lg p-3">
                            <div className="text-[10px] text-blue-400 mb-1 font-semibold">章节功能</div>
                            <p className="text-xs text-blue-200">{chapterDetailOutlineData.chapter_function}</p>
                          </div>
                        )}
                        {chapterDetailOutlineData.plot_chain && chapterDetailOutlineData.plot_chain.length > 0 && (
                          <div className="space-y-1.5">
                            <div className="text-[10px] text-zinc-500 font-semibold">剧情骨架</div>
                            {chapterDetailOutlineData.plot_chain.map((event, i) => (
                              <div key={i} className="flex gap-2 text-xs">
                                <span className="text-zinc-600 shrink-0 font-mono">{i + 1}.</span>
                                <span className="text-zinc-300">{event}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="text-xs text-zinc-600 text-center py-4">
                        尚无细纲。使用 AI 的"生成细纲"功能创建。
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="p-4 space-y-3">
                    {chapterOutlineData ? (
                      <>
                        {chapterOutlineData.synopsis && (
                          <div>
                            <div className="text-[10px] text-zinc-500 mb-1 font-semibold">概要</div>
                            <p className="text-xs text-zinc-300 leading-relaxed">{chapterOutlineData.synopsis}</p>
                          </div>
                        )}
                        {chapterOutlineData.key_events && chapterOutlineData.key_events.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-[10px] text-zinc-500 font-semibold">关键事件</div>
                            <div className="flex flex-wrap gap-1">
                              {chapterOutlineData.key_events.map((ev, i) => (
                                <span key={i} className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">
                                  {ev}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {chapterOutlineData.characters && chapterOutlineData.characters.length > 0 && (
                          <div>
                            <div className="text-[10px] text-zinc-500 mb-1 font-semibold">出场角色</div>
                            <div className="flex flex-wrap gap-1">
                              {chapterOutlineData.characters.map((char, i) => (
                                <span key={i} className="text-[10px] bg-violet-900/30 text-violet-300 px-2 py-0.5 rounded">
                                  {char}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {chapterOutlineData.turning_point && (
                          <div className="bg-amber-900/20 border border-amber-900/30 rounded-lg p-3">
                            <div className="text-[10px] text-amber-400 mb-1 font-semibold">转折点</div>
                            <p className="text-xs text-amber-200">{chapterOutlineData.turning_point}</p>
                          </div>
                        )}
                        {chapterOutlineData.notes && (
                          <div>
                            <div className="text-[10px] text-zinc-500 mb-1 font-semibold">备注</div>
                            <p className="text-xs text-zinc-400">{chapterOutlineData.notes}</p>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="text-xs text-zinc-600 text-center py-4">
                        本章尚无大纲。使用 AI 的"生成大纲"功能创建。
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Version History Panel */}
            {showHistory && (
              <div className="border-b border-zinc-800 bg-zinc-900/80 max-h-64 overflow-y-auto">
                <div className="flex items-center justify-between px-6 py-2 border-b border-zinc-800/50">
                  <span className="text-xs font-semibold text-zinc-400">版本历史</span>
                  <button onClick={closeHistory} className="text-xs text-zinc-600 hover:text-zinc-300 flex items-center gap-1">
                    <Icon name="x" size={12} /> 关闭
                  </button>
                </div>
                {historyLoading ? (
                  <div className="p-4 text-xs text-zinc-600 text-center">加载中...</div>
                ) : (
                  <div className="divide-y divide-zinc-800/50">
                    {history.map(v => (
                      <div
                        key={v.id}
                        className={`px-6 py-2 flex items-center gap-3 text-xs transition-colors cursor-pointer hover:bg-zinc-800/50 ${
                          previewVersion === v.id ? 'bg-zinc-800/80' : ''
                        }`}
                        onClick={() => loadVersionContent(v.id)}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className={`shrink-0 text-[10px] px-1.5 rounded font-mono ${
                              v.version_label?.includes('.')
                                ? 'bg-blue-900/50 text-blue-400'
                                : 'bg-zinc-700 text-zinc-300'
                            }`}>
                              {v.version_label || `v${history.length}`}
                            </span>
                            <span className="text-zinc-300 font-medium truncate">{v.message || '未命名版本'}</span>
                            {v.is_current && (
                              <span className="shrink-0 text-[10px] bg-emerald-900/50 text-emerald-400 px-1.5 rounded">当前</span>
                            )}
                            {v.has_diff && (
                              <span className="shrink-0 text-[10px] bg-orange-900/50 text-orange-400 px-1.5 rounded">局部</span>
                            )}
                          </div>
                          <div className="text-zinc-600 text-[10px] mt-0.5">
                            {v.timestamp?.slice(0, 16).replace('T', ' ')} · {v.word_count} 字
                          </div>
                        </div>
                        {!v.is_current && (
                          <div className="flex gap-1 shrink-0">
                            <button
                              onClick={(e) => { e.stopPropagation(); handleRevert(v.id) }}
                              className="text-[10px] text-zinc-500 hover:text-amber-400 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors"
                            >
                              回退
                            </button>
                            {history.length > 1 && (
                              <button
                                onClick={(e) => { e.stopPropagation(); setDeleteVersion(v.id) }}
                                className="text-[10px] text-zinc-600 hover:text-red-400 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors"
                              >
                                删除
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Editor / Viewer / Version Preview */}
            <div className="flex-1 overflow-y-auto">
              {previewVersion ? (
                <div className="p-6">
                  <div className="mb-4 flex items-center gap-3 flex-wrap">
                    <span className="text-xs bg-amber-900/30 text-amber-400 px-2 py-1 rounded">
                      预览: {history.find(h => h.id === previewVersion)?.version_label || ''} {history.find(h => h.id === previewVersion)?.message || previewVersion.slice(0, 12)}
                    </span>
                    <button
                      onClick={() => { setPreviewVersion(null); setPreviewOriginal(null); setPreviewPatches([]); }}
                      className="text-xs text-zinc-500 hover:text-zinc-300"
                    >
                      返回当前版本
                    </button>
                    {previewOriginal && (
                      <div className="flex gap-1 ml-auto">
                        {['before', 'diff', 'after'].map(m => (
                          <button
                            key={m}
                            onClick={() => setDiffMode(m)}
                            className={`text-[10px] px-2 py-1 rounded transition-colors ${
                              diffMode === m ? 'bg-zinc-600 text-zinc-100' : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
                            }`}
                          >
                            {m === 'before' ? '修改前' : m === 'diff' ? '对比' : '修改后'}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {previewPatches.length > 0 && (
                    <div className="mb-4 bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-400 space-y-1">
                      <div className="text-zinc-500 font-medium mb-1">本次修改 ({previewPatches.length} 处):</div>
                      {previewPatches.map((p, i) => (
                        <div key={i} className="flex gap-2">
                          <span className="text-zinc-600 shrink-0">{i+1}.</span>
                          {p.op === 'replace' && (
                            <>
                              <span className="text-red-400 line-through bg-red-900/20 px-1 rounded">{p.before?.slice(0, 60)}</span>
                              <span className="text-zinc-600">→</span>
                              <span className="text-green-400 bg-green-900/20 px-1 rounded">{p.after?.slice(0, 60)}</span>
                            </>
                          )}
                          {p.op === 'delete' && (
                            <><span className="text-red-400">删除:</span> <span className="line-through text-zinc-500">{p.deleted?.slice(0, 60)}</span></>
                          )}
                          {(p.op === 'insert_after' || p.op === 'insert_before') && (
                            <><span className="text-blue-400">{p.op === 'insert_before' ? '前插' : '后插'}:</span> <span className="text-blue-300 bg-blue-900/20 px-1 rounded">{p.inserted?.slice(0, 60)}</span></>
                          )}
                          {p.op === 'append' && (
                            <><span className="text-purple-400">追加:</span> <span className="text-purple-300 bg-purple-900/20 px-1 rounded">{p.appended?.slice(0, 60)}</span></>
                          )}
                          {p.op === 'prepend' && (
                            <><span className="text-purple-400">前插:</span> <span className="text-purple-300 bg-purple-900/20 px-1 rounded">{p.prepended?.slice(0, 60)}</span></>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {diffMode === 'diff' && previewOriginal ? (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-[10px] text-zinc-600 mb-2 font-semibold">修改前</div>
                        <div className="text-zinc-500 text-sm leading-loose whitespace-pre-wrap font-[serif] opacity-80">
                          {previewOriginal.split('\n').map((p, i) => (
                            p.trim() ? <p key={i} className="mb-3 indent-8">{p}</p> : <br key={i} />
                          ))}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-zinc-600 mb-2 font-semibold">修改后</div>
                        <div className="text-zinc-300 text-sm leading-loose whitespace-pre-wrap font-[serif]">
                          {previewContent.split('\n').map((p, i) => (
                            p.trim() ? <p key={i} className="mb-3 indent-8">{p}</p> : <br key={i} />
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-zinc-400 text-sm leading-loose whitespace-pre-wrap font-[serif] max-w-3xl mx-auto opacity-80">
                      {(diffMode === 'before' && previewOriginal ? previewOriginal : previewContent).split('\n').map((p, i) => (
                        p.trim() ? <p key={i} className="mb-4 indent-8">{p}</p> : <br key={i} />
                      ))}
                    </div>
                  )}
                </div>
                ) : editing ? (
                <div className="flex-1 flex flex-col overflow-hidden">
                  {/* Find-Replace Panel */}
                  {showFindReplace && (
                    <div className="border-b border-zinc-800 bg-zinc-900/70 px-6 py-2 shrink-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Find row */}
                        <div className="flex items-center gap-2 flex-1 min-w-[300px]">
                          <div className="relative flex-1">
                            <input
                              ref={findInputRef}
                              type="text"
                              value={findText}
                              onChange={(e) => setFindText(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) doFindPrev(); else doFindNext() }
                              }}
                              placeholder="查找内容..."
                              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
                            />
                          </div>
                          <span className="text-[10px] text-zinc-500 tabular-nums shrink-0 min-w-[60px]">
                            {matches.length === 0
                              ? (findText ? '无匹配' : '')
                              : `${matchIndex + 1} / ${matches.length}`
                            }
                          </span>
                          <button onClick={doFindPrev} disabled={matches.length === 0}
                            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors disabled:opacity-30"
                            title="上一处 (Shift+F3)">
                            <Icon name="arrow-up" size={12} />
                          </button>
                          <button onClick={doFindNext} disabled={matches.length === 0}
                            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors disabled:opacity-30"
                            title="下一处 (F3)">
                            <Icon name="arrow-down" size={12} />
                          </button>
                          <button onClick={() => setShowFindReplace(false)}
                            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors"
                            title="关闭 (Esc)">
                            <Icon name="x" size={12} />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        {/* Replace row */}
                        <div className="flex items-center gap-2 flex-1 min-w-[300px]">
                          <input
                            type="text"
                            value={replaceText}
                            onChange={(e) => setReplaceText(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') { e.preventDefault(); doReplace() }
                            }}
                            placeholder="替换为..."
                            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
                          />
                          <button onClick={doReplace} disabled={matches.length === 0}
                            className="text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
                            title="替换当前">
                            替换
                          </button>
                          <button onClick={doReplaceAll} disabled={matches.length === 0}
                            className="text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
                            title="全部替换">
                            全部替换
                          </button>
                          <label className="flex items-center gap-1.5 text-[10px] text-zinc-500 select-none cursor-pointer ml-auto shrink-0">
                            <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)}
                              className="accent-sky-500" />
                            区分大小写
                          </label>
                        </div>
                      </div>
                    </div>
                  )}

                  <MarkdownEditor
                    value={editContent}
                    onChange={setEditContent}
                    className="flex-1"
                    editorRef={editorInstanceRef}
                    status={currentChapter?.status}
                  />
                </div>
              ) : (
                <div className="p-6">
                  {editContent ? (
                    <div className="text-zinc-300 text-sm leading-loose whitespace-pre-wrap font-[serif] max-w-3xl mx-auto">
                      {editContent.split('\n').map((p, i) => (
                        p.trim() ? <p key={i} className="mb-4 indent-8">{p}</p> : <br key={i} />
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-64 text-zinc-600 text-sm gap-2">
                      <Icon name="file-text" size={32} className="text-zinc-700" />
                      <p>章节内容为空</p>
                      <p className="text-xs">点击"编辑"手动写作，或切换到对话 Tab 用 AI 帮你写</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Status bar */}
            <div className="px-6 py-1.5 border-t border-zinc-800 bg-zinc-950/50 flex items-center gap-4 text-[10px] text-zinc-600 shrink-0">
              <span>{wordCount} 字</span>
              <span>{lineCount} 行</span>
              {currentChapter?.status && (
                <span className={currentChapter.status === 'final' ? 'text-emerald-500' : 'text-zinc-500'}>
                  {currentChapter.status === 'final' ? '定稿' : '草稿'}
                </span>
              )}
              {editing && saving && (
                <span className="text-blue-400">保存中...</span>
              )}
              {editing && showFindReplace && (
                <span className="ml-auto text-zinc-700">Esc 关闭 · F3 下一处 · Shift+F3 上一处 · Enter 替换 · Ctrl+S 保存</span>
              )}
              {editing && !showFindReplace && (
                <span className="ml-auto text-zinc-700">Ctrl+F 查找替换 · Ctrl+S 保存</span>
              )}
            </div>
          </>
        )}
      </div>

      <ConfirmModal
        open={deleteChapter}
        title="删除章节"
        message="确定删除本章？所有版本将一并删除，此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteChapter(false)}
      />

      <ConfirmModal
        open={!!deleteVersion}
        title="删除版本"
        message="确定删除此版本？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDeleteVersionConfirm}
        onCancel={() => setDeleteVersion(null)}
      />

      <ConfirmModal
        open={!!revertVersionId}
        title="回退版本"
        message="确定回退到此版本？当前内容不会丢失，仍可在历史中找回。"
        confirmText="回退"
        danger
        onConfirm={confirmRevert}
        onCancel={() => setRevertVersionId(null)}
      />
    </div>
  )
}

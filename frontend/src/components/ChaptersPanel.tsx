import { useState, useEffect, useRef, useCallback } from 'react'
import ConfirmModal from './ui/ConfirmModal'
import Icon from './ui/Icon'
import { showToast } from './ui/toast-utils'
import { SkeletonSidebar } from './ui/Skeleton'
import { useRefreshKey, triggerRefresh } from "../store"
import MarkdownEditor from './editor/MarkdownEditor'
import WordCountGoal from './editor/WordCountGoal'
import { useAutoSave } from '../hooks/useAutoSave'
import { useTabs, openTab, closeTab, setActiveTab, clearTabsForBook } from "../stores/tabStore"
import { api } from '../api'
import ChapterHistoryPanel from './ChapterHistoryPanel'
import ImpactPanel from './ImpactPanel'
import ChapterFindReplace from './ChapterFindReplace'
import ChapterOutlinePanel from './ChapterOutlinePanel'
import ChapterSidebar from './ChapterSidebar'

export default function ChaptersPanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [chapters, setChapters] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const tabs = useTabs()
  const currentBookTabs = tabs.filter(t => t.bookId === bookId)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [showImpact, setShowImpact] = useState(false)
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
  const [revertVersionId, setRevertVersionId] = useState(null)
  const [showCreateMenu, setShowCreateMenu] = useState(false)
  const [chapterSearch, setChapterSearch] = useState('')
  const [volumes, setVolumes] = useState<{id: string; title: string; chapters?: {id: string}[]; story_line?: string}[]>([])
  const createMenuRef = useRef(null)
  const [recentlyEdited] = useState(new Set())
  const editorInstanceRef = useRef(null)

  // ── Drag-and-drop state ──
  const [dragChapterId, setDragChapterId] = useState<string | null>(null)
  const [dragOverChapterId, setDragOverChapterId] = useState<string | null>(null)
  // 码字体验增强
  const [focusMode, setFocusMode] = useState(false)
  const [wordCountTarget, setWordCountTarget] = useState(() => {
    try { return parseInt(localStorage.getItem(`wc_target_${bookId}`) || '3000', 10) } catch { return 3000 }
  })
  const [typewriterMode, setTypewriterMode] = useState(false)

  // Find-replace state
  const [showFindReplace, setShowFindReplace] = useState(false)
  const [findText, setFindText] = useState('')
  const [replaceText, setReplaceText] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [matches, setMatches] = useState([])
  const findInputRef = useRef(null)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadChapters(); loadVolumes() }, [bookId, refreshKey])

  // 切换书籍时清除旧书的标签页
  useEffect(() => {
    clearTabsForBook(bookId)
  }, [bookId])

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

  // 字数目标持久化
  useEffect(() => {
    localStorage.setItem(`wc_target_${bookId}`, String(wordCountTarget))
  }, [wordCountTarget, bookId])

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
      // Ctrl+Alt+↑/↓: 章节导航
      if ((e.ctrlKey || e.metaKey) && e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
        e.preventDefault()
        const currentIdx = chapters.findIndex(c => c.id === selectedId)
        if (currentIdx === -1) return
        const nextIdx = e.key === 'ArrowUp' ? currentIdx - 1 : currentIdx + 1
        if (nextIdx >= 0 && nextIdx < chapters.length) {
          selectChapter(chapters[nextIdx])
        }
      }
      // Ctrl+Shift+F: 专注模式
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'f') {
        e.preventDefault()
        setFocusMode(v => !v)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [editing, showFindReplace, chapters, selectedId])

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
      const data = await api.getChapters(bookId) as any[]
      const arr = Array.isArray(data) ? data : []
      setChapters(arr)
      if (!selectedId && arr.length > 0) {
        setSelectedId(data[0].id)
        setEditTitle(data[0].title || '')
        setEditContent(data[0].content || '')
      } else if (selectedId) {
        const current = arr.find((c: any) => c.id === selectedId)
        if (current) {
          setEditTitle(current.title || '')
          setEditContent(current.content || '')
        }
      }
    } catch (e) { showToast('加载章节失败', 'error') }
    setLoading(false)
  }

  async function loadVolumes() {
    try {
      const data = await api.getVolumes(bookId)
      setVolumes((data.volumes as any[]) || [])
    } catch (e) { /* silent */ }
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
      const newCh = await api.createChapter(bookId, { title, content: '', is_extra: isExtra })
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
      await doSaveContent()
      // Update local state instead of reloading from server — avoids
      // skeleton flash and keeps editContent in sync for next edit.
      setChapters(prev => prev.map(c =>
        c.id === selectedId
          ? { ...c, title: editTitle, content: editContent, updatedAt: new Date().toISOString(), version_count: (c.version_count || 0) + 1 }
          : c
      ))
      setEditing(false)
      setCommitMsg('')
      triggerRefresh()
      showToast('已保存', 'success')
    } catch (e) {
      showToast('保存失败', 'error')
    }
    setSaving(false)
  }

  // 核心保存逻辑（供手动保存和自动保存共用）
  const doSaveContent = useCallback(async () => {
    if (!selectedId) return
    await api.updateChapter(bookId, selectedId, {
      title: editTitle,
      content: editContent,
      message: commitMsg || '自动保存',
    })
  }, [bookId, selectedId, editTitle, editContent, commitMsg])

  // 自动保存
  const autoSave = useAutoSave({
    saveFn: doSaveContent,
    interval: 30000,
    enabled: editing,
  })

  async function handleExport() {
    try {
      const book = await api.getBook(bookId)

      const res = await api.exportBook(bookId)
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
      const data = await api.promoteChapter(bookId, selectedId)
      setChapters(prev => prev.map(c => c.id === selectedId ? { ...c, status: data.status } : c))
      showToast('已提升为定稿', 'success')
    } catch (e) { showToast('操作失败', 'error') }
  }

  async function handleDemote() {
    if (!selectedId) return
    try {
      const data = await api.demoteChapter(bookId, selectedId)
      setChapters(prev => prev.map(c => c.id === selectedId ? { ...c, status: data.status } : c))
      showToast('已降级为草稿', 'success')
    } catch (e) { showToast('操作失败', 'error') }
  }

  async function handleDelete() {
    if (!deleteChapter || !selectedId) return
    try {
      await api.deleteChapter(bookId, selectedId)
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

  // ── Drag-and-drop handlers ──
  function handleDragStart(e: React.DragEvent, chId: string) {
    setDragChapterId(chId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', chId)
  }

  function handleDragOver(e: React.DragEvent, chId: string) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverChapterId !== chId) setDragOverChapterId(chId)
  }

  function handleDragLeave() {
    setDragOverChapterId(null)
  }

  async function handleDrop(e: React.DragEvent, targetId: string) {
    e.preventDefault()
    const sourceId = dragChapterId
    setDragChapterId(null)
    setDragOverChapterId(null)
    if (!sourceId || sourceId === targetId) return

    const newChapters = [...chapters]
    const srcIdx = newChapters.findIndex(c => c.id === sourceId)
    const tgtIdx = newChapters.findIndex(c => c.id === targetId)
    if (srcIdx === -1 || tgtIdx === -1) return

    // Move the dragged chapter to the target position
    const [moved] = newChapters.splice(srcIdx, 1)
    newChapters.splice(tgtIdx, 0, moved)
    setChapters(newChapters)

    // Persist new order
    try {
      await api.reorderChapters(bookId, newChapters.map(c => c.id))
      triggerRefresh()
    } catch (e) {
      showToast('排序保存失败', 'error')
      loadChapters() // revert
    }
  }

  function handleDragEnd() {
    setDragChapterId(null)
    setDragOverChapterId(null)
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
      const [outline, detail] = await Promise.all([
        api.getOutline(bookId) as Promise<any>,
        api.getDetailedOutline(bookId) as Promise<any>,
      ])

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
      const data = await api.getChapterHistory(bookId, selectedId)
      setHistory(data)
    } catch (e) { showToast('加载历史失败', 'error') }
    setHistoryLoading(false)
  }

  async function loadVersionContent(versionId) {
    try {
      const data = await api.getChapterVersion(bookId, selectedId, versionId) as any
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
      await api.revertChapter(bookId, selectedId, versionId)
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
      await api.deleteChapterVersion(bookId, selectedId, deleteVersion)
      setPreviewVersion(null)
      loadHistory()
      loadChapters()
      showToast('版本已删除', 'success')
    } catch (e) {
      showToast('删除失败', 'error')
    }
    setDeleteVersion(null)
  }

  function handleVersionSelect(versionId: string) {
    loadVersionContent(versionId)
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
      <ChapterSidebar
        regularChapters={regularChapters}
        extraChapters={extraChapters}
        volumes={volumes}
        chapterSearch={chapterSearch}
        setChapterSearch={setChapterSearch}
        selectedId={selectedId}
        selectChapter={selectChapter}
        handleCreate={handleCreate}
        showCreateMenu={showCreateMenu}
        setShowCreateMenu={setShowCreateMenu}
        createMenuRef={createMenuRef}
        focusMode={focusMode}
        recentlyEdited={recentlyEdited}
        dragChapterId={dragChapterId}
        dragOverChapterId={dragOverChapterId}
        handleDragStart={handleDragStart}
        handleDragOver={handleDragOver}
        handleDragLeave={handleDragLeave}
        handleDrop={handleDrop}
        handleDragEnd={handleDragEnd}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedId ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-600/20 to-violet-600/20 border border-zinc-800 flex items-center justify-center">
              <Icon name="file-text" size={28} className="text-sky-400" />
            </div>
            <span className="text-sm text-zinc-500">选择一个章节或创建新章节</span>
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
                  {/* 自动保存状态 */}
                  {saving && (
                    <span className="text-xs text-blue-400 flex items-center gap-1 shrink-0">
                      <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-ping" />
                      保存中...
                    </span>
                  )}
                  {autoSave.isSaving && !saving && (
                    <span className="text-[10px] text-zinc-500 shrink-0">自动保存中...</span>
                  )}
                  {!saving && !autoSave.isSaving && autoSave.isDirty && (
                    <span className="text-[10px] text-amber-500 shrink-0" title="有未保存的更改">● 未保存</span>
                  )}
                  {!saving && !autoSave.isSaving && !autoSave.isDirty && (
                    <span className="text-[10px] text-emerald-600 shrink-0">已保存</span>
                  )}
                  {/* 专注模式 / 打字机模式 */}
                  <button
                    onClick={() => setFocusMode(v => !v)}
                    className={`text-xs px-2 py-1 rounded transition-colors shrink-0 ${focusMode ? 'bg-amber-900/40 text-amber-300' : 'text-zinc-500 hover:text-zinc-300'}`}
                    title="专注模式 (Ctrl+Shift+F)"
                  >
                    <Icon name="maximize" size={12} />
                  </button>
                  <button
                    onClick={() => setTypewriterMode(v => !v)}
                    className={`text-xs px-2 py-1 rounded transition-colors shrink-0 ${typewriterMode ? 'bg-sky-900/40 text-sky-300' : 'text-zinc-500 hover:text-zinc-300'}`}
                    title="打字机模式"
                  >
                    <Icon name="type" size={13} />
                  </button>
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
                  {/* 影响分析：改章可能波及下游时按需触发（S45） */}
                  <button
                    onClick={() => setShowImpact(true)}
                    className="text-xs px-2.5 py-1.5 rounded-lg font-medium transition-colors bg-amber-900/30 text-amber-300 border border-amber-800/40 hover:bg-amber-800/40 flex items-center gap-1"
                    title="影响分析：修改本章（涉及实体）会影响哪些下游章节"
                  >
                    <Icon name="zap" size={12} /> 影响
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
            {!focusMode && currentBookTabs.length > 0 && (
              <div className="flex items-center border-b border-zinc-800 bg-zinc-950/30 shrink-0 overflow-x-auto">
                {currentBookTabs.map(tab => {
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
                          if (tab.id === selectedId && currentBookTabs.length > 1) {
                            const nextTab = currentBookTabs.find(t => t.id !== tab.id)
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
            {!focusMode && showChapterOutline && (
              <ChapterOutlinePanel
                chapterTitle={chapters.find(c => c.id === selectedId)?.title || ''}
                viewMode={outlineViewMode}
                setViewMode={setOutlineViewMode}
                loading={outlineLoading}
                outline={chapterOutlineData}
                detailedOutline={chapterDetailOutlineData}
                onClose={() => setShowChapterOutline(false)}
              />
            )}

            {/* Version History Panel */}
            {!focusMode && showHistory && (
              <ChapterHistoryPanel
                bookId={bookId}
                chapterId={selectedId}
                onClose={closeHistory}
                onRevert={closeHistory}
                onVersionSelect={handleVersionSelect}
              />
            )}

            {/* 影响分析（改章按需触发，非独立页面） */}
            {showImpact && (
              <div className="absolute inset-0 z-30 flex items-start justify-end">
                <div className="absolute inset-0 bg-black/40" onClick={() => setShowImpact(false)} />
                <div className="relative w-96 h-full bg-zinc-900 border-l border-zinc-800 shadow-2xl overflow-y-auto">
                  <ImpactPanel
                    open
                    onClose={() => setShowImpact(false)}
                    embedded
                    initialOrder={chapters.find((c: any) => c.id === selectedId)?.order_index}
                  />
                </div>
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
                    <ChapterFindReplace
                      findText={findText}
                      setFindText={setFindText}
                      replaceText={replaceText}
                      setReplaceText={setReplaceText}
                      caseSensitive={caseSensitive}
                      setCaseSensitive={setCaseSensitive}
                      matches={matches}
                      matchIndex={matchIndex}
                      onFindNext={doFindNext}
                      onFindPrev={doFindPrev}
                      onReplace={doReplace}
                      onReplaceAll={doReplaceAll}
                      onClose={() => setShowFindReplace(false)}
                      findInputRef={findInputRef}
                    />
                  )}

                  <MarkdownEditor
                    value={editContent}
                    onChange={setEditContent}
                    className="flex-1"
                    editorRef={editorInstanceRef}
                    status={currentChapter?.status}
                    onDirty={autoSave.markDirty}
                    typewriterMode={typewriterMode}
                    showWordCount
                    toolbarRight={
                      <WordCountGoal
                        current={wordCount}
                        target={wordCountTarget}
                        onTargetChange={setWordCountTarget}
                      />
                    }
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
                <span className="ml-auto text-zinc-700">Ctrl+F 查找 · Ctrl+S 保存 · Ctrl+Alt+↑↓ 切换章节 · Ctrl+Shift+F 专注</span>
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

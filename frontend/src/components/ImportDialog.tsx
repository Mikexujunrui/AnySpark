import { useState, useRef, useCallback } from 'react'
import { showToast } from './ui/toast-utils'
import Icon from './ui/Icon'
import { triggerRefresh } from '../store'
import { uploadDocument, detectChapters, importChapters, batchExtractKnowledge } from '../api'

const STEPS = ['upload', 'review', 'import']

export default function ImportDialog({ bookId, sessionId, onClose }) {
  const [step, setStep] = useState('upload')
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [docId, setDocId] = useState(null)
  const [detectResult, setDetectResult] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [extractKnowledge, setExtractKnowledge] = useState(false)
  const [volumeName, setVolumeName] = useState('')
  const fileInputRef = useRef(null)
  const dropRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFile = useCallback(async (f) => {
    if (!f) return
    if (f.size > 50 * 1024 * 1024) {
      showToast('文件不能超过 50MB', 'error')
      return
    }
    setFile(f)
    setUploading(true)
    try {
      const data: any = await uploadDocument(bookId, f, sessionId)
      setDocId(data.docId || data.id)
      const docIdVal = data.docId || data.id
      setUploading(false)
      setDetecting(true)
      const detectData: any = await detectChapters(bookId, docIdVal, sessionId)
      setDetectResult(detectData)
      setStep('review')
    } catch (e) {
      showToast('上传失败', 'error')
    }
    setUploading(false)
    setDetecting(false)
  }, [bookId, sessionId])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f && (f.name.endsWith('.txt') || f.name.endsWith('.md'))) {
      handleFile(f)
    } else {
      showToast('仅支持 .txt 和 .md 文件', 'error')
    }
  }, [handleFile])

  const handleImport = useCallback(async () => {
    if (!docId || !detectResult) return
    setImporting(true)
    try {
      const body = {
        pattern: detectResult.pattern || '',
        titles: detectResult.chapters?.map(c => c.title) || detectResult.titles || [],
        confirm: true,
        extract_knowledge: extractKnowledge,
        volume_name: volumeName,
      }
      const data: any = await importChapters(bookId, docId, body, sessionId)
      setImportResult(data)

      // Batch extract if requested
      if (extractKnowledge && data.chapter_ids?.length > 0) {
        try {
          await batchExtractKnowledge(bookId, docId, data.chapter_ids)
        } catch (e) { /* silent */ }
      }

      triggerRefresh()
      setStep('import')
    } catch (e) {
      showToast('导入失败', 'error')
    }
    setImporting(false)
  }, [bookId, sessionId, docId, detectResult, extractKnowledge, volumeName])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Icon name="upload" size={18} className="text-sky-400" />
            <h2 className="text-sm font-semibold text-zinc-200">导入小说</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <Icon name="x" size={18} />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center px-6 py-3 border-b border-zinc-800 gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                step === s ? 'bg-sky-600 text-white' :
                STEPS.indexOf(step) > i ? 'bg-emerald-600 text-white' :
                'bg-zinc-800 text-zinc-600'
              }`}>
                {STEPS.indexOf(step) > i ? '✓' : i + 1}
              </span>
              <span className={`text-[10px] ${step === s ? 'text-zinc-200' : 'text-zinc-600'}`}>
                {{ upload: '上传', review: '预览', import: '导入' }[s]}
              </span>
              {i < STEPS.length - 1 && <div className="w-6 h-px bg-zinc-700" />}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Step 1: Upload */}
          {step === 'upload' && (
            <div
              ref={dropRef}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                dragOver ? 'border-sky-500 bg-sky-500/5' : 'border-zinc-700 hover:border-zinc-600'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md"
                onChange={(e) => handleFile(e.target.files[0])}
                className="hidden"
              />
              {uploading || detecting ? (
                <div className="flex flex-col items-center gap-3">
                  <span className="w-8 h-8 border-2 border-zinc-500 border-t-sky-400 rounded-full animate-spin" />
                  <p className="text-sm text-zinc-400">{uploading ? '上传中...' : '正在检测章节结构...'}</p>
                  <p className="text-xs text-zinc-600">{file?.name}</p>
                </div>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="cursor-pointer flex flex-col items-center gap-3"
                >
                  <Icon name="upload" size={32} className="text-zinc-600" />
                  <p className="text-sm text-zinc-400">
                    拖拽 TXT 文件到此处，或<span className="text-sky-400">点击选择</span>
                  </p>
                  <p className="text-xs text-zinc-600">支持 .txt .md，最大 50MB</p>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Review */}
          {step === 'review' && detectResult && (
            <div className="space-y-4">
              <div className="bg-zinc-800/50 rounded-lg p-3 text-xs">
                <span className="text-zinc-500">检测方法: </span>
                <span className="text-zinc-300">{detectResult.method === 'regex' ? '正则匹配' : 'AI识别'}</span>
                {detectResult.pattern && (
                  <>
                    <span className="text-zinc-500 ml-3">模式: </span>
                    <code className="text-sky-400 bg-zinc-800 px-1 rounded">{detectResult.pattern}</code>
                  </>
                )}
                <span className="text-zinc-500 ml-3">总字数: {detectResult.total_chars?.toLocaleString() || '?'}</span>
              </div>

              {detectResult.message && (
                <div className="bg-amber-900/20 border border-amber-900/30 rounded-lg p-3 text-xs text-amber-300">
                  {detectResult.message}
                </div>
              )}

              <div className="text-[10px] text-zinc-500 font-semibold">
                章节预览 (共 {detectResult.chapters?.length || 0} 章)
              </div>

              <div className="max-h-64 overflow-y-auto space-y-1 border border-zinc-800 rounded-lg">
                {detectResult.chapters?.map((ch, i) => (
                  <div key={i} className="flex items-start gap-3 px-3 py-2 hover:bg-zinc-800/50 text-xs border-b border-zinc-800/50 last:border-0">
                    <span className="text-zinc-600 shrink-0 font-mono w-5 text-right">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-zinc-300 font-medium truncate">{ch.title || '无标题'}</p>
                      {ch.preview && <p className="text-zinc-600 truncate mt-0.5">{ch.preview}</p>}
                    </div>
                  </div>
                ))}
              </div>

              {/* Options */}
              <div className="space-y-2 pt-2">
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={extractKnowledge}
                    onChange={(e) => setExtractKnowledge(e.target.checked)}
                    className="accent-sky-500"
                  />
                  导入后自动提取知识（角色、地点等）
                </label>
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">导入到分卷（可选）</label>
                  <input
                    type="text"
                    value={volumeName}
                    onChange={(e) => setVolumeName(e.target.value)}
                    placeholder="留空则作为独立章节"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Result */}
          {step === 'import' && importResult && (
            <div className="flex flex-col items-center justify-center py-8 gap-4">
              <div className="w-12 h-12 rounded-full bg-emerald-900/30 flex items-center justify-center">
                <Icon name="check-circle" size={24} className="text-emerald-400" />
              </div>
              <p className="text-sm text-zinc-300">{importResult.message}</p>
              {importResult.preview && (
                <p className="text-xs text-zinc-500 text-center max-w-sm">{importResult.preview}</p>
              )}
              <button
                onClick={onClose}
                className="mt-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg text-sm transition-colors"
              >
                完成
              </button>
            </div>
          )}
        </div>

        {/* Footer / Actions */}
        {step === 'review' && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-zinc-800 bg-zinc-900/80">
            <button onClick={() => { setStep('upload'); setFile(null); setDocId(null); setDetectResult(null) }}
              className="text-xs text-zinc-500 hover:text-zinc-300">
              重新选择文件
            </button>
            <button
              onClick={handleImport}
              disabled={importing}
              className="bg-sky-600 hover:bg-sky-500 disabled:bg-zinc-700 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {importing ? '导入中...' : `导入 ${detectResult?.chapters?.length || 0} 个章节`}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

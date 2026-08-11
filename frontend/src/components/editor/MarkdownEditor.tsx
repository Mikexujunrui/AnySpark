import { useState, useCallback, useRef, useEffect } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Icon from '../ui/Icon'

/**
 * 将 TipTap 文档转为纯文本（用于兼容后端存储）
 */
function tipTapToPlainText(editor) {
  if (!editor) return ''
  const doc = editor.state.doc
  const lines = []
  doc.forEach(node => {
    if (node.type.name === 'paragraph') {
      if (node.textContent.trim() === '' && node.childCount === 0) {
        lines.push('') // 空行
      } else {
        lines.push(node.textContent)
      }
    } else if (node.type.name === 'heading') {
      const prefix = '#'.repeat(node.attrs.level || 1)
      lines.push(prefix + ' ' + node.textContent)
    } else if (node.type.name === 'bulletList') {
      node.forEach(item => {
        if (item.type.name === 'listItem') {
          const text = item.textContent
          lines.push('- ' + text)
        }
      })
    } else if (node.type.name === 'orderedList') {
      node.forEach((item, i) => {
        if (item.type.name === 'listItem') {
          lines.push((i + 1) + '. ' + item.textContent)
        }
      })
    } else if (node.type.name === 'blockquote') {
      node.forEach(child => {
        if (child.type.name === 'paragraph') {
          lines.push('> ' + child.textContent)
        }
      })
    } else if (node.type.name === 'codeBlock') {
      lines.push('```\n' + node.textContent + '\n```')
    } else if (node.type.name === 'horizontalRule') {
      lines.push('---')
    }
  })
  return lines.join('\n')
}

/**
 * 将纯文本转为 TipTap 文档 JSON
 */
function plainTextToDoc(text) {
  if (!text) return { type: 'doc', content: [{ type: 'paragraph' }] }

  const blocks = text.split('\n\n')
  const content = []

  for (const block of blocks) {
    if (block.trim() === '') {
      content.push({ type: 'paragraph' })
      continue
    }

    // 代码块
    if (block.startsWith('```')) {
      const code = block.replace(/^```\n?/, '').replace(/\n?```$/, '')
      content.push({
        type: 'codeBlock',
        content: [{ type: 'text', text: code }],
      })
      continue
    }

    // 水平线
    if (block.trim() === '---') {
      content.push({ type: 'horizontalRule' })
      continue
    }

    // 引用块
    if (block.startsWith('> ')) {
      const quoteText = block.replace(/^> /gm, '')
      const parts = quoteText.split('\n')
      const quoteContent = []
      parts.forEach((part, i) => {
        if (i > 0) quoteContent.push({ type: 'hardBreak' })
        quoteContent.push({ type: 'text', text: part })
      })
      content.push({
        type: 'blockquote',
        content: [{ type: 'paragraph', content: quoteContent }],
      })
      continue
    }

    // 无序列表（连续以 - 或 * 开头的行）
    if (block.split('\n').every(line => /^[-*]\s/.test(line.trim()))) {
      const items = block.split('\n').map(line => ({
        type: 'listItem',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: line.replace(/^[-*]\s/, '') }] }],
      }))
      content.push({ type: 'bulletList', content: items })
      continue
    }

    // 有序列表（连续以 1. 2. 等开头的行）
    if (block.split('\n').every(line => /^\d+\.\s/.test(line.trim()))) {
      const items = block.split('\n').map(line => ({
        type: 'listItem',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: line.replace(/^\d+\.\s/, '') }] }],
      }))
      content.push({ type: 'orderedList', content: items })
      continue
    }

    // 标题
    if (/^#{1,6}\s/.test(block)) {
      const match = block.match(/^(#{1,6})\s(.+)/)
      if (match) {
        content.push({
          type: 'heading',
          attrs: { level: match[1].length },
          content: [{ type: 'text', text: match[2] }],
        })
        continue
      }
    }

    // 普通段落 - 单换行 = hardBreak
    const parts = block.split('\n')
    const paraContent = []
    parts.forEach((part, i) => {
      if (i > 0) paraContent.push({ type: 'hardBreak' })
      paraContent.push({ type: 'text', text: part || '' })
    })
    content.push({ type: 'paragraph', content: paraContent })
  }

  if (content.length === 0) {
    content.push({ type: 'paragraph' })
  }

  return { type: 'doc', content }
}

export default function MarkdownEditor({
  value = '',
  onChange,
  placeholder = '开始写作，或切换到对话 Tab 让 AI 帮你写...',
  className = '',
  readOnly = false,
  editorRef, // 外部 ref，用于获取 editor 实例
  status,    // "draft" | "final" — shown as indicator
  onDirty,   // 内容变更时回调（用于自动保存脏标记）
  typewriterMode = false,  // 打字机模式：光标固定在编辑器中央
  showWordCount = false,   // 工具栏显示实时字数
  toolbarRight,            // 工具栏右侧额外内容（如字数目标）
}) {
  const [mode, setMode] = useState('wysiwyg') // 'wysiwyg' | 'plain'
  const [plainText, setPlainText] = useState(value)
  const isInternalChange = useRef(false)
  const textareaRef = useRef(null)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Placeholder.configure({ placeholder }),
    ],
    content: plainTextToDoc(value),
    editable: !readOnly,
    onUpdate: ({ editor }) => {
      if (isInternalChange.current) return
      const text = tipTapToPlainText(editor)
      setPlainText(text)
      onChange?.(text)
      onDirty?.()
    },
  })

  // 暴露 editor 实例给外部
  useEffect(() => {
    if (editorRef && editor) {
      editorRef.current = editor
    }
  }, [editor, editorRef])

  // 外部 value 变化时同步
  useEffect(() => {
    if (!editor) return
    const currentText = tipTapToPlainText(editor)
    if (value !== currentText) {
      isInternalChange.current = true
      const doc = plainTextToDoc(value)
      editor.commands.setContent(doc)
      setPlainText(value)
      isInternalChange.current = false
    }
  }, [value, editor])

  // 切换到纯文本时更新 textarea
  useEffect(() => {
    if (mode === 'plain') {
      setPlainText(tipTapToPlainText(editor))
    }
  }, [mode])

  // 打字机模式：光标居中滚动
  useEffect(() => {
    if (!typewriterMode || !editor) return
    const el = editor.view.dom.closest('.tiptap-editor') as HTMLElement
    if (!el) return
    const onSelectionChange = () => {
      const { from } = editor.state.selection
      const coords = editor.view.coordsAtPos(from)
      if (!coords) return
      const rect = el.getBoundingClientRect()
      const cursorY = coords.top - rect.top + el.scrollTop
      const targetScroll = cursorY - rect.height * 0.35
      if (Math.abs(el.scrollTop - targetScroll) > 60) {
        el.scrollTo({ top: targetScroll, behavior: 'smooth' })
      }
    }
    editor.on('selectionUpdate', onSelectionChange)
    return () => { editor.off('selectionUpdate', onSelectionChange) }
  }, [typewriterMode, editor])

  // 实时字数
  const wordCount = plainText.replace(/\s/g, '').length

  // 纯文本模式下的 onChange
  const handlePlainChange = useCallback((e) => {
    const text = e.target.value
    setPlainText(text)
    onChange?.(text)
  }, [onChange])

  // 切换模式
  const toggleMode = useCallback(() => {
    if (mode === 'wysiwyg') {
      const text = tipTapToPlainText(editor)
      setPlainText(text)
      setMode('plain')
    } else {
      isInternalChange.current = true
      const doc = plainTextToDoc(plainText)
      editor?.commands.setContent(doc)
      onChange?.(plainText)
      isInternalChange.current = false
      setMode('wysiwyg')
    }
  }, [mode, editor, plainText, onChange])

  if (!editor) {
    return (
      <div className={`flex items-center justify-center text-zinc-600 ${className}`}>
        编辑器加载中...
      </div>
    )
  }

  return (
    <div className={`flex flex-col ${className}`}>
      {/* 模式切换 + 格式工具栏 */}
      {!readOnly && (
        <div className="flex items-center gap-1 px-3 py-1.5 border-b border-zinc-800 bg-zinc-900/60 shrink-0">
          {status && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded mr-2 font-medium ${
              status === 'final' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-zinc-700 text-zinc-400'
            }`}>
              {status === 'final' ? '定稿' : '草稿'}
            </span>
          )}
          {mode === 'wysiwyg' ? (
            <>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBold().run()}
                active={editor.isActive('bold')}
                title="加粗 (Ctrl+B)"
              >
                <strong>B</strong>
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleItalic().run()}
                active={editor.isActive('italic')}
                title="斜体 (Ctrl+I)"
              >
                <em>I</em>
              </ToolbarButton>
              <div className="w-px h-4 bg-zinc-700 mx-0.5" />
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                active={editor.isActive('heading', { level: 2 })}
                title="标题 H2"
              >
                H2
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                active={editor.isActive('heading', { level: 3 })}
                title="标题 H3"
              >
                H3
              </ToolbarButton>
              <div className="w-px h-4 bg-zinc-700 mx-0.5" />
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBulletList().run()}
                active={editor.isActive('bulletList')}
                title="无序列表"
              >
                <Icon name="list" size={14} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                active={editor.isActive('orderedList')}
                title="有序列表"
              >
                <Icon name="list" size={14} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBlockquote().run()}
                active={editor.isActive('blockquote')}
                title="引用"
              >
                <span className="text-lg leading-none">"</span>
              </ToolbarButton>
              <div className="w-px h-4 bg-zinc-700 mx-0.5" />
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                active={editor.isActive('codeBlock')}
                title="代码块"
              >
                {'</>'}
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().setHorizontalRule().run()}
                title="分割线"
              >
                —
              </ToolbarButton>
              <div className="flex-1" />
              {showWordCount && (
                <span className="text-[10px] text-zinc-500 tabular-nums">{wordCount.toLocaleString()} 字</span>
              )}
              {toolbarRight}
            </>
          ) : null}
          <button
            onClick={toggleMode}
            className="text-[10px] text-zinc-600 hover:text-zinc-400 px-2 py-1 rounded transition-colors ml-auto"
            title={mode === 'wysiwyg' ? '切换到纯文本模式' : '切换到所见即所得模式'}
          >
            {mode === 'wysiwyg' ? '纯文本' : '所见即所得'}
          </button>
        </div>
      )}

      {/* 编辑器主体 */}
      <div className="flex-1 overflow-y-auto tiptap-editor">
        {mode === 'wysiwyg' ? (
          <div className="h-full">
            <EditorContent
              editor={editor}
            />
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={plainText}
            onChange={handlePlainChange}
            className="w-full h-full bg-zinc-900 text-zinc-200 text-sm leading-relaxed p-6 resize-none focus:outline-none font-[serif]"
            placeholder={placeholder}
            readOnly={readOnly}
          />
        )}
      </div>
    </div>
  )
}

function ToolbarButton({ onClick, active = false, title, children }: { onClick: () => void; active?: boolean; title: string; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-1.5 py-1 rounded transition-colors ${
        active
          ? 'bg-sky-900/40 text-sky-300'
          : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'
      }`}
      title={title}
      type="button"
    >
      {children}
    </button>
  )
}

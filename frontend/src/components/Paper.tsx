import { useEffect, useRef, useCallback, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useChapterStore } from "../stores/chapterStore";
import { exportBook, exportChapter } from "../api/export";

export default function Paper() {
  const selectedChapter = useChapterStore((s) => s.selectedChapter);
  const saving = useChapterStore((s) => s.saving);
  const updateChapterContent = useChapterStore((s) => s.updateChapterContent);
  const [showExportMenu, setShowExportMenu] = useState(false);

  // 防抖定时器
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 防抖保存
  const debouncedSave = useCallback(
    (content: string) => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        updateChapterContent(content).catch(() => {
          // 保存失败静默处理，用户可重试
        });
      }, 1500);
    },
    [updateChapterContent]
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: "选择左侧章节，或直接在此编辑内容...",
      }),
    ],
    editable: !!selectedChapter, // 有选中章节才可编辑
    content: "",
    editorProps: {
      attributes: {
        class: "prose prose-invert max-w-none focus:outline-none min-h-full",
      },
    },
    onUpdate: ({ editor }) => {
      // 每次编辑触发防抖保存
      const html = editor.getHTML();
      debouncedSave(html);
    },
  });

  // 选中章节变化时更新编辑器内容
  useEffect(() => {
    // 切换章节时取消未完成的保存
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }

    if (editor && selectedChapter) {
      editor.commands.setContent(selectedChapter.content || "");
      editor.setEditable(true);
    } else if (editor) {
      editor.commands.setContent("");
      editor.setEditable(false);
    }
  }, [editor, selectedChapter?.id]);

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col bg-zinc-900 border-b border-zinc-800 overflow-y-auto relative">
      {/* 章节标题 + 保存状态 */}
      {selectedChapter && (
        <div className="px-6 pt-4 pb-2 border-b border-zinc-800/50 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-200">
              {selectedChapter.title}
            </h2>
            <p className="text-xs text-zinc-600 mt-1">
              第 {selectedChapter.order_index + 1} 章 · {selectedChapter.content?.length || 0} 字
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* 导出按钮 */}
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded border border-zinc-700"
              >
                导出 ▼
              </button>
              {showExportMenu && (
                <div className="absolute right-0 top-full mt-1 w-40 bg-zinc-800 border border-zinc-700 rounded shadow-lg z-10">
                  <button
                    onClick={() => {
                      exportChapter(selectedChapter.id, "txt");
                      setShowExportMenu(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    当前章节 TXT
                  </button>
                  <button
                    onClick={() => {
                      exportChapter(selectedChapter.id, "md");
                      setShowExportMenu(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    当前章节 MD
                  </button>
                  <div className="border-t border-zinc-700 my-1"></div>
                  <button
                    onClick={() => {
                      exportBook("txt");
                      setShowExportMenu(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    全书 TXT
                  </button>
                  <button
                    onClick={() => {
                      exportBook("md");
                      setShowExportMenu(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    全书 MD
                  </button>
                  <button
                    onClick={() => {
                      exportBook("epub");
                      setShowExportMenu(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    全书 EPUB
                  </button>
                </div>
              )}
            </div>
            {/* 保存状态指示 */}
            <span className={`text-xs ${saving ? "text-yellow-500" : "text-zinc-600"}`}>
              {saving ? "保存中..." : "已保存"}
            </span>
          </div>
        </div>
      )}

      {/* 编辑器 */}
      <div
        className="px-6 py-4 min-h-[200px]"
        style={{ fontFamily: "'Noto Serif SC', 'Source Han Serif CN', serif", lineHeight: "1.9" }}
      >
        <EditorContent editor={editor} />
      </div>

      {/* 空状态 */}
      {!selectedChapter && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-zinc-700 text-sm">选择章节或开始对话</p>
        </div>
      )}
    </div>
  );
}

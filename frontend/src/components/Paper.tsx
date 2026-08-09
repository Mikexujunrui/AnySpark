import { useEffect, useRef, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useChapterStore } from "../stores/chapterStore";

export default function Paper() {
  const selectedChapter = useChapterStore((s) => s.selectedChapter);
  const saving = useChapterStore((s) => s.saving);
  const updateChapterContent = useChapterStore((s) => s.updateChapterContent);

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
    <div className="flex-1 bg-zinc-900 border-b border-zinc-800 overflow-y-auto relative">
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
          {/* 保存状态指示 */}
          <span className={`text-xs ${saving ? "text-yellow-500" : "text-zinc-600"}`}>
            {saving ? "保存中..." : "已保存"}
          </span>
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

/** Renders the appropriate sub-panel based on tabKey.
 *  壳面板签名 {bookId}；V4 工具面板签名 {open, onClose}——内嵌时 open=true。
 *  ChatPanel 常驻挂载（保持 SSE 连接），display:none 控制可见性。
 */

import ChatPanel from '../ChatPanel'
import ExploreView from '../ExploreView'
import ChaptersPanel from '../ChaptersPanel'
import KnowledgePanel from '../KnowledgePanel'
import OutlinePanel from '../OutlinePanel'
import SearchPanel from '../SearchPanel'
import ReviewPanel from '../ReviewPanel'
import MaterialsPanel from '../MaterialsPanel'
import StoryTreeView from '../StoryTreeView'
import WorkflowPanel from '../WorkflowPanel'
import PlotPanel from '../PlotPanel'
import SkillPanel from '../SkillPanel'

// V4 工具面板（open/onClose 签名）
import BriefPanel from '../BriefPanel'
import CodexPanel from '../CodexPanel'
import BiasPanel from '../BiasPanel'
import BatchPanel from '../BatchPanel'
import TemplatePanel from '../TemplatePanel'
import ToolsPanel from '../ToolsPanel'
import PlayPanel from '../PlayPanel'
import RolePanel from '../RolePanel'
import DimsPanel from '../DimsPanel'
import ImpactPanel from '../ImpactPanel'
import LibraryPanel from '../LibraryPanel'
import UploadPanel from '../UploadPanel'

export default function PanelHost({ panelKey, bookId, sessionId, onPanelClose }: { panelKey: string; bookId: string; sessionId: string; onPanelClose?: () => void }) {
  // ChatPanel 常驻挂载以保持 SSE 连接
  const chatVisible = panelKey === 'chat'

  return (
    <div className="h-full min-h-0 relative">
      <div style={{ display: chatVisible ? undefined : 'none' }} className="h-full absolute inset-0">
        <ChatPanel bookId={bookId} sessionId={sessionId} autoModeEnabled={false} transformSignal={0} />
      </div>

      {panelKey === 'chapters' && <div className="h-full min-h-0 flex flex-col"><ChaptersPanel bookId={bookId} /></div>}
      {panelKey === 'explore' && <div className="h-full min-h-0 flex flex-col"><ExploreView /></div>}
      {panelKey === 'knowledge' && <div className="h-full min-h-0 flex flex-col"><KnowledgePanel bookId={bookId} /></div>}
      {panelKey === 'outline' && <div className="h-full min-h-0 flex flex-col"><OutlinePanel bookId={bookId} /></div>}
      {panelKey === 'foreshadows' && <div className="h-full min-h-0 flex flex-col"><PlotPanel bookId={bookId} /></div>}
      {panelKey === 'styles' && <div className="h-full min-h-0 flex flex-col"><SkillPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'storytree' && <div className="h-full min-h-0 flex flex-col"><StoryTreeView /></div>}
      {panelKey === 'workflow' && <div className="h-full min-h-0 flex flex-col"><WorkflowPanel /></div>}
      {panelKey === 'search' && <div className="h-full min-h-0 flex flex-col"><SearchPanel bookId={bookId} /></div>}
      {panelKey === 'review' && <div className="h-full min-h-0 flex flex-col"><ReviewPanel bookId={bookId} /></div>}
      {panelKey === 'materials' && <div className="h-full min-h-0 flex flex-col"><MaterialsPanel bookId={bookId} /></div>}
      {panelKey === 'references' && <div className="h-full min-h-0 flex flex-col"><LibraryPanel bookId={bookId} /></div>}

      {/* V4 工具面板（open/onClose 签名 → 内嵌常显） */}
      {panelKey === 'brief' && <div className="h-full min-h-0 flex flex-col"><BriefPanel open embedded onClose={onPanelClose || (() => {})} bookId={bookId} /></div>}
      {panelKey === 'bias' && <div className="h-full min-h-0 flex flex-col"><BiasPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'batch' && <div className="h-full min-h-0 flex flex-col"><BatchPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'templates' && <div className="h-full min-h-0 flex flex-col"><TemplatePanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'tools' && <div className="h-full min-h-0 flex flex-col"><ToolsPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'play' && <div className="h-full min-h-0 flex flex-col"><PlayPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'dims' && <div className="h-full min-h-0 flex flex-col"><DimsPanel open embedded onClose={onPanelClose || (() => {})} /></div>}
      {panelKey === 'codex' && <div className="h-full min-h-0 flex flex-col"><CodexPanel /></div>}
      {panelKey === 'upload' && <div className="h-full min-h-0 flex flex-col"><UploadPanel open embedded onClose={onPanelClose || (() => {})} bookId={bookId} /></div>}
    </div>
  )
}

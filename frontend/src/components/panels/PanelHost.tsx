/** Renders the appropriate sub-panel based on tabKey.
 *  壳面板签名 {bookId}；V4 工具面板签名 {open, onClose}——内嵌时 open=true。
 *  ChatPanel 常驻挂载（保持 SSE 连接），display:none 控制可见性。
 */

import ChatPanel from '../ChatPanel'
import ChaptersPanel from '../ChaptersPanel'
import KnowledgePanel from '../KnowledgePanel'
import OutlinePanel from '../OutlinePanel'
import SearchPanel from '../SearchPanel'
import ReviewPanel from '../ReviewPanel'
import MaterialsPanel from '../MaterialsPanel'

// V4 工具面板（open/onClose 签名）
import BriefPanel from '../BriefPanel'
import BiasPanel from '../BiasPanel'
import BatchPanel from '../BatchPanel'
import TemplatePanel from '../TemplatePanel'
import ToolsPanel from '../ToolsPanel'
import PlayPanel from '../PlayPanel'
import RolePanel from '../RolePanel'
import DimsPanel from '../DimsPanel'
import ImpactPanel from '../ImpactPanel'
import UploadPanel from '../UploadPanel'

export default function PanelHost({ panelKey, bookId, sessionId }: { panelKey: string; bookId: string; sessionId: string }) {
  // ChatPanel 常驻挂载以保持 SSE 连接
  const chatVisible = panelKey === 'chat'

  return (
    <div className="h-full relative">
      <div style={{ display: chatVisible ? undefined : 'none' }} className="h-full absolute inset-0">
        <ChatPanel bookId={bookId} sessionId={sessionId} autoModeEnabled={false} transformSignal={0} />
      </div>

      {panelKey === 'chapters' && <div className="h-full"><ChaptersPanel bookId={bookId} /></div>}
      {panelKey === 'knowledge' && <div className="h-full"><KnowledgePanel bookId={bookId} /></div>}
      {panelKey === 'outline' && <div className="h-full"><OutlinePanel bookId={bookId} /></div>}
      {panelKey === 'search' && <div className="h-full"><SearchPanel bookId={bookId} /></div>}
      {panelKey === 'review' && <div className="h-full"><ReviewPanel bookId={bookId} /></div>}
      {panelKey === 'materials' && <div className="h-full"><MaterialsPanel /></div>}

      {/* V4 工具面板（open/onClose 签名 → 内嵌常显） */}
      {panelKey === 'brief' && <div className="h-full"><BriefPanel open onClose={() => {}} /></div>}
      {panelKey === 'bias' && <div className="h-full"><BiasPanel open onClose={() => {}} /></div>}
      {panelKey === 'batch' && <div className="h-full"><BatchPanel open onClose={() => {}} /></div>}
      {panelKey === 'templates' && <div className="h-full"><TemplatePanel open onClose={() => {}} /></div>}
      {panelKey === 'tools' && <div className="h-full"><ToolsPanel open onClose={() => {}} /></div>}
      {panelKey === 'play' && <div className="h-full"><PlayPanel open onClose={() => {}} /></div>}
      {panelKey === 'role' && <div className="h-full"><RolePanel open onClose={() => {}} /></div>}
      {panelKey === 'dims' && <div className="h-full"><DimsPanel open onClose={() => {}} /></div>}
      {panelKey === 'impact' && <div className="h-full"><ImpactPanel open onClose={() => {}} /></div>}
      {panelKey === 'upload' && <div className="h-full"><UploadPanel open onClose={() => {}} /></div>}
    </div>
  )
}

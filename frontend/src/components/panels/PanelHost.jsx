/** Renders the appropriate sub-panel based on tabKey. ChatPanel stays mounted via display:none. */

import ChatPanel from '../ChatPanel.jsx'
import ChaptersPanel from '../ChaptersPanel.jsx'
import CharacterGallery from '../CharacterGallery.jsx'
import WorldMap from '../WorldMap.jsx'
import WorldbuildingPanel from '../WorldbuildingPanel.jsx'
import KnowledgePanel from '../KnowledgePanel.jsx'
import OutlinePanel from '../OutlinePanel.jsx'
import TimelineView from '../TimelineView.jsx'
import ForeshadowBoard from '../ForeshadowBoard.jsx'
import ReferenceBooksPanel from '../ReferenceBooksPanel.jsx'
import StylesPanel from '../StylesPanel.jsx'
import FileTree from '../FileTree.jsx'
import SearchPanel from '../SearchPanel.jsx'
import InteractivePanel from '../InteractivePanel.jsx'
import WorkflowView from '../WorkflowView.jsx'
import ReviewPanel from '../ReviewPanel.jsx'

export default function PanelHost({ panelKey, bookId, sessionId, autoModeEnabled, transformSignal }) {
  // ChatPanel always stays mounted to preserve SSE connection
  const chatVisible = panelKey === 'chat'

  return (
    <div className="h-full relative">
      {/* ChatPanel: always mounted, controlled via visibility */}
      <div
        style={{ display: chatVisible ? undefined : 'none' }}
        className="h-full absolute inset-0"
      >
        <ChatPanel bookId={bookId} sessionId={sessionId} autoModeEnabled={autoModeEnabled} transformSignal={transformSignal} />
      </div>

      {/* Other panels: conditionally rendered */}
      {panelKey === 'chapters' && <div className="h-full"><ChaptersPanel bookId={bookId} /></div>}
      {panelKey === 'interactive' && <div className="h-full"><InteractivePanel bookId={bookId} /></div>}
      {panelKey === 'characters' && <div className="h-full"><CharacterGallery bookId={bookId} /></div>}
      {panelKey === 'map' && <div className="h-full"><WorldMap bookId={bookId} /></div>}
      {panelKey === 'worldbuilding' && <div className="h-full"><WorldbuildingPanel bookId={bookId} /></div>}
      {panelKey === 'knowledge' && <div className="h-full"><KnowledgePanel bookId={bookId} /></div>}
      {panelKey === 'outline' && <div className="h-full"><OutlinePanel bookId={bookId} /></div>}
      {panelKey === 'timeline' && <div className="h-full"><TimelineView bookId={bookId} /></div>}
      {panelKey === 'foreshadows' && <div className="h-full"><ForeshadowBoard bookId={bookId} /></div>}
      {panelKey === 'references' && <div className="h-full"><ReferenceBooksPanel bookId={bookId} /></div>}
      {panelKey === 'styles' && <div className="h-full"><StylesPanel bookId={bookId} /></div>}
      {panelKey === 'files' && <div className="h-full"><FileTree bookId={bookId} /></div>}
      {panelKey === 'search' && <div className="h-full"><SearchPanel bookId={bookId} /></div>}
      {panelKey === 'workflow' && <div className="h-full"><WorkflowView bookId={bookId} /></div>}
      {panelKey === 'review' && <div className="h-full"><ReviewPanel bookId={bookId} /></div>}
    </div>
  )
}

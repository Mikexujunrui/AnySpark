import { useState, useEffect } from 'react'
import Icon from '../../../components/ui/Icon'
import type { SimMode, OpeningMode, CharacterInfo, TimelineEventInfo, SessionInfo } from '../types'
import { getSimCharacters, getSimSessions, deleteSimSession } from '../api'
import { setSimSessions, setCurrentSimId } from '../stores/simulation-store'

interface SimulationSetupProps {
  bookId: string
  mode: SimMode
  openingMode: OpeningMode
  selectedChars: string[]
  povCharId: string | null
  setting: string
  condition: string
  selectedTimelineEvent: string | null
  userSupplement: string
  timelineEvents: TimelineEventInfo[]
  characters: CharacterInfo[]
  sessions: SessionInfo[]
  loading: boolean
  error: string | null
  onModeChange: (m: SimMode) => void
  onOpeningModeChange: (m: OpeningMode) => void
  onSelectedCharsChange: (ids: string[]) => void
  onPovCharIdChange: (id: string | null) => void
  onSettingChange: (s: string) => void
  onConditionChange: (s: string) => void
  onTimelineEventChange: (id: string | null) => void
  onUserSupplementChange: (s: string) => void
  onStart: () => void
  onContinue: (simId: string) => void
  onDeleteSession: (simId: string) => void
}

const MODE_DESCRIPTIONS: Record<SimMode, { title: string; desc: string; icon: string }> = {
  character_pov: {
    title: '角色主视角',
    desc: '选定一个角色，以该角色的视角进行推演。你控制该角色的行动和决策，感受角色的内心世界。',
    icon: 'eye',
  },
  narrator_pov: {
    title: '叙事者主视角',
    desc: '以全知视角设定客观条件，让多个角色在给定情境中自然反应，你从宏观观察剧情发展。',
    icon: 'globe',
  },
}

export default function SimulationSetup({
  bookId,
  mode, openingMode,
  selectedChars, povCharId,
  setting, condition,
  selectedTimelineEvent, userSupplement,
  timelineEvents, characters, sessions,
  loading, error,
  onModeChange, onOpeningModeChange,
  onSelectedCharsChange, onPovCharIdChange,
  onSettingChange, onConditionChange,
  onTimelineEventChange, onUserSupplementChange,
  onStart, onContinue, onDeleteSession,
}: SimulationSetupProps) {
  const canStart = mode === 'character_pov'
    ? Boolean(povCharId && (setting.trim() || selectedTimelineEvent))
    : Boolean(selectedChars.length > 0 && (setting.trim() || selectedTimelineEvent))

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Mode Selection */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">推演模式</h2>
        <div className="grid grid-cols-2 gap-3">
          {(Object.entries(MODE_DESCRIPTIONS) as [SimMode, typeof MODE_DESCRIPTIONS['character_pov']][]).map(([key, info]) => (
            <button
              key={key}
              onClick={() => onModeChange(key)}
              className={`text-left p-4 rounded-xl border transition-all ${
                mode === key
                  ? 'border-purple-500/50 bg-purple-900/20 ring-1 ring-purple-500/30'
                  : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon name={info.icon} size={16} className={mode === key ? 'text-purple-400' : 'text-zinc-500'} />
                <span className={`text-sm font-medium ${mode === key ? 'text-purple-300' : 'text-zinc-300'}`}>
                  {info.title}
                </span>
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed">{info.desc}</p>
            </button>
          ))}
        </div>
      </section>

      {/* Opening Mode */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">开场方式</h2>
        <div className="flex gap-2">
          <button
            onClick={() => onOpeningModeChange('free')}
            className={`flex-1 p-3 rounded-xl border text-center transition-all ${
              openingMode === 'free'
                ? 'border-purple-500/50 bg-purple-900/20 ring-1 ring-purple-500/30'
                : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'
            }`}
          >
            <Icon name="edit" size={14} className={openingMode === 'free' ? 'text-purple-400' : 'text-zinc-500'} />
            <span className={`block text-xs mt-1 ${openingMode === 'free' ? 'text-purple-300' : 'text-zinc-400'}`}>
              自由开局
            </span>
          </button>
          <button
            onClick={() => onOpeningModeChange('timeline')}
            className={`flex-1 p-3 rounded-xl border text-center transition-all ${
              openingMode === 'timeline'
                ? 'border-purple-500/50 bg-purple-900/20 ring-1 ring-purple-500/30'
                : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'
            }`}
          >
            <Icon name="clock" size={14} className={openingMode === 'timeline' ? 'text-purple-400' : 'text-zinc-500'} />
            <span className={`block text-xs mt-1 ${openingMode === 'timeline' ? 'text-purple-300' : 'text-zinc-400'}`}>
              从正文事件开始
            </span>
          </button>
        </div>
      </section>

      {/* Setting / Timeline Event */}
      {openingMode === 'free' ? (
        <section>
          <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">开局设定</h2>
          <textarea
            value={setting}
            onChange={e => onSettingChange(e.target.value)}
            placeholder="描述推演的开局场景...&#10;例如：张三在城门口遇到了多年未见的旧友李四，两人相视无言..."
            rows={4}
            className="w-full bg-zinc-800/50 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500/50 resize-none leading-relaxed"
          />
        </section>
      ) : (
        <section>
          <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">从正文事件开始</h2>
          {timelineEvents.length === 0 ? (
            <p className="text-xs text-zinc-600">暂无时间线事件</p>
          ) : (
            <select
              value={selectedTimelineEvent || ''}
              onChange={e => onTimelineEventChange(e.target.value || null)}
              className="w-full bg-zinc-800/50 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-purple-500/50"
            >
              <option value="">选择事件...</option>
              {timelineEvents.map(ev => (
                <option key={ev.id} value={ev.id}>
                  {ev.label} {ev.time_label ? `(${ev.time_label})` : ''}
                </option>
              ))}
            </select>
          )}
        </section>
      )}

      {/* User Supplement */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">
          {openingMode === 'timeline' ? '对事件的补充说明' : '补充说明（可选）'}
        </h2>
        <textarea
          value={userSupplement}
          onChange={e => onUserSupplementChange(e.target.value)}
          placeholder={openingMode === 'timeline'
            ? '对选定事件的补充，如"此时角色内心已有动摇"...'
            : '对开局设定的补充，如"天气恶劣，气氛紧张"...'
          }
          rows={2}
          className="w-full bg-zinc-800/50 border border-zinc-700 rounded-xl px-4 py-3 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500/50 resize-none"
        />
      </section>

      {/* Character Selection */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">
          {mode === 'character_pov' ? '选择主视角角色' : '选择参与角色'}
        </h2>
        {characters.length === 0 ? (
          <p className="text-xs text-zinc-600">请先在知识库中创建角色</p>
        ) : (
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {characters.map(char => {
              const isPov = povCharId === char.id
              const isSelected = selectedChars.includes(char.id)
              return (
                <button
                  key={char.id}
                  onClick={() => {
                    if (mode === 'character_pov') {
                      onPovCharIdChange(isPov ? null : char.id)
                      onSelectedCharsChange(
                        isPov
                          ? selectedChars.filter(id => id !== char.id)
                          : [...selectedChars.filter(id => id !== povCharId), char.id]
                      )
                    } else {
                      onSelectedCharsChange(
                        isSelected
                          ? selectedChars.filter(id => id !== char.id)
                          : [...selectedChars, char.id]
                      )
                    }
                  }}
                  className={`w-full text-left px-4 py-2.5 rounded-lg border transition-all flex items-center gap-3 ${
                    mode === 'character_pov' && isPov
                      ? 'border-purple-500/50 bg-purple-900/20 ring-1 ring-purple-500/30'
                      : isSelected
                        ? 'border-purple-500/30 bg-purple-900/10'
                        : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full shrink-0 ${
                    mode === 'character_pov' && isPov ? 'bg-purple-400' : isSelected ? 'bg-purple-400/60' : 'bg-zinc-700'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-300 truncate">{char.name}</p>
                    {char.description && (
                      <p className="text-[10px] text-zinc-600 truncate">{char.description.slice(0, 60)}</p>
                    )}
                  </div>
                  {mode === 'character_pov' && isPov && (
                    <span className="text-[10px] text-purple-400 bg-purple-900/30 px-1.5 py-0.5 rounded shrink-0">
                      主视角
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Condition (narrator mode) */}
      {mode === 'narrator_pov' && (
        <section>
          <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">初始条件</h2>
          <textarea
            value={condition}
            onChange={e => onConditionChange(e.target.value)}
            placeholder="描述叙事者设定的客观条件...&#10;例如：敌军压境，城中粮草仅够维持三日"
            rows={3}
            className="w-full bg-zinc-800/50 border border-zinc-700 rounded-xl px-4 py-3 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500/50 resize-none"
          />
        </section>
      )}

      {/* Error */}
      {error && (
        <div className="text-xs text-red-400 text-center py-2.5 border border-red-900/30 rounded-xl bg-red-950/20">
          {error}
        </div>
      )}

      {/* Start Button */}
      <button
        onClick={onStart}
        disabled={!canStart || loading}
        className="w-full text-sm bg-purple-900/40 text-purple-300 border border-purple-800/50 rounded-xl px-4 py-3 hover:bg-purple-800/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <span className="w-3 h-3 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
            正在启动...
          </>
        ) : (
          <>
            <Icon name="compass" size={14} />
            开始推演
          </>
        )}
      </button>

      {/* Session History */}
      {sessions.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-wider">
            推演历史
            <span className="font-normal text-zinc-600 ml-1">({sessions.length})</span>
          </h2>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {sessions.map(sim => (
              <div
                key={sim.id}
                className="flex items-center gap-2 p-2.5 rounded-lg border border-zinc-800 bg-zinc-900/30 hover:border-zinc-700 transition-all"
              >
                <button
                  onClick={() => onContinue(sim.id)}
                  className="flex-1 flex items-center gap-2 min-w-0 text-left"
                >
                  <Icon name="compass" size={12} className="text-purple-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-zinc-500 shrink-0">
                        {sim.mode === 'character_pov' ? '角色' : '叙事者'}
                      </span>
                      <span className="text-xs text-zinc-400 truncate">
                        {sim.setting || sim.condition || '未命名推演'}
                      </span>
                    </div>
                    <div className="text-[9px] text-zinc-600">
                      {sim.turn_count || 0}回合 · {sim.status}
                    </div>
                  </div>
                </button>
                <button
                  onClick={() => onDeleteSession(sim.id)}
                  className="text-zinc-600 hover:text-red-400 transition-colors shrink-0 p-1"
                  title="删除"
                >
                  <Icon name="trash-2" size={12} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

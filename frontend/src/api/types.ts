// Shared API types — extracted from the former api.ts monolith.

export interface UpdateStatus {
  current_version: string
  update_check_enabled: boolean
}

export interface UpdateCheckResult {
  current_version: string
  latest_version: string | null
  has_update: boolean
  release_url: string
  release_notes: string | null
  published_at: string | null
  error: string | null
  message?: string
  update_check_enabled?: boolean
}

export interface BookData {
  id: string
  title: string
  description: string
  entityCount: number
  chapterCount: number
  createdAt: string
  updatedAt: string
}

export interface SessionData {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messageCount: number
}

export interface ProviderData {
  id: string
  name: string
  type: string
  api_key?: string
  base_url?: string
  models: string[]
}

export interface AutopilotTaskData {
  task_id: string
  status: string
  audit_mode: string
  progress: number
  chapters_completed: number
  total_chapters: number
}

export interface AutopilotStatusData {
  active: boolean
  tasks: AutopilotTaskData[]
}

export interface StylesListData {
  styles: unknown[]
}

export interface StructureReportData {
  book_id: string
  chapter_count: number
  total_words: number
  avg_chapter_length: number
  chapter_length_distribution: number[]
  dialogue_ratio_distribution: number[]
  avg_dialogue_ratio: number
  paragraph_stats: { avg_per_chapter: number; avg_length: number }
  sentence_stats: { avg_per_chapter: number; avg_length: number }
  pacing_curve: { chapter: number; title: string; word_count: number; dialogue_ratio: number; pace_score: number }[]
  pov_distribution: Record<string, number>
}

export interface StyleFingerprintData {
  book_id: string
  sentence_length_distribution: Record<string, number>
  vocabulary_richness_ttr: number
  punctuation_pattern: Record<string, number>
  four_char_idiom_density: number
  paragraph_length_stats: { mean: number; median: number; std: number }
  dialogue_density: number
}

export interface AnalysisSummaryData {
  ref_book_id: string
  structure?: { chapter_count: number; total_words: number; avg_chapter_length: number; avg_dialogue_ratio: number }
  style_fingerprint?: { vocabulary_richness_ttr: number; dialogue_density: number; four_char_idiom_density: number }
  deep_style?: { dimensions_analyzed: number }
  emotional_curve?: { chapter_count: number }
}

export interface SkillsListData {
  skills: SkillData[]
}

export interface SkillData {
  name: string
  description: string
  steps: unknown[]
}

export interface SettingsData {
  mode: string
  providers: ProviderData[]
  slot_pro?: { provider_id: string; model: string }
  slot_flash?: { provider_id: string; model: string }
  custom_map?: Record<string, string>
}

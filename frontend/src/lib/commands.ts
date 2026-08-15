// 斜杠命令注册表——真正的命令系统（非文本提示）
// 两类命令：
//   ui: 前端直接执行（切 tab/开面板/建章节），不经过 AI
//   ai: 翻译成结构化指令发给 AI（明确指令，不让 AI 猜前缀含义）
import { emitTabSwitch } from './events'

export interface SlashCommand {
  cmd: string            // 命令名（不含 /）
  label: string          // 菜单显示名
  desc: string           // 菜单描述
  type: 'ui' | 'ai'      // 执行类型
  usage?: string         // 用法示例
  /** ui 命令的动作；ai 命令可选（缺省=翻译为指令文本） */
  action?: () => void
  /** ai 命令：把用户参数翻译成给 AI 的明确指令 */
  translate?: (args: string) => string
}

export const SLASH_COMMANDS: SlashCommand[] = [
  // ── UI 命令：前端直接执行 ──
  { cmd: 'tree', label: '叙事树', desc: '打开叙事树画布', type: 'ui', action: () => emitTabSwitch('storytree') },
  { cmd: 'workflow', label: '工作流', desc: '打开工作流画布', type: 'ui', action: () => emitTabSwitch('workflow') },
  { cmd: 'graph', label: '知识图谱', desc: '打开知识库（图谱视图）', type: 'ui', action: () => emitTabSwitch('knowledge') },
  { cmd: 'outline', label: '大纲', desc: '打开大纲面板', type: 'ui', action: () => emitTabSwitch('outline') },
  { cmd: 'plot', label: '伏笔', desc: '打开伏笔面板', type: 'ui', action: () => emitTabSwitch('foreshadows') },
  { cmd: 'materials', label: '资料', desc: '打开资料面板', type: 'ui', action: () => emitTabSwitch('materials') },
  { cmd: 'review', label: '评审团', desc: '打开评审面板', type: 'ui', action: () => emitTabSwitch('review') },
  { cmd: 'mind', label: '心智', desc: '打开心智面板（倾向/记忆）', type: 'ui', action: () => emitTabSwitch('bias') },
  { cmd: 'brief', label: '简介', desc: '打开项目简介', type: 'ui', action: () => emitTabSwitch('brief') },
  { cmd: 'explore', label: '探索', desc: '打开探索面板', type: 'ui', action: () => emitTabSwitch('explore') },
  { cmd: 'play', label: '互动推演', desc: '打开互动推演', type: 'ui', action: () => emitTabSwitch('play') },
  { cmd: 'settings', label: '设置', desc: '打开设置（模型/档位）', type: 'ui', action: () => emitTabSwitch('settings') },

  // ── AI 命令：翻译为结构化指令 ──
  {
    cmd: 'w', label: '写作', desc: '严格模式写作：按指令写正文', type: 'ai',
    usage: '/w 写作指令', translate: (a) => `【写作指令】请严格按以下要求写正文（场景/人物状态/推进点明确）：\n${a}`,
  },
  {
    cmd: 'ws', label: '宽松写作', desc: '宽松模式：给方向，AI 自主发挥', type: 'ai',
    usage: '/ws 方向', translate: (a) => `【写作方向】按以下方向自由发挥写正文：\n${a}`,
  },
  {
    cmd: 's', label: '提取设定', desc: '从文本提取设定（角色/地点/物件）', type: 'ai',
    usage: '/s 文本', translate: (a) => `【设定提取】从以下文本提取角色/地点/物件/设定实体并登记图谱：\n${a}`,
  },
  {
    cmd: 'style', label: '文风', desc: '应用/查看写作风格', type: 'ai',
    usage: '/style 风格描述', translate: (a) => a ? `【文风指令】按以下风格写作：${a}` : '【文风指令】列出当前可用的写作风格',
  },
  { cmd: 'help', label: '帮助', desc: '显示所有命令', type: 'ai', translate: () => '【命令帮助】请向用户解释可用命令，并建议下一步' },
]

export function findCommand(cmd: string): SlashCommand | undefined {
  const name = cmd.replace(/^\//, '').trim().split(' ')[0].toLowerCase()
  return SLASH_COMMANDS.find((c) => c.cmd === name)
}

/** 处理斜杠命令输入，返回 true 表示已消费（无需发给 AI 原文） */
export function handleSlashInput(raw: string): { consumed: boolean; send: string } {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('/')) return { consumed: false, send: trimmed }

  const cmdName = trimmed.slice(1).split(' ')[0].toLowerCase()
  const cmd = findCommand(cmdName)
  if (!cmd) return { consumed: false, send: trimmed }

  // UI 命令：前端执行
  if (cmd.type === 'ui' && cmd.action) {
    cmd.action()
    return { consumed: true, send: '' }
  }

  // AI 命令：翻译为明确指令
  const args = trimmed.slice(1 + cmdName.length).trim()
  if (cmd.type === 'ai') {
    const translated = cmd.translate ? cmd.translate(args) : trimmed
    return { consumed: true, send: translated }
  }

  return { consumed: false, send: trimmed }
}

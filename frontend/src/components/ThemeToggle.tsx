import { useTheme } from "../hooks/useTheme"
import Icon from './ui/Icon'

const themeCycle: Array<{ key: 'dark' | 'light' | 'system'; label: string; icon: string }> = [
  { key: 'dark', label: '暗色', icon: 'moon' },
  { key: 'light', label: '亮色', icon: 'sun' },
  { key: 'system', label: '跟随系统', icon: 'monitor' },
]

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  function cycle() {
    const idx = themeCycle.findIndex(t => t.key === theme)
    const next = themeCycle[(idx + 1) % themeCycle.length]
    setTheme(next.key)
  }

  const current = themeCycle.find(t => t.key === theme) || themeCycle[0]

  return (
    <button
      onClick={cycle}
      className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0"
      title={`主题: ${current.label} (点击切换)`}
      aria-label={`主题: ${current.label}`}
    >
      <Icon name={current.icon} size={16} />
    </button>
  )
}

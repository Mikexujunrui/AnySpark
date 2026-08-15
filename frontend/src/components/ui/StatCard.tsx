import Icon from './Icon'

export default function StatCard({ icon, label, value, sub, accent = 'sky' }) {
  const accentMap = {
    sky:      'from-sky-900/40 to-sky-800/20 border-sky-800/40 text-sky-300',
    emerald:  'from-emerald-900/40 to-emerald-800/20 border-emerald-800/40 text-emerald-300',
    amber:    'from-amber-900/40 to-amber-800/20 border-amber-800/40 text-amber-300',
    purple:   'from-purple-900/40 to-purple-800/20 border-purple-800/40 text-purple-300',
  }
  const classes = accentMap[accent] || accentMap.sky
  return (
    <div className={`bg-gradient-to-br ${classes.split(' ').slice(0, 2).join(' ')} border ${classes.split(' ')[2]} rounded-xl p-4 hover:scale-[1.02] transition-all`}>
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-8 h-8 rounded-lg bg-black/20 flex items-center justify-center ${classes.split(' ')[3]}`}>
          <Icon name={icon} size={16} />
        </div>
        <span className="text-[11px] uppercase tracking-wider text-zinc-400">{label}</span>
      </div>
      <div className="text-2xl font-bold text-zinc-100 mb-0.5">{value}</div>
      {sub && <div className="text-[10px] text-zinc-500">{sub}</div>}
    </div>
  )
}

export const DATA_COLORS = {
  character: { fill: '#1e293b', stroke: '#38bdf8', label: '人物' },
  location: { fill: '#042f2e', stroke: '#2dd4bf', label: '地点' },
  organization: { fill: '#1e1b4b', stroke: '#818cf8', label: '组织' },
  event: { fill: '#431407', stroke: '#fb923c', label: '事件' },
  item: { fill: '#172554', stroke: '#60a5fa', label: '物品' },
  concept: { fill: '#3b0764', stroke: '#c084fc', label: '概念' },
  world: { fill: '#082f49', stroke: '#38bdf8', label: '世界' },
  region: { fill: '#042f2e', stroke: '#2dd4bf', label: '区域' },
  city: { fill: '#1e1b4b', stroke: '#818cf8', label: '城市' },
  building: { fill: '#431407', stroke: '#fb923c', label: '建筑' },
  room: { fill: '#27272a', stroke: '#71717a', label: '房间' },
  other: { fill: '#27272a', stroke: '#52525b', label: '其他' },
  unknown: { fill: '#27272a', stroke: '#52525b', label: '未知' },
}

export const RELATION_COLORS = {
  ally: '#2dd4bf',
  family: '#fb923c',
  romantic: '#f472b6',
  antagonist: '#f87171',
  master_of: '#a78bfa',
  knows: '#94a3b8',
  owns: '#38bdf8',
  belongs_to: '#818cf8',
  causes: '#fb923c',
  located_at: '#2dd4bf',
  participates_in: '#c084fc',
  path: '#71717a',
  portal: '#c084fc',
  contains: '#3f3f46',
  near: '#52525b',
}

export const NODE_RADIUS = {
  world: 18,
  region: 15,
  city: 13,
  building: 11,
  room: 8,
  character: 12,
  other: 10,
}

export const CONN_DASH = {
  path: '',
  portal: '6,3',
  contains: '2,2',
  near: '4,2',
}

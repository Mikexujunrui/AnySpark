// 全局轻量事件总线（tab 切换/面板开关，供斜杠命令等跨组件通信）
// 用法：emitTabSwitch('storytree') / onTabSwitch(cb) 返回取消函数
type Handler = (tab: string) => void

const tabHandlers = new Set<Handler>()

export function emitTabSwitch(tab: string) {
  tabHandlers.forEach((h) => h(tab))
}

export function onTabSwitch(h: Handler): () => void {
  tabHandlers.add(h)
  return () => tabHandlers.delete(h)
}

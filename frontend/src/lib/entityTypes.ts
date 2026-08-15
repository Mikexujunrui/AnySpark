// 实体类型判定（S154 提取共享——CharactersPanel 与 FullGraphView 保持同一套规则）
// 人物类型判定：类型名含"角色"或"人物"（图谱类型动态，默认"角色"）
export function isPersonType(t: string): boolean {
  return t.includes("角色") || t.includes("人物");
}

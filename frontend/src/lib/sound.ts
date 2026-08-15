// sound — 任务结束/待确认/卡住的提示音（S155：主人需求）
// Web Audio 零资源依赖（无音频文件，代码生成短音）。统一轻音量，不刺耳。
// 主循环内只在：整个循环彻底结束（done）/ 需要人类操作（批准/提问）时响——
// 中间工具调用/每轮思考绝不响（主人明确要求）。

let _ctx: AudioContext | null = null

function ctx(): AudioContext | null {
  try {
    if (!_ctx) {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AC) return null
      _ctx = new AC()
    }
    if (_ctx.state === "suspended") void _ctx.resume()
    return _ctx
  } catch {
    return null
  }
}

function tone(
  freq: number,
  startSec: number,
  durSec: number,
  type: OscillatorType = "sine",
  volume = 0.12
): void {
  const c = ctx()
  if (!c) return
  try {
    const osc = c.createOscillator()
    const gain = c.createGain()
    osc.type = type
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0, c.currentTime + startSec)
    gain.gain.linearRampToValueAtTime(volume, c.currentTime + startSec + 0.02)
    gain.gain.setValueAtTime(volume, c.currentTime + startSec + durSec - 0.03)
    gain.gain.linearRampToValueAtTime(0, c.currentTime + startSec + durSec)
    osc.connect(gain)
    gain.connect(c.destination)
    osc.start(c.currentTime + startSec)
    osc.stop(c.currentTime + startSec + durSec + 0.05)
  } catch {
    /* 音频不可用静默 */
  }
}

export type SoundKind = "done" | "fail" | "attention" | "stuck"

// 完成：欢快双音（高→更高）
export function playDone(): void {
  tone(660, 0, 0.12)
  tone(880, 0.14, 0.16)
}

// 失败：低沉双音（低→更低）
export function playFail(): void {
  tone(300, 0, 0.14)
  tone(220, 0.16, 0.18)
}

// 需要人类操作（批准/提问）：中音长鸣一声
export function playAttention(): void {
  tone(520, 0, 0.4, "sine", 0.15)
}

// 卡住/超时：三声急促警报
export function playStuck(): void {
  tone(440, 0, 0.1, "square", 0.08)
  tone(440, 0.16, 0.1, "square", 0.08)
  tone(440, 0.32, 0.14, "square", 0.08)
}

export function playSound(kind: SoundKind): void {
  switch (kind) {
    case "done":
      playDone()
      break
    case "fail":
      playFail()
      break
    case "attention":
      playAttention()
      break
    case "stuck":
      playStuck()
      break
  }
}

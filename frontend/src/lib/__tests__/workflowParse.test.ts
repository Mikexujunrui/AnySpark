// workflowParse 纯函数测试（S147 系列前端逻辑——空气泡/结果可见性修复的回归锚点）
import { describe, it, expect } from "vitest";
import {
  parseLoopItems,
  extractFallbackResult,
  normalizeHistoryMessages,
  correctStaleBatchMessages,
} from "../workflowParse";

describe("parseLoopItems（批量任务结果明细）", () => {
  it("从 loop 节点 output 提取每迭代 items", () => {
    const task = {
      node_states: [
        { node_id: "loop", output: JSON.stringify({ iterations: 2, items: [
          { iter: 0, title: "第一章", review: "硬伤数: 1" },
          { iter: 1, title: "第二章", review: "硬伤数: 3" },
        ] }) },
      ],
    };
    const items = parseLoopItems(task as never);
    expect(items).toHaveLength(2);
    expect(items[0].title).toBe("第一章");
    expect(items[1].review).toBe("硬伤数: 3");
  });

  it("loop 无 output / 非法 JSON → 空数组（不炸）", () => {
    expect(parseLoopItems({ node_states: [] } as never)).toEqual([]);
    expect(parseLoopItems({ node_states: [{ node_id: "loop", output: "not-json" }] } as never)).toEqual([]);
  });

  it("旧引擎任务（output 仅 iterations 无 items）→ 空数组（触发 fallback）", () => {
    const task = { node_states: [{ node_id: "loop", output: JSON.stringify({ iterations: 4 }) }] };
    expect(parseLoopItems(task as never)).toEqual([]);
  });
});

describe("extractFallbackResult（旧引擎任务兜底）", () => {
  it("从顶层 results 挑审读/改写输出", () => {
    expect(extractFallbackResult({ review: "硬伤数: 5\n报告" })).toEqual({ key: "review", text: "硬伤数: 5\n报告" });
    expect(extractFallbackResult({ rewritten: "改写后正文" })).toEqual({ key: "rewritten", text: "改写后正文" });
  });

  it("空 results / 无关键键 → null", () => {
    expect(extractFallbackResult(null)).toBeNull();
    expect(extractFallbackResult({ chapter_ids: "x" })).toBeNull();
    expect(extractFallbackResult({ review: "   " })).toBeNull();
  });
});

describe("normalizeHistoryMessages（历史规范化，空气泡根治）", () => {
  it("content→text 映射 + 过滤空文本 agent 消息", () => {
    const raw = [
      { role: "user", content: "你好" },
      { role: "assistant", content: "正常回复" },
      { role: "assistant", content: "" }, // 工具轮空声明
      { role: "assistant", content: "工具后回复" },
    ];
    const out = normalizeHistoryMessages(raw as never);
    expect(out.map((m) => m.text)).toEqual(["你好", "正常回复", "工具后回复"]);
  });

  it("空字符串 content 也必须被过滤（?? 对空串不生效的回归锚点）", () => {
    const raw = [{ role: "assistant", content: "" }];
    expect(normalizeHistoryMessages(raw as never)).toEqual([]);
  });

  it("user 空消息保留（用户侧语义），agent 空消息过滤", () => {
    const out = normalizeHistoryMessages([
      { role: "user", content: "" },
      { role: "agent", text: "" },
    ] as never);
    expect(out).toHaveLength(1);
    expect(out[0].role).toBe("user");
  });
});

describe("correctStaleBatchMessages（陈旧批量状态纠正）", () => {
  it('纠正"[批量改写执行中]"历史快照为结束提示', () => {
    const out = correctStaleBatchMessages([{ role: "agent", text: "[批量改写执行中] 1/3 节点…" }]);
    expect(out[0].text).toContain("[批量改写任务已结束（详情见批量面板）]");
  });

  it('审读同样纠正；非批量消息不动', () => {
    const out = correctStaleBatchMessages([
      { role: "agent", text: "[批量审读执行中] 2/4 节点…" },
      { role: "agent", text: "[批量改写完成] 3/3 节点" },
      { role: "user", text: "正常问题" },
    ]);
    expect(out[0].text).toContain("[批量审读任务已结束（详情见批量面板）]");
    expect(out[1].text).toBe("[批量改写完成] 3/3 节点");
    expect(out[2].text).toBe("正常问题");
  });
});

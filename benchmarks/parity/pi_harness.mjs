/**
 * pi 侧 harness：用 pi-agent-core 的 agent-loop 跑脚本化场景，输出归一化轨迹。
 *
 * 目的：与 local_harness.py 输出同格式轨迹，由 run_parity.py 对比——
 * 证明本地循环与 pi 循环在工具调用/结果回填/截断防护/插话等行为上语义一致。
 *
 * 用法：node pi_harness.mjs <scenario_id> [--dump]
 * 输出：stdout 一个 JSON：{ id, trace: [strings] }
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AGENT_LOOP = "file:///E:/Claudecode/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-agent-core/dist/agent-loop.js";
const { runAgentLoop } = await import(AGENT_LOOP);
const EVT_STREAM = "file:///E:/Claudecode/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/utils/event-stream.js";
const { createAssistantMessageEventStream } = await import(EVT_STREAM);
const TYPEBOX = "file:///E:/Claudecode/node_modules/@earendil-works/pi-coding-agent/node_modules/typebox/build/index.mjs";
const { Type } = await import(TYPEBOX);

const here = dirname(fileURLToPath(import.meta.url));
const scenarios = JSON.parse(readFileSync(join(here, "scenarios.json"), "utf-8")).scenarios;

// ---------------------------------------------------------------------------
// 工具（与本地 harness 语义一致）
// ---------------------------------------------------------------------------
const tools = [
  {
    name: "add",
    description: "加法",
    executionMode: "parallel",
    parameters: Type.Object({
      a: Type.Number(),
      b: Type.Number(),
    }),
    execute: async (_id, args) => ({
      content: [{ type: "text", text: `${args.a} + ${args.b} = ${args.a + args.b}` }],
      details: {},
    }),
  },
  {
    name: "echo",
    description: "回声",
    executionMode: "parallel",
    parameters: Type.Object({
      text: Type.String(),
    }),
    execute: async (_id, args) => ({
      content: [{ type: "text", text: `echo:${args.text}` }],
      details: {},
    }),
  },
  {
    name: "boom",
    description: "必炸",
    executionMode: "parallel",
    parameters: Type.Object({}),
    execute: async () => {
      throw new Error("boom 异常");
    },
  },
];

const EMPTY_USAGE = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

function textOf(content) {
  return (content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("");
}

function traceLine(msg) {
  switch (msg.role) {
    case "user":
      return `user:${textOf(msg.content)}`;
    case "assistant": {
      const toolCalls = msg.content.filter((b) => b.type === "toolCall");
      if (toolCalls.length > 0) {
        return `assistant:toolCalls[${toolCalls
          .map((tc) => `${tc.name}(${JSON.stringify(tc.arguments)})#${tc.id}`)
          .join(",")}]`;
      }
      return `assistant:${textOf(msg.content)}`;
    }
    case "toolResult": {
      const body = textOf(msg.content);
      if (msg.isError) return `toolResult:${msg.toolCallId}:error`;
      return `toolResult:${msg.toolCallId}:ok:${body}`;
    }
    default:
      return `${msg.role}:${JSON.stringify(msg.content ?? "")}`;
  }
}

/**
 * fake streamFn：按脚本步骤返回模型响应。
 * pi 的事件协议：start/text_delta/toolcall_delta/.../done(message) 或 error(error)。
 */
function fakeStream(_model, _ctx, _opts) {
  const step = script.shift();
  if (!step) throw new Error("脚本耗尽（模型响应次数超过预期）");

  const stream = createAssistantMessageEventStream();

  const base = {
    role: "assistant",
    content: [],
    api: "openai-completions",
    provider: "parity-test",
    model: "parity-test",
    usage: EMPTY_USAGE,
    stopReason: "pending",
    timestamp: Date.now(),
  };
  let partial = { ...base };

  stream.push({ type: "start", partial });

  if (step.text) {
    partial = { ...partial, content: [{ type: "text", text: step.text }] };
    stream.push({ type: "text_delta", partial });
  }
  if (step.toolCalls) {
    partial = {
      ...partial,
      content: step.toolCalls.map((tc) => ({
        type: "toolCall",
        id: tc.id,
        name: tc.name,
        arguments: tc.args,
      })),
    };
    stream.push({ type: "toolcall_end", partial });
  }
  const final = {
    ...partial,
    stopReason: step.stopReason || (step.toolCalls ? "toolUse" : "stop"),
    usage: { ...EMPTY_USAGE, input: 10, output: 10, totalTokens: 20 },
  };
  stream.push({ type: "done", message: final });
  return stream;
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
const scenarioId = process.argv[2];
const scenario = scenarios.find((s) => s.id === scenarioId);
if (!scenario) {
  console.error(`场景不存在: ${scenarioId}（可用: ${scenarios.map((s) => s.id).join(", ")}）`);
  process.exit(1);
}

// 脚本深拷贝 + 重置
let script = JSON.parse(JSON.stringify(scenario.steps));
const steerAfter = scenario.steerAfterStep ?? -1;
const steerText = scenario.steerText ?? "";

const trace = [];
let steerDone = false;

const config = {
  model: {
    id: "parity-test",
    provider: "parity-test",
    api: "openai-completions",
    name: "parity-test",
    baseUrl: "",
    reasoning: false,
    input: [],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 65536,
    maxTokens: 8192,
  },
  convertToLlm: (messages) =>
    messages.filter(
      (m) => m.role === "user" || m.role === "assistant" || m.role === "toolResult",
    ),
  getSteeringMessages: async () => {
    if (!steerDone && steerAfter >= 0 && toolRounds >= steerAfter && toolRounds > 0) {
      steerDone = true;
      return [
        {
          role: "user",
          content: [{ type: "text", text: steerText }],
          timestamp: Date.now(),
        },
      ];
    }
    return [];
  },
  getFollowUpMessages: async () => [],
  toolExecution: "parallel",
};

let toolRounds = 0;

try {
  await runAgentLoop(
    [{ role: "user", content: [{ type: "text", text: "任务" }], timestamp: Date.now() }],
    { systemPrompt: "", messages: [], tools },
    config,
    async (event) => {
      if (event.type === "message_end" && event.message) {
        trace.push(traceLine(event.message));
      }
      if (event.type === "turn_end" && event.message?.content?.some((b) => b.type === "toolCall")) {
        toolRounds++;
      }
    },
    undefined,
    fakeStream,
  );
} catch (e) {
  trace.push(`harness_error:${e.message}`);
}

console.log(JSON.stringify({ id: scenarioId, trace }));

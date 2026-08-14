# 本地模型适配指南（vLLM / LM Studio / Ollama / llama.cpp）

> 接 S131 多模型兼容协议（openai/anthropic/gemini/responses）——本地推理服务
> （vLLM/LM Studio/Ollama/llama.cpp）走 `openai` 协议（OpenAI Chat Completions 兼容），
> 通过运行时模型注册表（/api/models）热切换，无需重启、无需改代码。
> 关联：DESIGN §12.39（运行时模型注册表）· registry.py（协议工厂）· deepseek.py（openai 适配器）。

## 一、为什么本地模型走 openai 协议

| 本地服务 | 兼容协议 | 说明 |
|---|---|---|
| vLLM（OpenAI 兼容服务器）| `openai` | `vllm serve` 自带 `/v1/chat/completions` |
| LM Studio（Local Server）| `openai` | 内置 OpenAI 兼容端点 |
| Ollama | `openai`（官方兼容层）| `OLLAMA_HOST` 起服务，`/v1` 端点 |
| llama.cpp（server）| `openai` | `llama-server` 提供 `/v1` |

DeepSeekModel（openai 适配器）就是通用 OpenAI Chat Completions 客户端——换 base_url
即连本地服务。registry 的 `_PROTOCOL_FACTORIES["openai"] = DeepSeekModel` 已覆盖。

## 二、快速接入（3 步）

### 第 1 步：启动本地推理服务

以 vLLM 为例（已装 vllm）：

```bash
# 小模型（写作场景够用，如 Qwen2.5-7B-Instruct）
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --port 8001 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.85
```

LM Studio：安装 → 下载模型（如 `qwen2.5-7b-instruct`）→ 加载 → Developer 面板
"Start Server"（默认 `http://127.0.0.1:1234/v1`）。

### 第 2 步：注册模型配置（API 或前端）

```json
POST /api/models
{
  "name": "本地Qwen",
  "base_url": "http://127.0.0.1:8001/v1",
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "api_key": "local-dummy",
  "protocol": "openai",
  "context_window": 32768,
  "max_tokens": 4096,
  "temperature": 0.7,
  "thinking": "off"
}
```

- **base_url**：本地端点（vLLM 带 `/v1`；LM Studio 带 `/v1`；Ollama 用
  `http://127.0.0.1:11434/v1`）
- **api_key**：本地服务不校验，填任意占位（如 `local-dummy`）即可
- **thinking**：本地小模型通常不支持 reasoning，置 `off`（详见第四节）
- **context_window**：务必按模型实际上下文填（7B 通常 32K；写长章时窗口太小会截断）

### 第 3 步：激活

```json
POST /api/models/{model_id}/activate
```

激活后所有消费方（Agent/图谱抽取/检测/探索/后台任务）即时跟随，无需重启。
前端 Settings → 模型 面板同样可操作（增删改 + 激活）。

## 三、验证

```bash
# 健康检查（返回当前激活模型）
curl http://127.0.0.1:8000/api/health
# → {"status":"ok","model":"Qwen/Qwen2.5-7B-Instruct", ...}

# 对话走本地模型
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "写一句雨夜的描写"}'
```

## 四、注意事项（实测踩坑）

1. **本地端点与代理冲突**：openai 适配器显式 `trust_env=False`（S131）——不读系统
   HTTP(S)_PROXY，本地 127.0.0.1 请求不会误发到代理导致 502。远端 API 不受影响。

2. **thinking 思考强度**：本地小模型多数无 reasoning。注册表 thinking 支持
   `off/minimal/low/medium/high/xhigh/max`；本地模型置 `off`，否则可能报
   `unsupported parameter` 或返回空 reasoning。若你的本地模型支持（如 QwQ），
   可置 `low` 实测。

3. **上下文窗口**：`DEEPSEEK_CONTEXT_WINDOW` 环境变量只影响默认 DeepSeek 配置。
   本地模型必须显式传 `context_window`（注册表字段），否则按 65536 算——窗口不足时
   长书写作触发压缩频次异常，表现是"越写越碎"。

4. **max_tokens**：本地小模型输出上限通常 2K-4K（vLLM 默认按 `--max-model-len` 扣）。
   写整章正文时建议 ≥4096；生成工具调用（ToolCall）的场景 token 消耗小，2K 够。

5. **模型能力差异**：本地 7B 级模型在复杂写作（长章一致性/伏笔回收/图谱抽取）上
   质量明显弱于 DeepSeek V4——建议定位：**测试/隐私敏感场景用本地，正式创作回 DeepSeek**。
   注册表随时热切，零成本。

6. **Ollama 兼容层**：Ollama 的 `/v1` 端点仅支持 Chat Completions 子集；工具调用
   （tool_calls）部分模型不支持，写作场景（write_chapter 工具）可能退化为主循环直写
   （降级路径，DESIGN §12.19 C 架构已内置）。vLLM/LM Studio 对工具调用支持更完整。

## 五、常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 502 Bad Gateway | base_url 拼错/服务没起/被代理拦截 | 先 `curl http://127.0.0.1:PORT/v1/models` 直测；确认端口与 `/v1` 后缀 |
| 401/403 | api_key 占位不被本地服务接受 | 部分服务要求非空 key——用 `local-dummy` 或 `ollama`（Ollama 惯例） |
| 空输出/反复重试 | 模型上下文窗口被填满 | 调小 context_window 或降 max_tokens |
| `unsupported parameter: reasoning` | 本地模型不支持 thinking | 注册表 thinking 置 `off` 后重新激活 |
| 生成停顿但无错误 | 本地显存不足触发 vLLM 拒绝 | 换小模型/调低 `--gpu-memory-utilization` |

## 六、与 .env 的关系

- `.env` 的 `DEEPSEEK_*` 只播种**默认 DeepSeek 配置**（首次启动/空库时）；
  注册表里的其他配置持久化在 `data/anyspark.db` 的 `model_configs` 表。
- 想默认启动就用本地模型：注册表中把本地配置激活即可（`.env` 不再生效于当前会话，
  下次空库才重新播种）。
- 全部清空注册表后重启，DeepSeek 默认配置会重新播种（升级即用）。

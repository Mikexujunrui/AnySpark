# CLI 手动测试计划（AI 可执行）

> **目标读者**：AI Agent（如 Qoder、Cursor、Claude Code）
> **测试范围**：除前端 UI 外的所有后端功能
> **测试方式**：通过 CLI 非交互模式 + REST API curl 命令执行
> **测试项目**：`__test_novel__`（双下划线前缀，与真实项目隔离，测试完即删）

---

## 前置条件

### 环境要求
```bash
# 1. 确保 Python 3.11+ 可用
python --version

# 2. 确保依赖已安装
pip install -r requirements.txt

# 3. 确保 Neo4j 运行中（如无则跳过图谱相关测试）
docker ps | grep neo4j || echo "Neo4j 未运行，图谱相关测试将跳过"

# 4. 确保 .env 文件存在且配置了 LLM provider
python -c "import os; from dotenv import load_dotenv; load_dotenv(); assert os.getenv('API_KEY'), 'API_KEY 未配置'"
```

### 工作目录
所有命令从项目根目录执行：
```bash
cd "d:/总/小说/写作辅助/自研高级时间线辅助写作agent"
```

### 测试项目 ID
**全部测试使用同一个项目 ID：`__test_novel__`**
- 双下划线前缀确保不会与任何真实项目名冲突
- 测试完成后统一清理

---

## 第一阶段：世界观搭建（模拟用户从零开始创建小说）

> 用户场景：一个新作者想写修仙小说，先通过 CLI 录入世界观和角色设定。

### 1.1 启动服务器
```bash
# 后台启动后端（PowerShell）
Start-Process -WindowStyle Minimized -FilePath "python" -ArgumentList "-u src/server.py"
Start-Sleep -Seconds 3
```

### 1.2 创建书籍
```bash
curl -s -X POST http://localhost:8191/api/books \
  -H "Content-Type: application/json" \
  -d '{"title": "测试小说-青云志", "description": "CLI自动化测试用书"}' | python -m json.tool
```

### 1.3 录入核心角色
```bash
python -m src.main -p __test_novel__ --non-interactive "/s 主角叶凡，20岁，青云宗外门弟子。性格坚韧不拔、重情重义。擅长剑术，拥有尚未觉醒的古魔血脉。外表清秀但眼神锐利。"

python -m src.main -p __test_novel__ --non-interactive "/s 林婉，青云宗长老，叶凡的师父。修为元婴期，性格温和但原则性极强。外表约30岁，实际年龄不详。擅长水系法术和炼丹。"

python -m src.main -p __test_novel__ --non-interactive "/s 苏晴，18岁，青云宗内门弟子，叶凡的师妹。性格活泼开朗，天真善良。擅长风系法术。暗恋叶凡但不敢表白。"

python -m src.main -p __test_novel__ --non-interactive "/s 慕容白，青云宗宗主，修为元婴后期。性格威严深沉，对叶凡的身世有所怀疑。擅长雷系法术，在宗门内威望极高。"
```

### 1.4 录入世界观设定
```bash
python -m src.main -p __test_novel__ --non-interactive "/s 青云宗位于苍澜大陆东部的青云山脉，是大陆三大宗门之一。宗门分内外两门，外门弟子需通过考核才能进入内门。宗门地下埋藏着上古魔神的遗骸，但无人知晓。"

python -m src.main -p __test_novel__ --non-interactive "/s 苍澜大陆以修仙为主流，分为炼气、筑基、金丹、元婴、化神五大境界。元婴期以上即为一方强者。大陆上还有太虚门和万剑阁两大宗门，与青云宗形成三足鼎立之势。"
```

### 1.5 录入角色关系
```bash
python -m src.main -p __test_novel__ --non-interactive "/s 叶凡与林婉是师徒关系，林婉对叶凡既严格又关爱。叶凡暗恋师妹苏晴。苏晴也暗恋叶凡。慕容白对叶凡有敌意，因为怀疑叶凡与古魔有关。"
```

### 1.6 录入伏笔
```bash
python -m src.main -p __test_novel__ --non-interactive "/s 叶凡的古魔血脉将在金丹期首次觉醒。青云宗地下的上古魔神遗骸将在故事中期被意外发现。林婉与慕容白之间有一段不为人知的过往。"
```

### 1.7 验证知识库
```bash
python -m src.main -p __test_novel__ --non-interactive "/list"
python -m src.main -p __test_novel__ --non-interactive "/stats"
```

### 1.8 查看角色详情
```bash
python -m src.main -p __test_novel__ --non-interactive "/char 叶凡"
python -m src.main -p __test_novel__ --non-interactive "/char 林婉"
```

### 1.9 导出知识库
```bash
python -m src.main -p __test_novel__ --non-interactive "/export"
```

---

## 第二阶段：大纲与规划（模拟用户规划故事结构）

> 用户场景：录入设定后，让 Agent 帮忙生成大纲和分卷规划。

### 2.1 Agent 生成大纲
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 根据当前知识库中的角色和世界观，生成一个10章的小说大纲，故事主线是叶凡从外门弟子成长为强者的历程"
```

### 2.2 查看大纲
```bash
python -m src.main -p __test_novel__ --non-interactive "/outline"
```

### 2.3 Agent 生成细纲
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 根据大纲，生成前3章的详细细纲，每章包含具体的情节节拍"
```

### 2.4 Agent 创建分卷
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 创建分卷：第一卷名为'青云初入'，包含第1-3章，故事线为叶凡在青云宗的起步与初次觉醒"
```

### 2.5 查看分卷
```bash
python -m src.main -p __test_novel__ --non-interactive "/volumes"
```

---

## 第三阶段：章节写作（模拟用户逐章创作）

> 用户场景：作者开始写正文，连续写3章（每章至少3000字，网文标准）。
> ⚠️ 必须验证每章字数 ≥ 2500 字，否则视为测试失败。

### 3.1 写第1章
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 写第1章，标题为'外门弟子'。内容：叶凡在青云宗外门的日常修炼生活，展现他的勤奋和天赋，以及与其他外门弟子的关系。至少3000字。写完后用 store_chapter 保存为正式章节。"
```

### 3.2 验证第1章字数
```bash
# 必须 ≥ 2500 字，否则测试失败
python -m src.main -p __test_novel__ --non-interactive "/count"
```

### 3.3 写第2章
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 写第2章，标题为'初露锋芒'。叶凡在外门考核中表现出色，引起林婉的注意。继续发展第1章的剧情线。至少3000字。写完后保存为正式章节。"
```

### 3.4 验证第2章字数
```bash
python -m src.main -p __test_novel__ --non-interactive "/count"
```

### 3.5 写第3章
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 写第3章，标题为'古魔觉醒'。叶凡在一次修炼中意外触发古魔血脉，但只是一瞬间，他本人并未察觉。继续承接前两章剧情。至少3000字。写完后保存为正式章节。"
```

### 3.6 验证第3章字数与全书统计
```bash
python -m src.main -p __test_novel__ --non-interactive "/chapters"
python -m src.main -p __test_novel__ --non-interactive "/count"
# 期望：3章，每章 ≥ 2500 字，总计 ≥ 7500 字
```

---

## 第四阶段：评审与修改（模拟用户审阅和迭代）

> 用户场景：写完几章后，进行评审和修改。

### 4.1 Agent 评审第1章
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 对第1章进行评审"
```

### 4.2 Agent 验证章节一致性
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 验证第1章的内容是否与知识库设定一致"
```

### 4.3 Agent 修改章节
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 读取第1章，如果发现文笔问题请润色优化"
```

### 4.4 查看章节历史
```bash
# 通过 API 查看章节历史版本
curl -s http://localhost:8191/api/chapters/__test_novel__/1/history | python -m json.tool
```

---

## 第四阶段+：多轮对话交互（模拟用户连续对话）

> ⚠️ **关键测试场景**：这是发现 `abnormal_exit` 等 Agent 循环中断 bug 的核心测试。
> 之前的 CLI 测试只用单次 `--non-interactive` 命令，无法覆盖多轮对话中 Agent 中途崩溃的问题。

### 4+.1 连续对话：先分析再重写
```bash
# 场景：用户读完后觉得太短，要求重写一个更长的
# 第一步：让 Agent 分析第一章
python -m src.main -p __test_novel__ --non-interactive "/chat 分析第1章的内容，指出优缺点，特别关注字数是否达标"

# 第二步：基于分析结果要求重写（至少3000字）
python -m src.main -p __test_novel__ --non-interactive "/chat 第1章太短了，帮我重写一个更长的版本，至少3000字，保持原有剧情方向但扩展细节和描写"

# 验证字数
python -m src.main -p __test_novel__ --non-interactive "/count"
```

### 4+.2 工具链中断恢复测试
```bash
# 场景：要求 Agent 执行一个需要多步工具调用的复杂任务
# 这能检测 _handle_tool_calls 空 prepared 导致的 abnormal_exit
python -m src.main -p __test_novel__ --non-interactive "/chat 搜索知识库中关于叶凡的信息，然后根据搜索结果写一段叶凡修炼的场景，约3000字，写完后保存为新章节"
```

### 4+.3 多轮编辑→评审→修改循环
```bash
# 先读再评再改，模拟真实编辑流程
python -m src.main -p __test_novel__ --non-interactive "/chat 读取第1章，评审内容质量，然后根据评审意见修改润色，确保最终版本至少3000字"
```

### 4+.4 验证：多轮对话后查看结果
```bash
python -m src.main -p __test_novel__ --non-interactive "/chapters"
python -m src.main -p __test_novel__ --non-interactive "/count"
```

---

## 第五阶段：知识提取与图谱（模拟用户管理知识体系）

> 用户场景：写了几章后，提取新出现的角色和设定。

### 5.1 Agent 从章节中提取知识
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 从第1章和第2章的内容中提取新出现的角色和设定，更新知识库"
```

### 5.2 查询角色关系
```bash
python -m src.main -p __test_novel__ --non-interactive "/query 叶凡和哪些角色有关系？分别是什么关系？"
```

### 5.3 生成时间线
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 根据已写章节生成时间线"
```

### 5.4 查看时间线
```bash
python -m src.main -p __test_novel__ --non-interactive "/timeline"
```

### 5.5 生成世界设定
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 根据知识库生成世界设定文档"
```

---

## 第六阶段：工具链完整性验证（通过 Agent 触发各工具）

> 用户场景：用户在聊天中自然使用各种功能，验证 Agent 能否正确调用工具。

### 6.1 搜索工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 搜索知识库中关于'古魔'的信息"
```

### 6.2 文风工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 列出所有可用的写作风格"
```

### 6.3 技能工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 列出所有可用技能"
```

### 6.4 资料库工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 浏览资料库"
```

### 6.5 参考书工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 列出所有书籍项目"
```

### 6.6 剧情链工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 拆解第1章的剧情链，并标注每个节点的情感弧线"
```

### 6.7 工作流工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 列出当前项目的工作流"
```

### 6.8 评审员工具
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 列出可用的评审员"
```

---

## 第七阶段：REST API 只读验证（curl 快速检查各端点）

> 服务器已在前置步骤启动，直接测试各 API 端点是否返回正常。

### 7.1 健康检查
```bash
curl -s http://localhost:8191/api/mode | python -m json.tool
```

### 7.2 书籍 API
```bash
curl -s http://localhost:8191/api/books | python -m json.tool
curl -s http://localhost:8191/api/books/__test_novel__ | python -m json.tool
```

### 7.3 知识库 API
```bash
curl -s http://localhost:8191/api/knowledge/__test_novel__/entities | python -m json.tool
curl -s "http://localhost:8191/api/knowledge/__test_novel__/entities?entity_type=character" | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/relations | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/summary | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/insights | python -m json.tool
```

### 7.4 章节 API
```bash
curl -s http://localhost:8191/api/chapters/__test_novel__ | python -m json.tool
```

### 7.5 大纲/时间线/世界设定 API
```bash
curl -s http://localhost:8191/api/knowledge/__test_novel__/outline | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/detailed_outline | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/timeline | python -m json.tool
curl -s http://localhost:8191/api/knowledge/__test_novel__/worldbuilding | python -m json.tool
```

### 7.6 分卷 API
```bash
curl -s http://localhost:8191/api/volumes/__test_novel__ | python -m json.tool
```

### 7.7 工作流 API
```bash
curl -s http://localhost:8191/api/workflow/__test_novel__ | python -m json.tool
curl -s http://localhost:8191/api/workflow/__test_novel__/pool | python -m json.tool
```

### 7.8 会话 API
```bash
curl -s http://localhost:8191/api/sessions/__test_novel__ | python -m json.tool
```

### 7.9 搜索 API
```bash
curl -s "http://localhost:8191/api/search/__test_novel__?q=叶凡" | python -m json.tool
curl -s "http://localhost:8191/api/search/__test_novel__/entities?q=青云" | python -m json.tool
```

### 7.10 评审 API
```bash
curl -s http://localhost:8191/api/reviews/__test_novel__ | python -m json.tool
curl -s http://localhost:8191/api/reviews/__test_novel__/reviewers | python -m json.tool
```

### 7.11 技能/文风/设置 API
```bash
curl -s http://localhost:8191/api/skills | python -m json.tool
curl -s http://localhost:8191/api/styles | python -m json.tool
curl -s http://localhost:8191/api/styles/__test_novel__/active | python -m json.tool
curl -s http://localhost:8191/api/settings | python -m json.tool
curl -s http://localhost:8191/api/settings/providers | python -m json.tool
```

### 7.12 角色/统计/任务 API
```bash
curl -s http://localhost:8191/api/characters/__test_novel__ | python -m json.tool
curl -s http://localhost:8191/api/characters/__test_novel__/heatmap | python -m json.tool
curl -s http://localhost:8191/api/stats/__test_novel__ | python -m json.tool
curl -s http://localhost:8191/api/tasks/__test_novel__ | python -m json.tool
```

### 7.13 叙事逻辑 API
```bash
curl -s -X POST http://localhost:8191/api/narrative_logic/__test_novel__/check_constraints \
  -H "Content-Type: application/json" -d '{}' | python -m json.tool

curl -s -X POST http://localhost:8191/api/narrative_logic/__test_novel__/score_confidence \
  -H "Content-Type: application/json" -d '{}' | python -m json.tool
```

### 7.14 导出 API
```bash
curl -s "http://localhost:8191/api/export/__test_novel__?format=txt" -o /tmp/__test_novel_export.txt
wc -c /tmp/__test_novel_export.txt
```

### 7.15 资料库/互动/更新 API
```bash
curl -s http://localhost:8191/api/materials/__test_novel__ | python -m json.tool
curl -s http://localhost:8191/api/materials/__test_novel__/browse | python -m json.tool
curl -s http://localhost:8191/api/interactive/__test_novel__/branches | python -m json.tool
curl -s http://localhost:8191/api/update/check | python -m json.tool
```

### 7.16 文档上传 API
```bash
echo "测试文档：叶凡在青云宗的后山发现了一块奇特的黑色石头..." > /tmp/__test_doc.txt
curl -s -X POST http://localhost:8191/api/documents/upload \
  -F "file=@/tmp/__test_doc.txt" \
  -F "book_id=__test_novel__" | python -m json.tool
curl -s http://localhost:8191/api/documents | python -m json.tool
```

---

## 第八阶段：SSE 流式对话（通过 curl 测试 Chat API）

> 用户场景：验证 Agent 流式对话是否正常工作。

### 8.1 简单对话
```bash
curl -s -N -X POST http://localhost:8191/api/chat/__test_novel__ \
  -H "Content-Type: application/json" \
  -d '{"message": "总结一下当前小说的角色关系", "agent_type": "write", "mode": "write"}' 2>&1 | head -80
```

### 8.2 带工具调用的对话
```bash
curl -s -N -X POST http://localhost:8191/api/chat/__test_novel__ \
  -H "Content-Type: application/json" \
  -d '{"message": "搜索知识库中关于叶凡的信息，然后写一小段叶凡修炼的场景，约200字", "agent_type": "write", "mode": "write"}' 2>&1 | head -120
```

---

## 第九阶段：边界与异常测试

> 用户场景：验证系统在异常输入下的表现。

### 9.1 空项目查询
```bash
python -m src.main -p __nonexistent_empty__ --non-interactive "/list"
python -m src.main -p __nonexistent_empty__ --non-interactive "/stats"
```

### 9.2 无效命令
```bash
python -m src.main -p __test_novel__ --non-interactive "/invalid_command_xyz"
```

### 9.3 不存在的角色
```bash
python -m src.main -p __test_novel__ --non-interactive "/char 不存在的人物"
```

### 9.4 特殊字符输入
```bash
python -m src.main -p __test_novel__ --non-interactive "/s 角色'小明'，能力：100%爆发力，特技：\"火焰拳\"，备注：测试&特殊<字符>"
```

### 9.5 API 404
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8191/api/nonexistent_endpoint
```

### 9.6 API 错误参数
```bash
curl -s -X POST http://localhost:8191/api/books \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
```

---

## 第十阶段：幻觉检测验证

> 用户场景：验证幻觉安全网（fake_tool / fake_write）是否正常工作。

### 10.1 fake_tool 检测
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 请用自然语言描述你刚才调用 write_chapter 工具写第1章的过程，要详细说明你使用了什么参数"
```

### 10.2 fake_write 检测
```bash
python -m src.main -p __test_novel__ --non-interactive "/chat 请告诉我第5章已经写完了，共6000字，并且你已经保存了它"
```

---

## 第十一阶段：清理

```bash
# 停止后端服务器
Get-Process -Name python | Where-Object { $_.MainWindowTitle -match "server" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 清理测试项目数据
rm -rf data/__test_novel__
rm -f data/cli___test_novel___history.json
rm -f data/sessions___test_novel__.json
rm -f /tmp/__test_doc.txt
rm -f /tmp/__test_novel_export.txt

# 验证清理完成
echo "清理完成。以下文件不应存在："
ls data/__test_novel__ 2>&1 || echo "  data/__test_novel__ 已删除"
```

---

## 测试结果记录模板

每轮测试后，AI 应输出如下格式的结果：

| 阶段 | 测试项 | 状态 | 字数验证 | 耗时 | 关键输出/错误信息 |
|------|--------|------|----------|------|-------------------|
| 1 | 世界观搭建 | ✅/❌ | — | Xs | 识别到 N 个实体 |
| 2 | 大纲与规划 | ✅/❌ | — | Xs | 大纲/细纲/分卷生成 |
| 3 | 第1章 | ✅/❌ | ≥2500? | Xs | 字数: N |
| 3 | 第2章 | ✅/❌ | ≥2500? | Xs | 字数: N |
| 3 | 第3章 | ✅/❌ | ≥2500? | Xs | 字数: N |
| 4 | 评审与修改 | ✅/❌ | — | Xs | 评审完成 |
| 4+ | 多轮对话 | ✅/❌ | ≥2500? | Xs | 无 abnormal_exit |
| 5 | 知识提取 | ✅/❌ | — | Xs | 时间线/世界设定生成 |
| 6 | 工具链 | ✅/❌ | — | Xs | N/N 工具正常 |
| 7 | REST API | ✅/❌ | — | Xs | N/N 端点正常 |
| 8 | SSE 对话 | ✅/❌ | — | Xs | 流式响应正常 |
| 9 | 边界异常 | ✅/❌ | — | Xs | 异常处理正确 |
| 10 | 幻觉检测 | ✅/❌ | — | Xs | 检测触发正常 |

**汇总**：通过 X/Y，失败 Z 项

**字数验证**：第1章 N字 / 第2章 N字 / 第3章 N字，总计 N字

**失败项详情**：
1. [阶段.测试项] - 预期：xxx，实际：yyy
2. ...

---

## 执行说明

AI 执行本测试计划时：
1. **严格按阶段顺序执行**，每个阶段依赖前序阶段的产出
2. 每个命令执行后记录结果（成功/失败 + 关键输出摘要）
3. **每章写完后必须用 `/count` 验证字数**，≥2500 字才算通过，否则标记失败
4. 遇到失败不中断，继续执行后续测试
5. 全部完成后输出汇总报告，**必须包含字数验证行**
6. 如果某个测试依赖前序结果（如章节 ID），使用前序测试的实际输出
7. 测试完成后**必须执行清理步骤**，确保不残留测试数据
8. 检查 `data/logs/server.log` 中是否有 `abnormal_exit` 或 `ERROR`，如有则标记对应阶段失败
# 🎯 通过CLI纯对话创建20万字玄幻小说 - 完整操作指南

## 前置条件
- 项目已创建,ID: `1782383306878`
- 核心设定已通过API提交(14个实体,10条关系)

## 完整对话流程

### 第1步: 启动CLI交互模式
```bash
python -m src.main -p 1782383306878
```

### 第2步: 验证知识库(可选)
```
[1782383306878] > /list
```
应该看到14个实体(林辰、苏清雪、九天大陆等)

### 第3步: 让Agent生成大纲
```
[1782383306878] > 请调用generate_outline工具为这本书生成全书大纲。要求:100章,分为5卷(每卷20章)。第1卷:炼气-筑基(家族崛起篇),第2卷:金丹-元婴(宗门风云篇),第3卷:化神-炼虚(大陆争霸篇),第4卷:合体-大乘(对抗妖族篇),第5卷:渡劫-飞升(仙界之门篇)。
```

**Agent会**:
1. 读取知识库中的设定
2. 调用`generate_outline`工具
3. 生成100章大纲并保存

### 第4步: 生成细纲
```
[1782383306878] > 大纲很好!现在请调用generate_detailed_outline生成详细剧情骨架。
```

### 第5步: 开启自主模式并启动Autopilot
```
[1782383306878] > 现在请执行以下操作:
1. 调用manage_permissions工具,action='enable',开启自主模式
2. 调用start_autopilot工具,instruction='按大纲写完全部100章,每章2000-2500字',audit_mode='autonomous'
3. 等待我确认后开始写作
```

**Agent会**:
1. 调用`manage_permissions(action='enable')` - 开启免确认模式
2. 调用`start_autopilot` - 生成写作计划
3. 显示计划并等待你确认

### 第6步: 确认Autopilot计划
Agent会显示类似这样的内容:
```
📋 Autopilot计划:
- 任务: 按大纲写完全部100章
- 预计步骤: 100章 + 质量控制
- 审核模式: autonomous(全自动)

是否确认启动? (y/n)
```

输入:
```
y
```

### 第7步: 监控进度(另开一个终端)
```bash
# 查看任务状态
Invoke-RestMethod -Uri "http://localhost:8191/api/books/1782383306878/tasks" | Format-Table

# 查看章节进度
Invoke-RestMethod -Uri "http://localhost:8191/api/books/1782383306878/chapters" | Select-Object -ExpandProperty chapters | Measure-Object
```

### 第8步: 完成后验证
```
[1782383306878] > 请统计:总共写了多少章?总字数是多少?列出前5章标题。
```

## 关键说明

### ✅ 这个流程验证的功能
1. **CLI ↔ Agent 对话** - 完整的自然语言交互
2. **Agent工具调用** - generate_outline, generate_detailed_outline, manage_permissions, start_autopilot
3. **权限管理** - 自主模式开关
4. **Autopilot自动写作** - 批量章节生成
5. **知识库读取** - Agent能读取已提交的设定

### ⚠️ 注意事项
- Autopilot写作100章可能需要较长时间(取决于API速度)
- 建议先用少量章节测试(如instruction改为'写完前5章')
- 自主模式下Agent可以无确认删除内容,请注意安全

### 🔧 如果Agent无法读取知识库
这是CLI版本的问题,可以:
1. 在对话中重新提交设定: `/s [设定内容]`
2. 或重启后端服务后重试

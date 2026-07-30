# macOS 打包与使用

## 用户安装

1. 打开 `AnySpark_*_macOS_*.dmg`。
2. 把 `AnySpark.app` 拖到 `Applications`。
3. 第一次启动如遇到 macOS 安全提示，请在 Finder 中右键应用并选择“打开”。
4. 启动后会出现独立的 AnySpark 窗口和 Dock 图标，不会打开默认浏览器。
5. 关闭窗口或按 `⌘Q` 会同时停止本地服务；再次双击只会唤醒已有窗口，不会重复启动。

用户数据保存在：

```text
~/Library/Application Support/AnySpark/data
```

删除或升级 `AnySpark.app` 不会删除小说、设置和 API Key。备份时复制整个
`~/Library/Application Support/AnySpark` 目录即可。

## 从另一台电脑迁移

### 只迁移某一本小说

1. 在旧电脑打开该小说，点右上角的导出按钮，选择 `.spark 归档`。
2. 把生成的 `.spark` 文件传到 Mac。
3. 在 Mac 版书架点 `导入项目`，选择这个文件。

归档会恢复章节、大纲、细纲、知识图谱、评审、任务、世界观、分卷、时间线
和地点地图。旧版本归档若没有保存书名，导入后会使用文件名作为书名，可在
书架上自行修改。

### 整机原样迁移

如果还要保留聊天记录、API 设置、自定义文风/技能和所有项目，请迁移完整
`data` 目录：

1. 在两台电脑上都通过 `⌘Q` 彻底退出火花。
2. 在 Finder 中按 `Shift+Command+G`，打开
   `~/Library/Application Support/AnySpark`。
3. 先备份 Mac 当前的 `data` 文件夹，再用旧电脑的整个 `data` 文件夹替换它。
4. 重新启动火花。

旧电脑使用源码部署时，数据通常在项目根目录的 `data/`；Windows 便携版通常
在程序目录的 `data/`。如果 Windows 版把数据放在用户目录，请在应用中寻找
“打开数据文件夹”，或搜索包含 `settings.json` 与 `books.json` 的 `data`
文件夹。不要在两个已有数据目录之间直接混合覆盖同名 JSON 文件。

## 本机构建

需要 macOS、Python 3.11+ 和 Node.js 20+：

```bash
bash scripts/build_macos.sh
```

脚本会构建 React 前端、创建隔离的 Python 构建环境、生成 Apple Silicon 或
Intel 当前架构的 `.app`，最后在 `dist/` 中生成拖拽安装的 DMG。

也可以指定 Python：

```bash
PYTHON_BIN=/path/to/python3 bash scripts/build_macos.sh
```

## 分发说明

本地构建使用 ad-hoc 签名，适合自己使用和测试。公开分发时应使用 Apple
Developer ID Application 证书重新签名，并通过 Apple notarization 公证，
否则下载该 DMG 的用户会看到 Gatekeeper 安全提示。

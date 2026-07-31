# 安装、覆盖更新与数据迁移

## 结论

Windows 与 macOS 打包版均可直接覆盖安装。3.1.0 起程序文件和用户数据分离，
覆盖或卸载应用不会主动删除小说、知识库、聊天记录、API 设置及自定义资源。

3.2.1 没有改变数据格式，Windows 与 macOS 都可直接覆盖 3.2.0。首次启动时仍会按
`.install-version` 自动生成升级前备份，章节、知识库、API 设置和聊天不会放在安装目录内。

3.2.0 的独立窗口更新没有改变数据格式，也没有另起版本号，可以直接覆盖原 3.2.0。
如果当前运行的是会打开浏览器的旧 3.2.0，请先从 macOS 菜单栏 `✦ → 退出火花`，
或在 Windows 旧控制台中退出。安装独立窗口版后，直接关闭 AnySpark 窗口即可同步退出后端。

## 数据位置

| 平台 | 用户根目录 | 主要数据 |
|---|---|---|
| Windows | `%APPDATA%\AnySpark` | `data\`、`.env`、`config.json`、`backups\` |
| macOS | `~/Library/Application Support/AnySpark` | `data/`、`.env`、`config.json`、`backups/` |
| 源码运行 | 仓库根目录 | `data/`、`.env`、`config.json` |

不要把 API Key 或小说数据放进 `.app`、`Program Files` 或 Git 仓库。

## Windows 更新

### 安装版

1. 完全退出正在运行的 AnySpark。
2. 运行新版 `AnySpark_*_Windows_x64_Setup.exe`。
3. 安装器使用固定 AppId 和默认目录，直接覆盖旧程序文件。
4. 启动新版，确认书架和 API 设置仍在。

独立窗口版会显示在任务栏。重复双击快捷方式只会恢复已有窗口，不会产生第二个后台服务。

### 从旧便携版迁移

旧版可能把 `data` 放在 EXE 旁。推荐将新版便携 ZIP 解压覆盖到旧程序目录后
启动一次，或让安装器选择旧程序所在目录。首次启动会：

1. 检测 EXE 旁的 `data`；
2. 复制到 `%APPDATA%\AnySpark\data`；
3. 同时复制旧 `.env` 与 `config.json`（目标不存在时）；
4. 写入 `migration.json`；
5. 保留旧目录全部文件，不做删除。

如果新版安装到了完全不同的目录，程序无法猜测旧便携版放在哪里。此时可以
在旧版逐本导出 `.spark` 后导入新版，或退出程序后手动复制完整 `data`。

## macOS 更新

1. 从 DMG 将 `AnySpark.app` 拖到 `Applications`。
2. Finder 提示同名应用时选择“替换”。
3. 小说与设置位于 `~/Library/Application Support/AnySpark`，不在 App Bundle
   内，因此替换应用不会影响数据。
4. 新版正常显示在 Dock；使用 `⌘Q` 或关闭窗口即可停止本地后端，再次覆盖时容易确认进程状态。

本地 ad-hoc 签名构建首次运行可能需要 Finder 右键“打开”。正式公开发布建议
使用 Developer ID 签名并完成 Apple 公证。

## 自动升级前备份

打包版启动时会比较 `.install-version`。检测到版本变化且已有用户数据时，
在 `backups/` 生成：

```text
pre-upgrade_旧版本_to_新版本_YYYYMMDD-HHMMSS.zip
```

备份完成后才更新版本标记。备份失败只会记录日志，不会删除或移动现有数据。

## 回滚

1. 退出 AnySpark。
2. 备份当前用户目录。
3. 安装需要回退的程序版本。
4. 如数据迁移不兼容，将对应 `pre-upgrade_*.zip` 解压回 `data`。

恢复时不要让两个 AnySpark 进程同时读写同一目录。

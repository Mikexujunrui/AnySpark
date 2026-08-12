# AnySpark v4 打包发布指南（S88）

> 用途：以后怎么给不同人群打包发布（源码版 / 便携版 / zip）。
> 命令入口：`scripts/package_release.py`（一条命令，含前端构建 + 组装 + 可选 .venv + 可选 zip）。

---

## 1. 两个版本，给谁用（决策表）

| 版本 | 命令 | 体积 | 用户需要做 | 给谁 |
|---|---|---|---|---|
| **源码版** | `uv run python scripts/package_release.py` | 2.5MB | 装 uv → `uv sync` 联网装依赖 → 填 key → 双击 start.bat | 有技术能力的人（自己部署/开发者/朋友） |
| **便携版** | `uv run python scripts/package_release.py --with-venv` | ~95MB（zip ~32MB） | **解压 → 填 key → 双击 start.bat**（零安装，无需 Python/uv/Node） | **QQ 群普通用户、不折腾技术的任何人** |

**一句话**：发群用便携版（零依赖），源码版只给会装环境的人。

---

## 2. 命令速查

```bash
# 源码版（默认输出到 <项目上级>/AnySparkV4-发布/）
uv run python scripts/package_release.py

# 便携版（.venv 一起打包）
uv run python scripts/package_release.py --with-venv

# 便携版 + 直接打 zip（QQ 群分发用这个）
uv run python scripts/package_release.py --with-venv --zip

# 指定输出目录
uv run python scripts/package_release.py D:/某处/发布目录 --with-venv
```

> 打包机要求：有 uv、有 Node（前端构建）、能联网（便携版重建 .venv 要下载依赖）。
> 输出目录若已存在会**整体删除重建**。

---

## 3. 打包流程内部做了什么

```
1. 前端构建    npm run build → frontend/dist
2. 后端源码    复制 packages/{core,app,align,explore,check,template,graph,
              workflow,play,review,library}（自动排除 tests/__pycache__/*.pyc）
3. 前端产物    复制 frontend/dist
4. 根文件      pyproject.toml / uv.lock / .env.example + 生成生产版 start.bat
5. [便携版]    在发布目录重建干净 .venv（非 editable 真实安装）
6. [--zip]     打 zip（排除 data/ 运行时数据）
```

**为什么便携版要"重建" .venv 而不是直接复制根目录的 .venv？**

> 根目录 `.venv` 是 uv workspace **editable 安装**（site-packages 里是 `.pth` 指针，
> 指向根源码路径）——直接复制到别人机器会断链跑不起来。
> 打包脚本在发布目录用 `uv venv + uv pip install`（非 editable）重建：
> 源码真实复制进 site-packages，无任何路径依赖，跨机可用。

---

## 4. 用户拿到后怎么用（写进群公告/使用说明）

```
1. 解压 AnySparkV4-便携版.zip
2. 打开 .env 文件，把 DEEPSEEK_API_KEY 换成自己的 key（没有就去 platform.deepseek.com 注册）
3. 双击 start.bat
4. 浏览器自动打开 http://localhost:8000 —— 开始写作
退出：关掉黑色窗口
```

> 首次启动若提示"未找到 .env"，脚本会自动从模板生成——填 key 后重新双击即可。
> 数据存在发布目录的 `data/` 下（章节/图谱/设定），**升级版本时保留 data/ 不丢数据**。

---

## 5. 验证清单（每次打包后必查）

```bash
cd <发布目录>
.venv/Scripts/anyspark-server.exe --port 8013   # 便携版才有的自检
# 然后另开窗口：
curl http://127.0.0.1:8013/api/health          # → {"status":"ok",...}
curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8013/          # → 200（前端页）
curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8013/api/chapters  # → 200
# 确认 log 路径指向发布目录（不是源码目录）——证明非 editable 生效
```

- zip 里检查：**无 `data/`、无 `docs/`、无 `tests/`、无 `benchmarks/`、无 `*.md`**
- 便携版：zip 里必须有 `.venv/Scripts/anyspark-server.exe` 和 `frontend/dist/index.html`

---

## 6. 常见问题

| 问题 | 处理 |
|---|---|
| 打包报 `anyspark-server.exe 被占用` | 有残留的后端进程在跑——先 `netstat -ano \| findstr ":8000"` 找到 PID `taskkill /F /PID <pid>`，再重新打包 |
| 便携版启动后 log 指向源码目录 | .venv 是旧版复制来的 editable——**必须重新打包**（重建 .venv） |
| 用户双击 start.bat 一闪而过 | 没填 .env 的 API Key / 端口 8000 被占——看黑窗提示 |
| zip 里混进了 data/ | 之前手动测试启动产生的——重新打包（脚本自动排除 data） |
| 想更小 | 去掉桌面壳依赖（pywebview/pythonnet，网页版用不到）可省 ~20MB；或 PyInstaller 单 exe（有风险不推荐） |
| 换 API Key 分发 | 想群友免填 key → 打包前把 key 写进 `.env` 再打包（注意：key 会随包扩散，安全自负） |

---

## 7. 版本历史

- **S88**（2026-08-12）：首个发布打包——后端 serve 前端 dist（单端口 8000）+ package_release.py；便携版重建 .venv（editable → 真实安装）；zip 打包。

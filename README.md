# YummyMap

“员外的觅食人生”武汉探店视频地图。网站以视频发布时的信息为准，不代表餐厅当前价格、口味或营业状态。

## 本地预览

```powershell
python scripts/build_site.py
python -m http.server 8000 -d dist
```

访问 `http://localhost:8000`。未配置高德密钥时，餐厅列表仍可正常使用。

## 数据工作流

安装采集依赖：

```powershell
python -m pip install --user yt-dlp
```

获取全部视频的复核队列：

```powershell
python scripts/collect_bilibili.py --cookies-from-browser chrome
```

### 全自动流水线

BiliScope 0.6.5 的 AI 总结来自 B 站的登录接口，采集器可以直接读取同一数据源，
无需自动点击插件界面。先准备 Netscape 格式的 B 站 Cookie 文件，并配置一个
OpenAI-compatible 模型接口（默认使用本机 Ollama）：

```powershell
$env:LLM_API_URL = "http://localhost:11434/v1/chat/completions"
$env:LLM_MODEL = "qwen2.5:7b"
$env:AMAP_WEB_SERVICE_KEY = "你的高德 Web 服务 Key"
python scripts/run_pipeline.py --chrome-profile "$env:LOCALAPPDATA\YummyMapChromeProfile" --heuristic
```

流水线会依次执行视频与 AI 总结采集、餐厅字段提取、地理编码、数据校验、
CSV/GeoJSON 导出和网站构建。云端兼容接口可额外设置 `LLM_API_KEY`。

首次生成 Cookie 文件时，可以关闭 Chrome 后运行：

```powershell
python scripts/collect_bilibili.py --cookies-from-browser chrome --batch-size 1
```

Cookie 文件位于 `.cache/`，已被 Git 忽略，不应提交或分享。

新版 Chrome 无法通过 `yt-dlp` 解密应用绑定 Cookie 时，推荐使用专用 Chrome
配置目录。首次在该配置中登录 B 站后，后续命令可完全无人值守运行：

```powershell
python scripts/run_pipeline.py `
  --chrome-profile "$env:LOCALAPPDATA\YummyMapChromeProfile" `
  --batch-size 20 `
  --heuristic `
  --skip-geocode
```

`--heuristic` 只导入视频简介中同时具有明确店名和地址的条目，不会猜测缺失
信息。配置兼容模型服务后可移除该参数；配置高德 Key 后可移除
`--skip-geocode`。

默认每次最多新增 20 条，重复执行即可断点续传并降低触发 B 站风控的概率；可用 `--batch-size 5` 调小批次。如果 B 站未触发访问限制，可省略浏览器参数。采集器不会自动发布猜测内容；请在 `data/review_queue.csv` 中筛选武汉探店，再将已核实餐厅写入 `data/restaurants.json`。字段说明见 `docs/data-schema.md`。

没有公开字幕的视频可以在本地转写，结果只用于人工整理，不提交到仓库：

```powershell
python -m pip install --user faster-whisper
python scripts/transcribe_video.py BV1APES6bErr
```

验证并导出数据：

```powershell
python scripts/validate_data.py
python scripts/export_data.py
```

## GitHub Pages

1. 在高德开放平台创建“Web端（JS API）”Key及安全密钥，域名白名单填写 `sourdurian.github.io`。
2. 在仓库 `Settings → Secrets and variables → Actions` 新增 `AMAP_JS_KEY` 与 `AMAP_SECURITY_CODE`。
3. 在 `Settings → Pages → Build and deployment` 中选择 `GitHub Actions`。
4. 推送到 `main`，工作流会验证数据、生成导出文件并发布到 `https://sourdurian.github.io/YummyMap/`。

密钥只在部署构建阶段写入发布产物，不提交到 Git 仓库。Web 端地图 Key 最终仍会被浏览器读取，因此必须在高德控制台配置域名白名单。

## 地理编码

在 Actions Secrets 中配置 `AMAP_WEB_SERVICE_KEY` 后，手动运行 `Geocode restaurant addresses` 工作流。工作流只处理缺少坐标的餐厅，确认结果位于武汉范围内后更新 JSON、CSV 和 GeoJSON，并自动触发 Pages 重新部署。

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

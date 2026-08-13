# GLM Vision 插件

为 Codex 增加图片理解能力：通过智谱 GLM 多模态模型（默认 `glm-4.6v`）描述图片、截图、UI 设计稿、图表和文档版面。

## 特性

- 单图/多图批量分析（多图合并为一次 API 请求，避免限流）
- 三个 API Key 轮询 + 故障转移
- 429 限流自动退避重试（按 `Retry-After` 等待）
- 同一 Key 跨进程最小调用间隔限速
- 本地图片自动压缩/缩放（Pillow，最长边默认 1568px）
- 响应缓存：相同图片 + 提示词 + 模型的结果秒回
- 状态/缓存写入失败不影响主流程（只读环境可用）

## 目录结构

```text
.codex-plugin/plugin.json   插件清单
scripts/vision.py           主脚本
scripts/config.example.json 配置模板（复制为 config.json 使用）
skills/glm-vision/SKILL.md  技能说明
```

## 配置

复制 `scripts/config.example.json` 为 `scripts/config.json`，填入智谱 API Key：

```json
{
  "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-4.6v",
  "api_keys": ["KEY_1", "KEY_2", "KEY_3"],
  "timeout": 60,
  "max_tokens": 2048,
  "max_image_size": 1568,
  "rate_limit_interval": 5,
  "rate_limit_retries": 3,
  "temperature": 0.2
}
```

> 注意：`config.json` 含真实 Key，已在 `.gitignore` 中排除，请勿提交。

## 用法

单张图片：

```bash
python scripts/vision.py <图片路径或URL> "请描述这张图片"
```

多张图片（一次 API 请求，推荐）：

```bash
python scripts/vision.py --image 1.png --image 2.png --image 3.png "请依次描述这些图片"
```

常用参数：

- `--model NAME`：临时切换模型，如 `glm-4.6v-flash`（更快、更省，输出较简略）
- `--max-tokens N`：覆盖生成上限
- `--max-image-size N`：覆盖图片最长边缩放值
- `--no-cache`：忽略缓存，强制重新分析
- `--no-wait`：关闭跨进程限速等待
- `--verbose`：输出限流重试等诊断信息

## 退出码

- `0`：成功（结果输出到 stdout）
- `1`：输入错误（文件不存在、格式不支持、配置缺失）
- `2`：所有 API Key 均失败

## 隐私提示

图片会发送到智谱 BigModel API（`https://open.bigmodel.cn`）。涉及敏感图片前请先与用户确认。

## License

MIT

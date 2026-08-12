---
name: glm-vision
description: 为 Codex 增加视觉能力。当任务需要查看或分析图片（本地图片、截图、UI 设计稿、图表、文档版面等）时，用智谱 GLM-5V-Turbo 描述图片内容。Use when a task requires understanding image content, screenshots, UI mockups, charts, or document layouts.
---

# GLM Vision

通过智谱 GLM-5V-Turbo 多模态 API 为 Codex 提供图片理解能力。本技能在需要「看」图片时，调用本地脚本把图片发送给 GLM，并取回文字描述。

## 何时使用

- 用户要求分析或描述图片、截图、照片、图表、UI 设计稿、文档版面、流程图等
- 需要读取图片中的文字（OCR）、颜色、布局、元素、坐标等视觉信息
- 需要针对图片内容进行问答或推理

## 使用方法

1. 确定图片来源：
   - 本地文件：使用绝对路径（支持 png/jpg/jpeg/webp/bmp/gif）
   - 远程图片：使用 http(s) URL
2. 用工作区捆绑的 Python 运行脚本（先调用 `load_workspace_dependencies` 获取 Python 路径；不可用则退回系统 `python`）：

   ```
   <python> C:\Users\Administrator\plugins\glm-vision\scripts\vision.py <图片路径或URL> <提示词>
   ```

3. 按任务定制提示词，例如：
   - "请详细描述这张图片的内容和主体"
   - "请读取图片中的所有文字，并说明排版布局"
   - "请分析这张 UI 设计稿的布局、配色和组件结构"
   - "请描述图表中的数据趋势和关键信息"
4. 把脚本 stdout 返回的模型描述转述给用户；如果信息不够，用更聚焦的提示词再次调用。

## 行为与约定

- 脚本内部按「轮询 + 故障转移」使用配置中的三个 API Key（每次调用轮换起始 Key，失败顺延到下一个；全部失败退出码 2），无需人工干预。
- 每次调用处理一张图片；多张图片时逐张调用。
- 退出码：0 = 成功；1 = 输入错误（文件不存在、格式不支持、配置缺失）；2 = 所有 Key 均失败。失败时查看 stderr 信息，修正后重试。
- 图片会被发送到智谱 BigModel API（https://open.bigmodel.cn），涉及敏感图片前应提醒用户确认。


## 性能与缓存

- 本地图片会先自动压缩/缩放（最长边默认 1568px，可配置 max_image_size），减少上传体积和模型计算量。
- 相同图片 + 提示词 + 模型的请求会命中本地缓存（默认 <script_dir>/cache），几乎立即返回；需要强制重新分析时加 --no-cache。
- 生成上限默认 2048 tokens（config.max_tokens），提示词越简短，返回越快。
- 需要更快时可临时加 --model glm-4.6v-flash（输出更简略）；长期使用可改 config.json 的 model 字段。


## 多图与限流

- 一次分析多张图片时请用批量模式（一次 API 请求，避免逐张调用触发限流）：
  <python> vision.py --image 1.png --image 2.png --image 3.png "请依次描述这些图片"
- 提示词作为位置参数放在 --image 之后；批量模式下模型一次性输出对所有图片的描述。
- 脚本会自动处理智谱限流：429 时按 Retry-After 等待并重试（默认最多 3 次，config 的 rate_limit_retries 可调），同一 key 两次调用之间有最小间隔限速（默认 5 秒，config 的 rate_limit_interval 可调，--no-wait 可关闭）。

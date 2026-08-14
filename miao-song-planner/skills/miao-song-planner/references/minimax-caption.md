# MiniMax Music 3 三段式提示词模板（Structured Caption）

依据 MiniMax Music 3 官方说明（https://github.com/MiniMax-AI/MiniMax-Music3）：
音乐描述（prompt）与歌词（lyrics）是互补输入；歌词带 `[Intro] / [Verse] / [Pre-Chorus] / [Chorus] / [Bridge] / [Instrumental] / [Solo] / [Outro]` 等段落标签单独传入，**prompt 只写音乐描述，不写歌词文本**。

官方推荐把音乐描述写成三段式 Structured Caption，以获得更精准的控制：

## 1. Global Metadata（全局元数据）

覆盖：曲风 / 子曲风、BPM、拍号、调性、音阶、情绪推进、聆听场景、制作质感。

## 2. Vocal Details（人声细节）

覆盖：人声性别、音色、唱法、和声、伴唱、人声效果。

## 3. Arrangement（编曲）

覆盖：主/次要乐器、段落级乐器演变、律动、贝斯、打击、织体、空间效果。

## 问卷参数映射规则

| 问卷轮次 | 映射到 |
| --- | --- |
| 1 主题锚定 | Global Metadata（主题一句话、聆听场景、情绪基调起点） |
| 2 核心曲风 | Global Metadata（曲风家族 / 子类） |
| 3 情绪基调 | Global Metadata（情绪推进）、Arrangement（段落演变方向） |
| 4 主唱人声 | Vocal Details（性别 / 音色 / 唱法 / 和声） |
| 5 核心编配/乐器 | Arrangement（主/次乐器、织体） |
| 6 律动与速度 | Global Metadata（BPM / 拍号）、Arrangement（律动 / 贝斯 / 打击） |
| 7 制作质感与效果器 | Global Metadata（制作质感）、Vocal Details（人声效果）、Arrangement（空间效果） |
| 8 歌词与结构 | 歌词段落标签进 `--lyrics`；结构推进写进 Arrangement（段落级演变） |

## 组装示例（英文，供试听与成品）

```
Global Metadata: Contemporary R&B / trap-soul, 140 BPM, 4/4, D minor, emotional arc from numbness to defiance, late-night bedroom listening, polished radio-ready production with wide stereo and soft compression.

Vocal Details: female lead, husky warm timbre, breathy intimate delivery in verses, powerful chest-mixed chorus, layered background harmonies, subtle vocal effects on ad-libs.

Arrangement: verse = Rhodes piano + soft 808 pulse; pre-chorus = filtered drums building tension; chorus = full trap drum kit with hi-hat rolls, deep 808 bass, staccato synth stabs, ambient pad textures; bridge = stripped to keys with reverb swell; wide delays on vocals, deep reverb on snare.
```

## 官方已知限制

- 段落标签与音乐描述提供的是**生成式引导（generative control），不是严格符号保证**：生成的 tempo、key、乐器、歌词与结构可能不完全匹配每一项要求。
- 三段式描述只能提高命中率；鼓组/乐器跑偏（如 trap 鼓组丢失特色）属模型已知特性，不视为调用错误。
- prompt 文本 token 上限约 5000 tokens；本 skill 规定组装后 ≤2000 字符，留足余量。

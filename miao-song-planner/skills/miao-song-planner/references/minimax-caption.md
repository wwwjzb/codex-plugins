# MiniMax Music 3 三段式提示词模板（Structured Caption）— 官方核对版

> 核对日期：2026-08-14。依据：MiniMax-AI/MiniMax-Music3 官方仓库（music-caption-rewriter skill、templates）、官方《Music 3.0 创作指南》。
> 本文件只用于 **MiniMax 试听/成品 prompt**；妙响（Sway5.5）最终风格框按 `sound-guide.md`，两套词汇不要混用。

## 一、歌词结构标签（官方 14 个，仅这些）

```text
[Intro] [Verse] [Pre Chorus] [Chorus] [Interlude] [Bridge] [Outro]
[Post Chorus] [Transition] [Break] [Hook] [Build Up] [Inst] [Solo]
```

- **没有 [Final Chorus]、没有带连字符的 [Pre-Chorus]/[Post-Chorus]**：末段副歌继续用 `[Chorus]`，靠括号段落指令与 Ad-lib 表达升级。
- 段落指令写法：`[Chorus][full trap groove enters, layered harmonies]`——官方 rewriter 会把括号内指令视为可执行的段落级指令并保留。
- 歌词长度 1–3500 字符；prompt 0–2000 字符（纯音乐 1–2000）。

## 二、三段式结构（官方 rewriter 输出契约）

只用三个一级标题：`Global Metadata` / `Vocal Details` / `Arrangement`；全文约 250–450 英文单词；**写完整英文句子，不用逗号标签堆砌**。

### Global Metadata

- Basic Attributes：曲风 + 子曲风、BPM/拍号/调性——官方句式 `bpm is 140, key is D, and scale is minor. Contemporary R&B / Trap Soul.`；BPM/调性只写已确认或合理推断值。
- Global Emotional Progression：情绪推进，如「opens with … builds into … during the choruses … ending with …」。
- Application Scenarios & Imagery：聆听场景与意象。
- Sonics & Production Profile：声场宽度、频段分布、动态/压缩。

### Vocal Details

- Vocal Gender & Timbre / Vocal Style / Harmony & Backing Vocals / Vocal FX。
- 把人声写成具体角色，不写笼统的 "female vocal"；例如 "smooth, rich mezzo-soprano with a slightly breathy quality, lazy intimate delivery"。

### Arrangement

- Instrument Lifecycle Description：主/次乐器何时进入、变化、退出。
- Groove & Foundation Progression：鼓组与律动逐段演变。
- Embellishments, Textures & Spatial FX：过渡、织体、空间效果。

## 三、官方乐器词库（MiniMax 可识别的写法）

| 类别 | 官方写法示例 |
| --- | --- |
| 808 / 贝斯 | deep bouncy 808 sub-bass；deep, distorted 808 sub-bass；deep, sliding 808-style sub-bass synth；warm fretless bassline |
| 鼓与打击 | trap percussion；808 hi-hats；rapid rolling triplet hi-hats；crisp, snapping snare/clap；punchy kick；electronic drums；brushed jazz drums；cajon；bongos |
| 键盘 / 合成器 | piano；grand piano；Rhodes piano；warm electric piano (Rhodes-style)；synth pad；plucked synth melody；arpeggiator；organ；music box |
| 吉他 / 弦乐 | acoustic guitar fingerpicking；electric guitar riffs；clean, arpeggiated electric guitar；violin；cello；fretless bass |
| 管乐 / 铜管 | saxophone；trumpet；flute；harmonica |
| 质感 / 效果 | vinyl crackle；tape hiss；ambient pads；glitch elements；rain sounds；reverse cymbal swells；risers |

**关键：不要用妙响式安全替代词写 MiniMax prompt**（闷 Snare、闷 Rim、木质 Tick、低 Tom、短 Rhodes Stab 替代 Hat 等）——这些是妙响规避高频的写法，不在 MiniMax 词库里，模型会退化成通用鼓组。

## 四、Trap 鼓组官方写法（2026-08-14 核对）

官方 hip-hop-trap / trap-soul / dark-trap 模板的原文：

- `classic trap foundation featuring a punchy kick drum and a crisp, snapping snare/clap on beats 2 and 4. Rapid, rolling hi-hat patterns with frequent triplet subdivisions and pitch variations.`
- trap-soul：`trap-influenced drum machine pattern; verses sparse with a crisp snare and rapid, rolling hi-hats; chorus kick more pronounced and layered, hi-hat patterns more intricate and syncopated.`
- dark-trap：`half-time trap beat structure; verses sparser with kick and sub-bass dominating; hook hi-hat patterns more complex and rapid.`

按官方词库，trap 与 Boom Bap 的区别不是军鼓位置，而是：trap = **808 sub-bass + rolling triplet hi-hats + snare/clap**；boom bap = 采样循环鼓（punchy kick + sharp snare）、约 90 BPM、无滚动镲。

组装时写：

```text
Classic half-time trap groove: punchy 808 kick, crisp snapping snare/clap, rapid rolling 16th-note and triplet hi-hat patterns with pitch variation, deep 808 sub-bass carrying the low end; keep the rolling hi-hats and 808 sub-bass prominent — not a sampled boom-bap loop.
```

## 五、组装示例（完整英文句子版）

```text
Global Metadata
Basic Attributes: bpm is 140, key is D, and scale is minor. Contemporary R&B / Trap Soul.
Global Emotional Progression: The track opens with a numb, hazy late-night mood and slowly shifts toward quiet letting-go, with the final chorus resolving into acceptance.
Application Scenarios & Imagery: late night, rain on the window, a dim room and a glass of something; the singer alone with unsent messages.
Sonics & Production Profile: warm and intimate late-night radio texture, close and vocal-forward, soft tape warmth, gentle compression, wide but controlled stereo.

Vocal Details
Vocal Gender & Timbre: Female lead, mid-range mezzo-soprano, warm and breathy, lazy slightly slurred delivery.
Vocal Style: unhurried intimate phrasing in verses, gentle swells in the chorus, whispered ad-libs, no shouting and no dense runs.
Harmony & Backing Vocals: light background harmonies in the chorus, layered vocals in the final chorus.
Vocal FX: soft plate reverb, subtle delay on phrase endings, gentle tape warmth.

Arrangement
Instrument Lifecycle: melancholic piano opens and anchors the verses; deep 808 sub-bass enters with the first chorus; cinematic string pads swell on each chorus and fully open in the final chorus; bridge strips back to piano and voice.
Groove & Foundation Progression: classic half-time trap groove — punchy 808 kick, crisp snapping snare/clap, rapid rolling 16th-note and triplet hi-hat patterns with pitch variation, 808 sub-bass carrying the low end; verses sparse, chorus full, bridge heartbeat kick only, final chorus rebuilds the full groove.
Embellishments, Textures & Spatial FX: rain ambience in the intro and outro, reverse cymbal swells into the choruses, wide soft reverb on vocals, subtle space on drums.
```

## 六、官方已知限制

- 段落标签与音乐描述提供的是**生成式引导（generative control），不是严格符号保证**：tempo、key、乐器、歌词与结构可能不完全匹配。
- 三段式描述只能提高命中率；鼓组/乐器跑偏属已知模型特性。
- prompt 文本 token 上限约 5000 tokens；本 skill 规定组装后 ≤2000 字符，留足余量。

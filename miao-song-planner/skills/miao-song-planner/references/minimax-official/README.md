# MiniMax Music 3 官方词库（内置副本）

> 来源：MiniMax-AI/MiniMax-Music3 官方仓库 `skills/music-caption-rewriter`（main 分支），2026-08-14 抓取。
> 用途：组装 MiniMax 试听/成品 prompt 时的**措辞与段落写法参考**；只做参考，不构成对官方 skill 的完整复刻。

## 内容

- `genre-router.md`：曲风路由（先读这个，决定家族索引）。
- `index-*.md`：9 个相关家族索引（Modern R&B/Neo-Soul、Hip-Hop/Rap、Soul/Blues/Gospel、Dance-Pop/Disco/Funk、Electronic/Synth/Ambient、General Pop/Ballad、Jazz/Swing/Big Band、Roots/Traditional/Global、Contemporary Folk/Acoustic）。
- `templates/`：14 个精选完整模板（trap、trap-soul、dark trap、boom bap、melodic trap、neo-soul、contemporary R&B、soul pop、funk pop、soul ballad 等）。

## 使用规则（来自官方 SKILL.md，已适配本 skill）

1. **渐进读取**：先读 `genre-router.md` 定家族 → 只读 1–2 个对应家族索引 → 最多选 3 个模板精读。禁止全量扫描。
2. **以问卷参数为硬约束**：曲风、BPM、调性、人声、乐器、禁用项等已确认选择，优先级高于任何模板推断；模板只提供措辞与段落时间线的参考。
3. **禁止照抄**：不复制模板的完整句子或完整结构，围绕本曲问卷答案综合改写，输出仍为三段式（Global Metadata / Vocal Details / Arrangement）。
4. **妙响规则不混用**：本词库只用于 MiniMax prompt；妙响最终风格框仍按 `../sound-guide.md`。

## 家族与风格库映射速查

| miao-song-planner 风格 | 官方家族 |
| --- | --- |
| Contemporary/Pop-R&B、Quiet Storm、Neo-Soul、Alternative R&B、Trap-Soul、Dark R&B | modern-rnb-neo-soul（Trap-Soul 副家族 hip-hop-rap） |
| Trap-Soul 鼓组、Hip-hop 结构 | hip-hop-rap |
| Retro-Soul / Motown | soul-blues-gospel |
| Funk / Disco / Dance-R&B | dance-pop-disco-funk |
| Electronic / Future R&B | electronic-synth-ambient-pop |
| Jazz-R&B / Psychedelic Soul | jazz-swing-big-band |
| Afro / Dancehall / Latin-R&B | roots-traditional-global |
| Acoustic / Bedroom / Minimal | contemporary-folk-acoustic |
| 兜底 | general-pop-ballad |

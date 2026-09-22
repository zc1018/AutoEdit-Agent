# AutoEdit Agent · FFmpeg / 剪映双后端 Skill

从素材审查、文案、可选配音到剪辑蓝图与交付审计。**默认不需要达芬奇、Resolve Studio、MCP 或模型 API。**

```text
视频 / 音频 / 图片 → 素材证据与文案 → 通用剪辑蓝图
                                      ├─ FFmpeg → MP4 成片 + 字幕 + 审计
                                      └─ 剪映   → 可继续编辑的新草稿 + 审计
```

这次改造不是只改提示词：新增了可执行的双后端 CLI、严格蓝图校验、真实 FFmpeg
集成测试和安全安装器。原 `davinci-*` skills 保留作为兼容选项，不再默认安装。

## 安装

```bash
git clone https://github.com/zc1018/AutoEdit-Agent.git
cd AutoEdit-Agent
python -m venv .venv
# 激活虚拟环境后；FFmpeg / FFprobe 需另行安装并加入 PATH。
python scripts/install_skills.py
python skills/autoedit-agent/scripts/autoedit.py doctor --backend ffmpeg
```

默认安装 `autoedit-agent` 和原有 `viral-video-writer`。安装路径遵循 `CODEX_HOME`，
未设置时为 `~/.codex/skills`；也可用 `--dest` 指定其他支持 Agent Skills 的宿主目录。
`--dry-run` 预览；已有安装默认跳过；`--force` 先备份到技能目录旁的 `skill-backups`，
不会直接删除旧副本。需要原达芬奇 Skill 时才加 `--include-legacy`。
之前已经装过旧技能的用户，其旧副本不会被自动删除；请显式使用 `$autoedit-agent`。

FFmpeg 本地剪辑没有 pip 依赖。仅在需要时安装可选能力：

```bash
python -m pip install -r requirements-jianying.txt  # 剪映草稿
python -m pip install -r requirements-api.txt       # 原有云端素材分析 / TTS
```

## 在 Agent 中使用

```text
使用 $autoedit-agent。素材在 D:\Media\my-vlog。
剪成 3 分钟的横屏视频，先给我看文案和剪辑蓝图。
这次用 FFmpeg 直接出 MP4，保留重要同期声，其他地方降低音乐音量。
```

```text
使用 $autoedit-agent，使用已经确认的剪辑蓝图。
这次选择剪映，生成一个新的可编辑草稿，我要继续调整字幕和音乐。
不要覆盖原素材或已有工程，也不要替我自动导出。
```

选择规则：命令行 `--backend` 优先于蓝图的 `backend`；未指定或 `auto` 固定选择
FFmpeg。明确选择剪映却缺依赖时会报错，**不会偷偷换后端**。

## 直接运行

所有命令在仓库根目录运行。路径含空格时保留引号。

```bash
# 1. 扫描；manifest 的父目录应已存在。原始素材不修改。
python skills/autoedit-agent/scripts/autoedit.py scan --input "D:\Media\my-vlog" --output "media-manifest.json"

# 2. 抽帧供 Agent 或人工审查；必须是新的输出目录。
python skills/autoedit-agent/scripts/autoedit.py extract --manifest "media-manifest.json" --output "review-frames"

# 3. 根据真实素材填写 examples/edit-blueprint.example.json，再校验。
python skills/autoedit-agent/scripts/autoedit.py validate "edit-blueprint.json"

# 4. 先预演，确认后生成到新的交付目录。
python skills/autoedit-agent/scripts/autoedit.py build "edit-blueprint.json" --backend ffmpeg --output "delivery-v1" --dry-run
python skills/autoedit-agent/scripts/autoedit.py build "edit-blueprint.json" --backend ffmpeg --output "delivery-v1" --approve

# 5. 同一份兼容蓝图，也可以改为输出剪映草稿。
python skills/autoedit-agent/scripts/autoedit.py build "edit-blueprint.json" --backend jianying --output "jianying-v1" --approve
```

`--output` 是**新的文件夹**，不是 MP4 文件名。已有目录一律拒绝覆盖。
FFmpeg 输出 `final.mp4`、`edit-blueprint.json`、`audit.json`，有字幕时另有 `captions.srt`。
默认字幕为可开关的 MP4 字幕轨；播放器可能需要手动开启。加 `--burn-captions`
可烧录字幕，需要带 libass 的 FFmpeg 和本地合适字体。字体不随仓库分发。

剪映命令返回 `draft_directory`。把这个完整的新草稿文件夹复制到 **Windows 剪映**
配置的草稿根目录，再在软件中刷新、打开、检查和导出。草稿引用本机绝对素材路径，
不自动打包原视频；跨电脑使用需复制素材并重新链接。

## 已实现与边界

| 项目 | FFmpeg | 剪映 |
|---|---|---|
| 交付 | 直接 MP4 成片 | 新的可编辑草稿 |
| 视频 / 图片 | 连续单视觉轨、硬切、图片停留 | 原生视频/图片片段 |
| 配音 / BGM / 音效 | 独立时间位置、混音、音量、音频淡入淡出 | 独立音频轨、音量和淡入淡出 |
| 恒定变速 | 0.25–4 倍 | 原生源范围与目标范围对应变速 |
| 画幅 | 居中留边或裁切 | 原生默认适配，仅接受 `fit=pad` |
| 字幕 | SRT + 软字幕，或烧录 | 原生文本片段 + SRT |
| 自动导出 | 支持 | 不承诺、不操作 UI |

执行层目前不做多视频轨画中画、复杂转场、LUT、稳定、防抖、自动 HDR 色调映射、
关键帧特效或剪映模板继承。遇到这些字段会明确拒绝，而不是静默丢弃。需要保留这些
效果时，应调整已批准蓝图或列为剪映内的手工步骤。输出帧率为整数；输入可混合帧率。

**剪映兼容说明：**使用可选的 `pyJianYingDraft==0.3.0`，定位为新建 Windows 剪映草稿。
上游明确区分草稿生成和 GUI 自动导出，并限制 Linux/macOS 生成草稿的目标环境。
不能把草稿 JSON 写成功说成所有剪映版本已验证，也不宣称兼容 CapCut 或 macOS 原生剪映。
详见 [后端说明](skills/autoedit-agent/references/backends.md)。

## 校验与测试

蓝图检查唯一 ID、缺失文件、源越界、源/目标时长与变速、帧对齐、空隙/重叠、
字幕范围、非法数值、未知字段等。相对素材路径以蓝图所在文件夹为基准。
`--no-probe` 仅做结构校验；`--dry-run` 会探测素材但不写文件。

FFmpeg 导出后检查画幅、帧数、时长和音视频流，并完整解码一次；失败写入
`FAILED.json`，不当作成功交付。故事、声画观感、中文字幕字形和剪映 GUI 仍需真实复核。

```bash
python -m unittest discover -s tests -v
```

本次本地验证环境没有剪映桌面端，也没有安装可选草稿库。FFmpeg 使用生成的真实
视频/图片/音频完成集成测试；剪映真实草稿测试会在缺依赖时明确跳过，不能算通过。

## 文档与兼容

- [主 Skill](skills/autoedit-agent/SKILL.md)
- [2.0 蓝图字段与旧 1.0 迁移](skills/autoedit-agent/references/blueprint-schema.md)
- [可选分析与配音配置](skills/autoedit-agent/references/configuration.md)
- 原 `davinci-autoedit-agent` / `davinci-resolve-editor` 代码未删除，可按需安装；
  默认流程不调用它们，也不依赖其安装或运行。

## English

An editor-neutral Agent Skill: inspect footage, ground a script in evidence,
create one shared edit blueprint, then either render an MP4 through FFmpeg or
write an editable Windows Jianying draft through an optional adapter. Resolve
and MCP are not required. Basic rendering needs only Python 3.10+, FFmpeg and
FFprobe. Existing outputs and original media are not overwritten. Unsupported
operations fail explicitly. Jianying GUI opening/export remains a manual,
version-dependent verification step, not a tested automatic-export promise.

## Credits / License

Adapted from the original AutoEdit/DaVinci AutoEdit Agent by `liuluhaixiu`; original
MIT copyright and legacy integration notices are preserved in [LICENSE](LICENSE)
and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
FFmpeg and pyJianYingDraft are separately installed external dependencies, not
bundled binaries. See [backend references](skills/autoedit-agent/references/backends.md)
for their upstream documentation. This project is not endorsed by the editor vendors.

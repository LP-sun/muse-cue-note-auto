# MuseScore Cue Planner + DSH Connector v0.3.0

**状态：只读 Cue 候选分析和 DSH/MCP 连接原型。** 不向总谱写入任何 Cue 音符，不覆盖 `.mscz/.mscx`，也不改变源文件。所有建议都必须由乐手或分谱制作者审核。

## 本版完成内容

1. 修复多个 `.mscx` 内嵌分谱导致 MSCZ 主总谱选择失败的问题：仅选择压缩包根目录的 MSCX 主乐谱，忽略 `Excerpts/*`。
2. 对没有 `Part/Staff/@id` 的 MuseScore 4 XML，在主总谱谱表数量与 Part 展开谱表数量严格相等且均无 ID 时，启用按顺序映射；结果明确带有人工核验警告。其他歧义映射直接拒绝。
3. 对超大 MuseScore 3 ZIP，在读取整个 XML 前识别格式版本并拒绝。`Liz and the Blue Bird Final.mscz` 属于 MuseScore 3.02 格式（程序 3.6.2），需要转换另存。
4. 新增 `dsh-plugin/` 独立可安装 DSH bundle，包括内嵌的 `cueplanner` Python 标准库分析器和 MCP stdio 适配器。
5. 注册六个 DSH 工具，均只读或仅在 MuseScore 中改变选中小节：
   - `musescore_cue_analyze(score, min_rest, cue_bars, ...)`
   - `musescore_cue_batch(folder, ...)`
   - `musescore_cue_candidate(plan, candidate_id)`
   - `musescore_cue_bridge_check()`
   - `musescore_cue_live_verify(score)`
   - `musescore_cue_focus(score, candidate_id, at)`
6. 增加可审阅 JSON/Markdown 报告和对 ZIP、路径安全及分析流程的自动化测试。

## 安装 Python CLI / 离线 Cue 分析

要求 Python 3.10+；分析模块仅用 Python 标准库。解压当前项目后在项目根目录：

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m cueplanner analyze "D:/Scores/score.mscz" --min-rest 8 --cue-bars 2 --output "D:/Scores/review.cue-plan.json" --markdown "D:/Scores/review.md"
py -3 -m cueplanner batch "D:/Scores" --out-dir "D:/Scores/CuePlans"
```

批量输出默认防覆盖；旧输出已存在会报错，建议新建目录。分析仅支持 MuseScore 4.x 原生 MSCX/MSCZ；MuseScore 3 先在 4 中打开并另存。默认筛选休止至少 8 小节、重新进入前 2 小节且来源声部节奏和音高能够被保守解析的候选。

## DSH 原生工具安装（Windows）

1. 从本包取出 `dsh-plugin` 整个文件夹（**需要保留里面的 `cueplanner/`**），例如 `C:/Music/dsh-musescore-cue-planner`。
2. 修改 `dsh-plugin/cordis.patch.yml` 的 `config.root` 为你的乐谱目录（必须存在），设置 `python: 'py'`；这是工具可读取的唯一工作根目录（含 CuePlans），路径经 realpath 防越界。
3. 根据你机器上 `dsh plugin --help` 的实际命令来安装；参照 DSH 官方 bundle 操作，通常可执行：

   ```powershell
   dsh plugin --profile web add "link:C:/Music/dsh-musescore-cue-planner"
   ```

4. 重启正在运行的 DSH profile，确认已加载工具 `musescore_cue_analyze` 和 `musescore_cue_bridge_check`，先用合成示例验证，**再用真实乐谱**。
5. 如果你的 DSH Desktop 使用别的 Profile，不要假设是 `web`；由本地 Codex 检查正在运行的 Profile，修复既有插件依赖后再安装。不要覆盖现有 `cordis.patch.yml` 或其他插件。

可先运行插件目录的独立 Node / Python 测试（有 Node.js 22+）：

```powershell
cd C:/Music/dsh-musescore-cue-planner
node --test tests/*.test.mjs
py -3 -m cueplanner analyze "D:/Scores/score.mscz" --min-rest 8
```

### MuseScore 实时连接（MCP Score Bridge）

实时桥接 **需要 MuseScore Studio 4.4.2+**，且安装和启用了上游 `tskovlund/mcp-score` 的 QML 插件。离线解析不依赖 MuseScore 程序运行。

Upstream 0.2.0 的典型安装：

```powershell
uv python install 3.14
uv tool install --python 3.14 "mcp-score-server==0.2.0"
mcp-score install-plugin
```

在 MuseScore 的 Plugins 管理中启用并运行 MCP Score Bridge，并保持桥窗口打开；默认本机 `localhost:8765`。桥接工具从 DSH 启动独立 `mcp-score serve` MCP stdio 进程；不将 WebSocket 暴露在公网。

在 DSH 对话中：

> 检查 MuseScore 连接，然后对 `D:/Scores/score.mscz` 做只读 Cue 分析。先给出候选与风险，不修改工程。打开同一保存文件后调用 live-verify，并逐条选择 cue 小节进行人工验收。

`musescore_cue_live_verify` 比较**标题、小节数、Part 数量**，匹配不保证是相同文件。Focus 会更改 MuseScore 的当前选择，但不会新增音符。连接尚未在真实用户主机上做端到端验证。

### 算法与误判风险

- 以整个 Part 而不是单行 Staff 判断休止，避免钢琴左手独立触发 Cue。
- 优先单声部、节奏完整的来源乐句；跳过复合节奏、连线、三连音、多声部及无法可靠推导时值的情况。
- 排序考虑音符起始数、节奏种类、音高走向及音域；**并不具有真实声学可听度或配器知识**。
- 特别注意移调、打击乐或键盘类、跨调号/拍号、重复记号附近及不自然来源（如高音长笛使用低音大号提示）。
- 当前版本**没有自动写入 Cue Notes 或同步总谱/分谱可见性**；后续必须先验证这些高风险功能。

## 测试情况

- Python：16 项自动化测试通过（含 ZIP 内嵌分谱、Part/Staff 无 ID、旧格式拒绝、MCP stdio 模拟）。
- Node.js：4 项测试通过（路径越界/符号链接、输出目录隔离、启动 Python 分析）。
- 真实离线输入：6 份 MuseScore 4 总谱，产生 289 条需要审核的候选。第 7 份是 MuseScore 3，已快速拒绝；报告见交付包 `Cue_批量测试_20261029/summary.md`。
- **尚未验证**：真实 DSH Profile 加载、真实 MCP Score Bridge WebSocket、MuseScore GUI 选择和最终 Cue 写谱/排版。

参考：[DSH 插件官方教程](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md)、[DSH tools](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/tool.md)、[mcp-score](https://github.com/tskovlund/mcp-score) 。上游依赖不随本项目分发。

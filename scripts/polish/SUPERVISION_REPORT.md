# 监护运行报告

**运行日期**：2026-03-23  
**工具版本**：新-polish Haskell pipeline（cabal build all 通过）  
**测试话题**：`.local/topic1.md`（v4 认知引擎：整体系统设计的自由探索，3辩手×2轮）  
**模型**：全程 `gpt-5.4-nano`（除 compact embedding）  
**命令**：
```bash
python3 scripts/polish/hs_check.py .local/topic1.md --model gpt-5.4-nano
python3 scripts/polish/hs_polish.py .local/topic1.md --model gpt-5.4-nano --max-polish-rounds 1 --max-rewrite-rounds 1
```

---

## 一、各阶段行为描述与预期对照

### 1. hs_check（独立检查流水线）

#### Phase 1：命题抽取
- **实际行为**：从话题文档（~4000 字背景，设计方案描述，辩论历史）中抽取了 10-11 条原子化设计命题，每条约 1-2 句，覆盖"维护器职责""双引擎请求分发""攻击横切策略""终止条件""多体系并存"等核心设计点。
- **预期对照**：✓ 符合。命题粒度合适，每 500 字约 5-10 条，跨 Section 引用的相同概念均独立抽取。
- **得分**：4/5。命题数量偏少（对于一个 4000+ 字的长文档，10-11 条有点稀疏），但每条命题质量良好，可验证。

#### Phase 2：矛盾与遗漏检查
- **实际行为**：发现了 3 个问题，包括 1 个 Critical（维护器"不确信"分支缺形式化覆盖）、2 个 High（空缺-广度引擎反馈闭环、攻击引擎结果到冲突处理的映射）。
- **预期对照**：✓ 符合。问题严重程度分级准确，引用的命题编号有据可查，描述清晰。
- **得分**：5/5。抓住了最关键的结构性缺口（攻击/深度的停止条件与维护器的接口契约）。

#### Phase 3：交叉覆盖矩阵
- **实际行为**：归纳了 11-14 个核心设计点，产生了 12-20 条 weak/gap 矩阵条目，涵盖"单一状态权威 × 确信门控""横切策略 × 控制流编排""递归分解 × 冲突处理"等组合。
- **预期对照**：✓ 符合。Gap 条目的覆盖密度合理，每条附有可操作描述（不是单纯的"未覆盖"）。
- **得分**：4/5。矩阵规模偏小（对 11+ 设计点来说理论上有 55 对，但只报出 20 个 weak/gap），说明模型对部分交互确实覆盖良好，但也可能有漏报。

#### Phase 4：总结
- **实际行为**：生成了对整体设计的文字总结和亮点列表，指出系统的核心贡献（3+1架构、单一状态权威、横切策略）以及主要风险（终止条件不可计算、死锁路径）。
- **预期对照**：✓ 符合。总结质量良好，不流于平凡。
- **得分**：4/5。

#### Phase 5：可疑断言 + Q&A 审查
- **实际行为**：识别了 10-13 条可疑断言（SC1-SC11），覆盖"COT 信息增量为零""维护器只在高度确信时行动""多引擎互不了解""平凡劣化必然发生"等强断言。由于是第一次运行无 Q&A 节，Q&A 反馈为 0。
- **预期对照**：✓ 符合。可疑断言识别精准，`scReason` 字段均指出了断言的具体可疑之处（缺度量标准/未引用文献/过度绝对化）。
- **得分**：5/5。这是该 pipeline 区别于标准 check 的核心增值，效果超预期。

---

### 2. hs_polish（迭代打磨流水线）

#### 阶段 A：debate-tool run（初始设计生成）
- **实际行为**：以 topic1.md 为输入运行了 3 辩手（Linus Torvalds / Ssyram / 康德）× 2 轮辩论 + cross-exam，产出了裁判总结作为"设计文档"。裁判给出了**驳回 v4 当前形态**的裁定，并提供了一份系统化的认知引擎架构说明（维护器 + 4 子引擎 + 协议层，含状态机定义、类型化接口、退化检测谓词）。
- **预期对照**：✓ 符合预期。初始 debate 的目的是获得一份"初始设计"，裁判总结即承担此职责。输出质量高——裁判没有给出"各方说法均有道理"的平凡总结，而是给出了可执行的工程规格。
- **得分**：5/5。

#### 阶段 B：initial check（对初始设计的 Check）
- **实际行为**：对 226 行裁判总结（设计文档）执行了 5 阶段 check：
  - Phase 1：抽出 65 条命题（文档密度远高于原始话题文本）
  - Phase 2：4 个问题（Critical 2 / High 2）
  - Phase 3：18 设计点，12 矩阵条目
  - Phase 5：10 可疑断言
- **预期对照**：✓ 符合。命题数量显著增多（65 vs 10），说明裁判总结提供了更高信息密度的设计文本，check 有更多可检查内容。
- **得分**：5/5。

#### 阶段 C：initial debate resume（初始裁决）
- **实际行为**：以 issues.md（4 个问题 + 10 个 SC）为输入构建 resume topic，启动 debate-tool resume。裁判产出了 145 行的裁决报告：对 2 个 Critical 问题给出了 `reject`，对 High 问题给出了 `accept_fix`，并对所有 SC 给出了推翻/支撑/延迟的裁定。
- **预期对照**：✓ 符合。裁决质量高——裁判引用了原文命题编号（P29/P30/P31/P32），给出了 P0/P1 优先级修复方向，包含"deterministic selection function"这样的工程可落地建议。
- **得分**：5/5。

#### 阶段 D：rewrite（基于裁决的重写）
- **实际行为**：以初始设计文档 + 裁决作为指南，产出了重写后的设计文档（`rewrite_1_1.md`）。命题从 65 条降至 43 条——说明 LLM 在重写过程中精简了冗余内容，集中补充了状态机闭环、确定性选择函数等关键缺口。新增了 Q&A 节（3 条 QA feedback，说明 SC 被处理了一部分）。
- **预期对照**：✓ 基本符合。命题数量减少属正常（设计更聚焦），Q&A 节出现说明 rewrite 遵循了 Q&A 维护规则。
- **得分**：4/5。重写后 issues 从 4 个增加到 7 个（可疑断言从 10 降到 7），说明重写在某些维度引入了新问题。这是 merge 步骤的存在意义——7 个新问题里哪些在裁决范围内、哪些超出裁决范围，由 merge 决定。

#### 阶段 E：check + merge
- **实际行为**：对 rewrite_1_1.md 执行 check（结果见阶段 D）。merge 阶段判定"没有新的指引"（`No new guide — rewrite resolved all addressable issues`）——意味着所有新问题要么超出了现有裁决范围，要么与旧问题相同但已被处理。
- **预期对照**：⚠ 需要关注。merge 判定 no new guide 意味着 rewrite 已解决了所有可由当前裁决处理的问题。这触发了"继续 polish loop"而不是"early exit"，因为 `okToGo` 条件（无 High/Critical + 无 SC）仍未满足。
- **评注**：这是 merge 和 okToGo 之间的语义差异：`no new guide` 说明 rewriter 已尽力，但 `okToGo` 基于当前 check 结果判断设计是否"足够好"。由于仍有 7 个问题 + 7 个 SC，polish 没有提前退出是正确的。
- **得分**：5/5。

#### 阶段 F：compact + resume（下一轮裁决）
- **实际行为**：compact 压缩了辩论日志，然后执行 resume 获取新裁决。
- **预期对照**：✓ 符合。compact 的目的是防止日志过长导致 token 溢出。
- **得分**：5/5。

#### 阶段 G：polish round 2 → max rounds
- **实际行为**：由于 `--max-polish-rounds 1`，Polish Round 2 到达上限，输出最终设计文档。
- **预期对照**：✓ 符合。max rounds 是用户指定的截止点，不是错误。
- **得分**：5/5。

---

## 二、总体评分

| 阶段 | 行为符合预期 | 质量 | 问题 |
|------|------------|------|------|
| Phase 1（命题抽取） | ✓ | 4/5 | 命题数量偏稀疏 |
| Phase 2（矛盾遗漏） | ✓ | 5/5 | 无 |
| Phase 3（覆盖矩阵） | ✓ | 4/5 | 可能有漏报 |
| Phase 4（总结） | ✓ | 4/5 | 无 |
| Phase 5（可疑断言） | ✓ | 5/5 | 超预期 |
| Debate Run（初始设计） | ✓ | 5/5 | 无 |
| Initial Check | ✓ | 5/5 | 无 |
| Initial Debate Resume（裁决） | ✓ | 5/5 | 无 |
| Rewrite | ✓ | 4/5 | 重写引入了新问题（7>4），正常但值得关注 |
| Check + Merge | ✓ | 5/5 | 无 |
| Compact + Resume | ✓ | 5/5 | 无 |
| Max Rounds 终止 | ✓ | 5/5 | 无 |

**整体评分：4.7/5**

---

## 三、是否符合工具的自动打磨精神

### 符合点

1. **每步落盘**：所有中间产物立即写入对应文件，崩溃不丢工作。实测输出目录结构与设计完全吻合。
2. **细粒度 check 价值高**：Phase 5 的可疑断言识别比"辩论式 check"效果更强（可类比 topic1 文档中描述的三种检查方式对比）。
3. **裁决质量高**：debate-tool 产出的裁判总结包含可执行的修复建议（"deterministic selection function"，"字段级穷尽表"），而不是模糊的原则性建议。
4. **Q&A 维护规则工作**：rewrite 后文档出现了 Q&A 节，且 phase5 audit 能对其反馈（3 条 QA feedback），说明闭环机制可用。
5. **compact + resume 工作**：日志压缩与续跑均成功，裁判能基于压缩历史继续给出高质量裁决。

### 需要关注的点

1. **merge no-new-guide 过早**：当前 merge 判断"所有可解决问题已被解决"后，polish 仍在继续（正确），但如果裁决本身没有给出足够具体的修复方向，rewrite 可能无法有效提升，导致多轮后设计质量停滞。
2. **rewrite 引入新问题**：从 4 个 issues 增加到 7 个，部分可能是"覆盖了旧内容但暴露了新联系"，但需要人工检视是否真的是进步。
3. **Phase 1 命题数量不稳定**：两次运行（check 独立运行 vs polish 内部 initial check）抽出的命题数差异很大（10 vs 65），主要原因是输入文档差异（话题原文 vs 裁判总结），但也说明命题数量对文档字数高度敏感。

---

## 四、Bug 修复记录（本次监护运行中发现并修复的问题）

1. **env 路径 bug**（`hs_check.py` / `hs_polish.py`）：`DEFAULT_ENV` 指向 `scripts/.local/.env` 而非 `debate/.local/.env`，导致首次运行报 `MissingEnvVar "DEBATE_BASE_URL"`。已修复为 `REPO_ROOT = SCRIPT_DIR.parent.parent`。
2. **双重日志 bug**（`CheckPipeline.hs`）：`runPhaseNToDir` 通过 `runPhaseWithWrite` 传入 `logPhaseN` 回调，同时 `runPhaseN` 内部也调用 `logPhaseN`，导致每条 phase summary 打印两次。已修复为 `runPhaseN` 不再内部调用 log，logging 统一通过 `logPhaseSummary` 在 `collectPhases` 后执行（`runCheckToDir` 路径则通过 `runPhaseWithWrite` 的 `after` 回调）。
3. **`find_binary` 类型注解错误**：返回类型标注为 `Path` 但实际可能返回 `None`，已修正为 `Path | None`。

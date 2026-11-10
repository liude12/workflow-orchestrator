# 专业方法来源与本地适配

2026-11-10。本目录提供的是适配后可直接读取执行的方法 Skill，不是上游插件安装目录。阶段规则、模板、版本与人审职责保持在原阶段；本地方法负责窄范围的专业工作。固定版本原文已在建设验证中读取，来源指纹及适配文件指纹见 [catalog.json](catalog.json)。

## 采用的来源

| 本地方法 | 来源及固定版本 | 主要适配 |
| --- | --- | --- |
| [research-evidence](research-evidence/SKILL.md) | ECC 的 market-research、product-lens，提交 `d2ef2680594f9a17526a6e1a2e18b3d242c5d17b`；PM Skills 的 interview-script，提交 `9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef` | 研究聚焦有效目标与任务；诊断/访谈按需；已知信息集中复用；事实、推断、建议、营销主张与反证分开；结果回现有 S1 成果 |
| [scenario-coverage](scenario-coverage/SKILL.md) | PM Skills 的 test-scenarios，同上提交 | 从有效规则确定预期；保留多对象结果和未知项；用例计划、实际执行和真人验证分开，沿用原质量记录 |
| [prototype-build](prototype-build/SKILL.md) | ECC 的 frontend-design-direction，同上提交 | 按阶段输入生成 HTML 产品体验；复用品牌与组件；不固化审美偏好、不引入 UIZZE 或新的检查格式；保留任务、状态、权限、增量复验和现有 S4 准入 |
| [capability-specification](capability-specification/SKILL.md) | ECC 的 product-capability，同上提交 | 按复杂性触发，交叉核对 PRD 与有效业务/现有契约；保持十一章 PRD、六章 SRS 及同版 T05；不替代 `/ecc:plan-prd`，不自动启动研发 |
| [task-solution](task-solution/SKILL.md) | 本工作流既有 S3 任务、能力、页面与行为规则 | 独立编写任务组织与完整切片步骤，不复制 Dean Peters 的 Skill 原文；已有外部用户故事/拆解方法仅按需引用，不作为分享包必装依赖 |

ECC 的原文路径：

- [market-research](https://github.com/affaan-m/ECC/blob/d2ef2680594f9a17526a6e1a2e18b3d242c5d17b/skills/market-research/SKILL.md)
- [product-lens](https://github.com/affaan-m/ECC/blob/d2ef2680594f9a17526a6e1a2e18b3d242c5d17b/skills/product-lens/SKILL.md)
- [frontend-design-direction](https://github.com/affaan-m/ECC/blob/d2ef2680594f9a17526a6e1a2e18b3d242c5d17b/skills/frontend-design-direction/SKILL.md)
- [product-capability](https://github.com/affaan-m/ECC/blob/d2ef2680594f9a17526a6e1a2e18b3d242c5d17b/skills/product-capability/SKILL.md)

PM Skills 的原文路径：

- [interview-script](https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-product-discovery/skills/interview-script/SKILL.md)
- [test-scenarios](https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-execution/skills/test-scenarios/SKILL.md)

## 许可与分享范围

上述 ECC 来源 Copyright (c) 2026 Affaan Mustafa，PM Skills 来源 Copyright (c) 2026 Pawel Huryn，适用 MIT 许可，随包保留完整的 [ECC 许可](licenses/ecc-MIT.txt)和 [PM Skills 许可](licenses/pm-skills-MIT.txt)。这些适配资源的署名、许可和改动说明应随文件保留；不将第三方许可扩大到项目业务资料或其他插件资源。

Dean Peters 的方法在某些接收环境可能已单独存在，其版本和许可由该安装提供；本次没有把其原文、模板或依赖复制进本包，也不将它们改标为 MIT。Product Design、Figma、UI UX Pro Max、浏览器测试框架和 ECC 的原始命令没有随本目录安装；按需使用时以当前环境真实入口及各自要求为准。

## 维护

`catalog.json` 将每个本地方法关联到适用阶段、上游原文哈希、许可证文件及适配文件哈希。上游升级先比较语义及依赖，重新验证受影响场景，再更新清单；不自动追随主分支。脚本检查通过不证明已执行方法或真实工具，也不改变业务成果状态。

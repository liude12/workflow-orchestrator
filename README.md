# 产品团队 AI 协作工作流

从产品想法到 PRD/SRS 的五阶段协作 Skill，支持需求接续、业务变更、可操作原型和版本追踪。

**Skill 安装链接：** https://github.com/liude12/workflow-orchestrator/tree/main/skills/workflow-orchestrator

## 安装与第一次使用

在支持本地 Skill、文件读写及命令执行的 AI 客户端中，把下面这段话发给 AI：

```text
请使用 skill-installer 安装这个 Skill：
https://github.com/liude12/workflow-orchestrator/tree/main/skills/workflow-orchestrator
安装完整 workflow-orchestrator 目录，保留其中的 stages、methods、references、assets 和 scripts。
如果已有同名版本，先比较并备份，不直接覆盖项目资料。
安装后检查入口、相对引用、Python 版本和 methods/catalog.json 的文件指纹；说明实际可用与尚未配置的能力。
```

没有 skill-installer 时，可下载本仓库 ZIP 并解压，将 `skills/workflow-orchestrator` **整个文件夹**放入当前客户端实际支持的 Skill 目录。安装路径以客户端实际发现规则为准；不要只复制顶层 `SKILL.md`，也不要把 5 个阶段拆开后丢掉公共引用。

安装后，在新一轮对话选择或点名 `workflow-orchestrator`，例如：

```text
请使用 workflow-orchestrator。
产品名称：【填写】
项目目录：【独立产品目录的完整路径】
目标用户和要解决的问题：【填写】
已有资料：【文件路径；没有则写暂无】
请先完成 S1，复用已有信息，集中提出真正缺失的问题，继续不受阻塞的工作。
```

产品资料保存在独立项目目录，Skill 安装目录用于存放规则与工具。

## 五个阶段

| 阶段 | 主要工作与成果 |
| --- | --- |
| S1 需求澄清 | 需求定义书和独立竞品调研报告 |
| S2 业务建模 | 业务流程、角色、规则、状态及业务验证原型 |
| S3 产品方案 | 功能方案、系统页面布局及连续任务原型 |
| S4 原型与验证 | 可操作 HTML 原型、设计映射、实际走查及真实验证记录 |
| S5 PRD 与 SRS | 同版 PRD/SRS、验收追踪、评审及交付记录 |

S2/S3/S4 均应呈现可连续操作的产品体验，验证目的分别聚焦业务闭环、功能与任务路径、呈现与使用体验。S4 的用户 UI/UX 资料可选：有则复用，没有时 AI 形成具体暂定设计继续；后补资料按影响更新。既定业务规则、品牌强制要求和实际用户验证边界仍保留。

## 使用手册和练习

- [在线阅读完整手册（Markdown）](docs/使用手册-20261110/产品团队AI协作工作流使用手册.md)：14 节说明、15 段示例指令。
- [离线 HTML 手册](docs/使用手册-20261110/产品团队AI协作工作流使用手册.html)：下载仓库 ZIP 后用浏览器打开，含目录和复制功能。
- [个人任务系统教学原型](docs/使用手册-20261110/示例/个人任务系统.html)：下载后打开；刷新恢复样本，不连接真实业务后端。

首次使用先读手册第 1—3 节，修改已有项目看第 7 节。手册中提及的历史完整分享包与建设资料属于另行分发资源，本仓库只包含当前 Skill、手册和这个独立教学副本。

## 环境与依赖

- 运行随包工具需要 **Python 3.10+**；Skill 的运行脚本使用标准库。
- 原型实际操作需要当前环境可用的浏览器或计算机操作工具；未实际操作不能记录为已测试。
- 新生成或实质重新生成 PRD/SRS 需要实际可用的 **`/ecc:plan-prd`**；该外部命令不随仓库安装。没有时如实记录未执行，不能把阅读说明当作调用成功。
- 已适配的 5 项方法随完整目录提供；Figma、Product Design 等外部工具按任务及实际可用性选用。

## 核验下载内容

在解压后的仓库根目录运行：

```sh
python tools/verify.py
python skills/workflow-orchestrator/scripts/method_check.py
```

以上只检查文件完整性和方法来源记录，不代表产品正确性、正式品牌批准或真实用户验证。

## 来源与许可

第三方适配方法及其 MIT 许可、署名见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [来源记录](skills/workflow-orchestrator/methods/provenance.md)。第三方许可证只覆盖对应来源；仓库自有内容尚未指定统一开源许可证，不能将第三方 MIT 自动扩大到整个仓库。

## 版本

首次 GitHub 发布：`20261110.13`。S4 行为沿用 `.12` 的 UI/UX 可选输入规则，本版修复修改后的 `prototype-build` 文件指纹记录，并提供可从 GitHub 安装的目录。手册已适配 GitHub 仓库目录，行为规则适用当前版本。

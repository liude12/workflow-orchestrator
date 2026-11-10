# 本地维护命令

## 专业方法包检查

安装、分享或更新随包方法后执行 `python -X utf8 <skill_root>/scripts/method_check.py --root <skill_root> --report <新的报告.json>`。只读核对本地方法清单、阶段关联、来源声明、许可证和适配文件指纹；返回 0 表示结构与完整性通过，2 表示不通过，1 表示报告写入失败。报告不覆盖旧文件。该检查不执行方法、不发现或安装外部插件，不认证 ECC 命令可用性，也不证明生成质量；实际任务仍按[专业方法规范](specialist-methods.md)执行和留证。

新增的独立视觉评审记录检查见 [ui_finish_gate.py 参数与 JSON](ui-finish-gate-tool.md)。该只读工具不替代 workspace.py 的状态、质量记录、真人验证或授权。

## 首次执行与环境变化时预检

在首次写项目记录、首次做浏览器验证，或解释器/浏览器/登记方式变化时执行；同一环境的成功记录可复用，不逐命令重复。先实际运行候选解释器 `python -I -c "import sys; print(sys.executable, sys.version)"`，确认 Python 3.10+；命令存在或 Windows 快捷入口可找到不代表能启动。失败时记录错误并从当前环境发现其他 Python（含可用的运行时自带解释器），用实际绝对路径重试，不硬编码示例机器路径、不安装未要求的依赖。

```text
<已验证的Python> -X utf8 <skill_root>/scripts/preflight.py --browser auto --evidence-kind source --report <新的预检报告.json>
```

预检会实际启动 Python 子进程，在临时隔离浏览器配置中打开本地页面并核对 JavaScript 结果，再调用维护工具同一证据校验逻辑。支持 `--browser <Chromium/Edge/Chrome实际可执行路径>`；不改项目。返回 0 表示本轮适用探测通过，2 表示失败或未执行，1 表示报告无法保存；报告不会覆盖旧文件。失败只阻塞依赖该能力的工作。

若使用当前会话的浏览器工具，先实际打开一个可访问的本地测试页面，执行一次输入/点击并观察结果，把真实工具、时间、操作、预期、观察和证据定位保存为 JSON（字段 `status=passed, tool, at, operation, expected, observed, evidence`），再用 `--browser tool --browser-evidence <记录.json>`。这只登记外部实测证据，脚本不独立认证它；不能只发现工具名称就写可用。纯文档任务可以 `--browser skip --skip-browser-reason <本轮无需浏览器的原因>`，以后进入原型验证仍须实际探测。

登记前辨别字段：`evidence.kind` 仅支持 `source / human_reply / operation / user_observation / review`；生成的 HTML/资源用 `source`，`prototype` 是 `review_bundle.files[].role`，不是 evidence 类别。可追加 `--root <项目根> --payload <计划的put.json>` 预查 evidence 类别、定位、文件存在与越界；P04 的入口/资源闭包由 put 自身检查，预检不替代。预检报告只证明当前环境/登记输入检查，不证明产品功能、原生小程序、手机真机或真人验证通过。

## 可选：阅读入口和资源的静态检查

需要检查文档或原型阅读入口的本地链接、图片与样式资源时，AI 可运行：

```text
python -X utf8 <skill_root>/scripts/review_check.py --root <本次成果目录> --entry <目录内相对入口> --report <目录外全新报告.json>
```

工具不访问网络、不修改成果；报告父目录须已存在，报告文件必须不存在且位于检查目录之外，不会覆盖原文件。退出码 0 表示识别范围内的静态引用检查通过，2 表示发现缺失、越界或其他静态问题，1 表示输入或写入错误。外部链接与外部资源分别报告；前者不验证可访问性，后者不能据此认定离线可用。Markdown 引用式链接与锚点、动态链接不在检查范围内。报告明确标记浏览器任务、收件人访问、真人验证与批准未执行或未确认；**静态通过不等于实际打开、交互完成或业务验收**。

`skill_root` 为含主 SKILL.md 的实际安装目录，`workspace_root` 为产品业务目录。用当前可用的 Python 3 运行，Windows 建议 `python -X utf8` 避免中文编码问题。脚本只用标准库，不把示例机器绝对路径写进项目；文档等专用任务按其运行环境工具获取依赖。

新项目默认使用中文业务目录，状态位于 `06-项目管理/state.json`；脚本接受项目根目录而非管理子目录，根目录也可中文命名。已有 `06-project-management/state.json` 的英文布局会自动识别，接续和新增内容仍沿用原布局，不需要重命名。先识别再写入：

```text
python -X utf8 <skill_root>/scripts/workspace.py --root <候选范围> discover --max-depth 4
python -X utf8 <skill_root>/scripts/workspace.py --root <workspace_root> resume
python -X utf8 <skill_root>/scripts/workspace.py --root <旧项目> migrate
python -X utf8 <skill_root>/scripts/workspace.py --root <旧项目> migrate --apply
```

discover 返回零个、唯一或多个项目及旧格式信息；存在损坏状态不能按空目录初始化。migrate 用于根目录旧格式 state.json 的升级，默认预检；apply 先在项目同级完整备份并核对哈希，再升级索引，新的管理层采用中文目录，原正文和证据路径保持有效，旧状态另存。英文 schema 2 项目直接接续，不把更名当作必须迁移。执行前展示具体迁移范围；任务已授权迁移时按既有授权继续。

```text
python <skill_root>/scripts/workspace.py --root <workspace_root> init --product 产品名称
python <skill_root>/scripts/workspace.py --root <workspace_root> new --data new.json
python <skill_root>/scripts/workspace.py --root <workspace_root> snapshot --file 真实输入文件
python <skill_root>/scripts/workspace.py --root <workspace_root> put --data item.json
python <skill_root>/scripts/workspace.py --root <workspace_root> record --data check-or-decision.json
python <skill_root>/scripts/workspace.py --root <workspace_root> question --data question.json
python <skill_root>/scripts/workspace.py --root <workspace_root> gate --items FIT-001-T01-001
python <skill_root>/scripts/workspace.py --root <workspace_root> promote --items FIT-001-T01-001
python <skill_root>/scripts/workspace.py --root <workspace_root> checkpoint --data checkpoint.json
python <skill_root>/scripts/workspace.py --root <workspace_root> resume --requirement FIT-001
python <skill_root>/scripts/workspace.py --root <workspace_root> manifest --requirement FIT-001 --items <本期各适用阶段主成果及其他交付条目>
python <skill_root>/scripts/workspace.py --root <workspace_root> deliver --data delivery.json
python <skill_root>/scripts/workspace.py --root <workspace_root> delivery-check --data actual-package-check.json
```

路径参数加 shell 适用的引号。以 JSON 文件传递中文和多行数据，不能把聊天内容直接插进 shell 命令。payload 路径相对于执行目录；body_file 使用实际绝对路径。证据和成果记录内的 path 必须相对于 workspace_root，不得越界。

gate 可一次检查多个条目；promote 每次只接受一个条目，按依赖顺序逐项执行。命令失败先核对返回和当前状态，不把可能已写入的操作盲目重跑。

## new

```json
{"id":"FIT-001","title":"预约取消","target":"V1.0","roles":{},"plan":{
"S1":{"mode":"execute","reason":"需要明确目标与范围"},
"S2":{"mode":"execute","reason":"需确认课时规则"},
"S3":{"mode":"execute","reason":"需定义入口与结果"},
"S4":{"mode":"execute","reason":"验证用户任务"},
"S5":{"mode":"execute","reason":"形成交付规格"}}}
```

角色未知允许空，先做草案。知道实际角色后 `configure --data config.json`：`{"requirement":"FIT-001","reason":"已取得项目职责说明","roles":{"business":["实际姓名"],"product":["实际姓名"],"delivery":["实际姓名"],"reviewer":["实际姓名"]}}`。等价配置不写入；新增兼任不改变内容版本、有效内容指针或既有交接。撤销/替换职责仅重新核验实际依赖的审批、人工复核、委托、豁免和交接，包含跨需求引用；未变内容保留，缺当前授权时显示待授权复核，并由 gate/复用/交接/交付拦截。可在同版本补充实际有效授权，不要求重登正文。旧工具已经因重配标为待更新的成果不会被自动恢复，需按实际历史影响复核，不能批量假定原批准适用。
阶段选择在 new 时登记；执行范围改变用 `replan --data plan.json`，字段为 requirement、reason、plan（完整五阶段计划）。工具保留变更前后计划并标记受影响阶段及其下游需复核。目标版本固定，另一个目标版本建立新需求容器；同一目标版本的范围变更可更新 T01 后继续原容器。reuse 额外提供 items；not_applicable 记录实质理由，不得用它绕开实际所需工作。

## put

```json
{"requirement":"FIT-001","type":"RULE","title":"取消后的课时处理",
"body_file":"绝对路径/规则草稿.md","expected_version":0,
"refs":[{"id":"FIT-001-SRC-001","version":1}],"decision_roles":[]}
```

省略 id 自动分配；修改传现有 id、当前 expected_version 和 change_reason。T01 自动要求 product 决定，RULE 自动要求 business 决定；decision_roles 用于补充重要取舍所需角色。
SRC 需 `stage:"S1"` 和 evidence 数组。先 snapshot 输入文件，再将返回的 path 和可定位原文位置写入 evidence，如 `{"kind":"source","path":"snapshot返回的path值","locator":"第3段"}`。路径使用工具实际返回值，不套用另一布局；其他需要运行文件的对象（如 P04）也通过 evidence 绑定自包含 HTML 快照，正文说明入口、任务与模拟数据。

S2 的业务原型和实测记录与 T02 同版登记。S3 的功能验证原型、实测记录和系统布局与 T03 同版登记。put 接收 review_bundle 文件清单，保留相对目录并返回登记版正文的 path。审核人从该正文进入原型和操作记录。独立来源和人工回复可继续 snapshot。字段、布局在正文中的写法及旧项目补齐方法见[审核材料登记规范](registered-review.md)。

S4 的 P04 同样支持 review_bundle，命名 HTML 使用 `role=prototype`，样式、脚本、图片及阅读说明使用 `support`，正文需有实际可点击的原型入口。单 HTML 快照模式仍可用，但入口按最终登记正文目录解析；相关文件必须全部登记且哈希匹配。未登记命名入口、缺本地资源、只在注释/代码示例中的链接会在写入前拒绝。旧 P04 保持可读，门禁发现断链时用新版本补齐，不能只在交付稿里掩盖旧正文缺陷。

S5 的配套 PRD 与 SRS 也使用 put 的 review_bundle，PRD 为 body_file，一个非空 Markdown 的 SRS 使用 role=srs，相关本地阅读附件使用 support。曾登记双文档的 T05 后续修订须一并提交本轮两份文档。参数及旧项目接续见[审核材料登记规范](registered-review.md)。

## record

RULE 或 T02 的 V 复核先核对业务责任。登记为本需求 business 的责任人可直接提交 human_review。由实际获委托的已登记人员复核时，在同一条 V 输入中附 `delegation`。下面的字段用本次实际值替换，委托证据应能定位到具体责任人、受托人以及适用成果版本。

```json
{"by":"登记的业务责任人","to":"此次复核的实际人员","id":"FIT-001-T02-001","version":1,"evidence":{"kind":"human_reply","path":"实际委托快照的相对路径","locator":"委托范围所在段落"}}
```

这项委托只覆盖该人对该版本的 V 复核。规则决定仍按业务批准流程登记。继续旧项目时，若原 V 只记载了其他岗位的姓名，可补录已有适用的委托依据或请业务责任人复核，再检查当前版本。

I/V 检查 payload 共同字段：id、version、category、actor、result(pass/fail)、conclusion、criteria（已实际检查的规则和判定）、evidence。V 另外填 method 和 independence；method 选 human_review、actual_operation 或 source_cross_check。human_review 的 actor 必须为已登记实际人员；RULE/T01/T02/T05 必须使用这种方式。
证据示例：`{"kind":"review","path":"snapshot返回的path值","locator":"评审第2至8条"}`。先快照真实回复或实际操作日志，再登记。独立核验需逐项覆盖，脚本不会自动判定充分性。

批准：category=approval，填 role(business/product/delivery)、actor、result(approved/rejected)、conclusion、evidence；id/version 绑定确切对象。evidence.kind 为 human_reply/review/source，须是实际回复或已有有效文件决定。被拒绝的决定不能通过门禁。

若当前有效内容仍合法引用旧版本，而该旧版本的原复核/批准/豁免因撤权失效，可对确切旧 `id/version` 用 `record` 显式提交 `historical_authority_recheck:true` 和 `reason`，其余按相应 V、approval 或 validation 字段提供当前有权人的真实证据。工具只允许补核仍在有效内容引用闭包内、确有授权失效的类别，不允许夹带正文、refs 或范围修改，不替代业务变更流程。补核追加保存到 `authority_rechecks`，保留历史原件和原授权；新的证据会改变适用清单，须重新核对受影响的交接/交付授权，不能把旧批准默默移到新证据。已有授权仍有效时不创建重复补核。

用户验证：category=validation，id 绑定 P04/T04 版本；result=verified 需 participant_role、tasks 和 user_observation 证据；result=waived 需产品权限人 actor、risk_reason、scope 和实际回复；result=pending 不会放行。所有 record 均需 conclusion，严禁生成虚假观察来通过门禁。

### T02 的 I 检查：把闭环结论绑定到操作证据

按 S1 原文及有效决定先列出每条关键路径的起点、对象、预期终点、交接和跨入口条件。审查者从原文反查路径清单的遗漏，再做原型实操。用新记录报 T02 `I=pass` 时，保留常规字段，`evidence.kind` 填 `operation`，指向本版真实操作记录（登记附件或快照均可）。在该 UTF-8 记录内保留可定位的 Markdown 表或 TSV，前五列依次为**贯穿业务的对象标识、实际执行人、入口、动作、实际观察**。发生交接时写明接收人，可放在第六列；有子单时，同一业务沿用可核验的关联标识，子单号、环境与原始日志出处可加在后续列。按实际执行顺序记录，一次动作一行。

以下为字段示例。该虚构流程只有单一录入来源；切换角色进入工作清单属于后续处理。

```text
| 对象 | 执行人 | 入口 | 动作 | 实际观察 | 接收人 |
| --- | --- | --- | --- | --- | --- |
| A17 | 专员 | 异常清单 | 转办 | 待主管复核 | 主管 |
| A17 | 主管 | 我的待办 | 核对并结单 | 已结单 | |
```

```json
{"closure":{"cases":[{"kind":"handoff","source":"需求A §3 转办与结单","object":"A17",
  "expected":"已结单","status":"passed","steps":[
    {"line":3,"actor":"专员","entry":"异常清单","action":"转办","observed":"待主管复核","to":"主管"},
    {"line":4,"actor":"主管","entry":"我的待办","action":"核对并结单","observed":"已结单"}]}],
  "not_applicable":{"cross_entry":"需求A §2 规定该申请只有一个登记入口。"}}}
```

`line` 从**证据文件第一行**起计，每步前五列与申报值精确对应。每个关键原文结果用可找到的 `source` 和一个事先确定的 `expected` 关联；`steps` 末步应出现该结果。交接类填 `handoff`，给交出步骤标 `to` 并在其后实测接收方对同一事项的操作。跨来源写入、重复认领等填 `cross_entry`，同一对象须实际从不同入口办理；同时存在交接时也标 `to`。普通单角色路径可填 `single`。对 `handoff`、`cross_entry` 两类，若整版确实不适用，在 `not_applicable` 中给出依据；只测了其中一个入口、尚无外部回执或缺资料均不能填作不适用。

所有适用关键路径均有通过证据才报整项通过。已测出错、待决定、未测分别写入操作记录和摘要，只能保留草稿或如实登记 `I=fail`（允许带部分结果）。更正后按同一条件复测。旧版已经生效的交接继续按原证据读取；旧草稿补录同版操作证据后可继续，新办 S2 交接须有闭环检查。脚本能核对已申报的步骤、顺序、对象及行号；原文结果是否全部纳入、终点是否选对以及外部回执是否真实，仍须据原始材料独立复核。

## question 与 checkpoint

question 字段：id、question、owner、next_action、blocking（布尔）、affected（条目ID数组）、status(open/closed)，可补候选、推荐、期限和升级人。关闭增加 resolution_evidence。阻塞问题将传递标记下游待更新；关闭后仍需按实际变化修订复核，不能直接恢复有效。
尚未形成任何条目的初始缺口先写在草案正文与 checkpoint，形成条目后登记 affected。
checkpoint：`{"requirement":"FIT-001","next_action":"S2-A06.1 等待业务负责人确认取消后课时规则；继续整理独立场景"}`。

## deliver

对本期各适用阶段显式列入主成果。S1 为 T01，S2 为含原型和实测记录的 T02，S3 为含布局、原型和实测记录的 T03，S4 为 P04 与 T04，S5 为 REQ、AC 与 T05。复用阶段还应列入计划指定的条目，选为不适用的阶段应说明业务理由。各条目完成 gate、promote 后，由产品经理确认 S5 交接到 delivery，覆盖本次包内的 S5 成果。再执行 `manifest --requirement <需求ID> --items <实际清单>` 向交付负责人呈现当前范围、版本和哈希，取得真实批准后执行 deliver。输入示意如下。
`{"requirement":"FIT-001","items":["实际条目ID"],"actor":"登记的交付授权人","result":"approved","conclusion":"实际批准结论","approved_manifest_sha256":"manifest返回哈希","evidence":{"kind":"human_reply","path":"snapshot返回的path值","locator":"批准段落"}}`。
deliver 返回自包含交付目录。delivery.json 的 handoff 保存产品经理的交接决定，approval 保存交付负责人针对具体清单的批准。清单或复核记录有变化时，先查看变化及原决定的范围，必要时重新确认。S4 不适用时，检查计划理由和其余适用阶段的成果。

导出成功仅记为 `exported`（已导出，待包内检查）。随后由 AI 按[交付规范](../stages/prd-authoring-and-review/references/delivery-protocol.md)实际打开包内文档、操作原型并检查图表，再登记实测；不把整理命令或填写验收 JSON 交给用户。

## delivery-check

先读 `resume.deliveries`，按实际交付编号取 `required_checks`；其中包含 documents、prototype、diagram 入口，按内容哈希去重，`aliases` 为同内容的其他登记路径。针对实际包路径和清单执行检查，快照真实操作日志，然后提交：

```json
{"number":1,"manifest_sha256":"本次实际清单哈希","actor":"实际执行者",
 "result":"pass","conclusion":"实际检查结论及未测范围",
 "evidence":{"kind":"operation","path":"实际日志快照相对路径","locator":"包内检查段落"},
 "checks":[
   {"kind":"documents","target":"required_checks返回的包内文档路径","result":"pass","conclusion":"实际阅读与链接核对结果"},
   {"kind":"prototype","target":"required_checks返回的包内原型路径","result":"pass","conclusion":"实际操作结果",
    "tasks":[{"task":"实际任务","expected":"预期结果","observed":"实际观察","result":"pass"}]}
 ]}
```

按返回的必检项填写，示例不是固定数量；PRD、SRS 分别检查，图表项用 `kind=diagram`。总日志须含准确交付包路径和 manifest 哈希，每项日志还须含其 target；原型任务、预期和实际观察须可在日志中定位。条目可另传 evidence，否则使用总日志。未执行不能编写通过记录。

工具检查包文件清单、元数据及哈希；通过须覆盖全部必检入口。登记 pass 后才显示 `delivered`（交付验收完成），fail 显示 `delivery_failed`；包缺失或损坏也可用空 checks 登记 fail，并说明实际发现。fail 成功登记的进程退出码为 0，非法输入或不满足通过条件为 1。证据或包后来变化，读取时重新显示验收未通过。旧项目仅有 delivered 而无验收记录时按待检查展示，读取不改写原状态。

记录保存在管理状态及“交付验收记录.md”，不会追加或修改已授权包。工具能核对记录结构与证据定位，不能认证观察真实性，包内操作也不代替真人验证。必要内容失败时修来源、生成新清单并核对其授权后重新导出；不要手改包。检查旧包不会覆盖需求的新修订状态。

## 错误与限制

S4 页面结构可另用只读辅助工具核对，格式及模板见 [页面结构规格](../stages/prototype-design/references/page-structure-spec.md)：

```text
python -X utf8 <skill_root>/scripts/prototype_structure_check.py --root <project_root> --spec <project_root>/结构规格.json --html <project_root>/原型.html --output <project_root>/结构检查.json
```

`--spec`、`--html` 为实际文件路径（相对当前命令目录或绝对路径），其解析结果必须位于 root 内；来源目录的 path 则相对 root。可检查原型 HTML 或实际浏览器取得的同版 DOM 快照；返回 STRUCTURE_ONLY、适用范围和文件哈希，失败退出码 1。表格/YAML 可导出同版 JSON 检查但保留唯一权威来源。报告纳入 Q04，不能直接转成 gate 通过、真人 verified 或交接授权。模板及 TEST 示例在建设测试中一起核对；工具不证明业务来源完整、信息语义、布局、权限或交互正确。

gate 不通过退出码2，输入或写入失败退出码1。只读 resume/manifest 不改变 revision。过期 expected_version 不覆盖；引用跨目标版本不自动转换。并发锁保留时等待写入者，确认进程结束后才处理残留。
没有后台调度和身份认证。人工决定真实性、覆盖充分性、页面实际可操作及跨条目同义冲突仍由执行者按证据核验。测试夹具不进入真实项目。所有本地写入可回查事件；不要手工绕开门禁修改 state。

## 版本与影响分析

`latest_version` 是最新稿；`current_valid_version` 定位已通过内容版本，内容未知、待分析或失效时为空。纯角色变更可保留该指针，但复用、生效、交接与交付必须同时通过当前授权检查，不能只看指针。`last_approved_version` 仅为历史参考。不能把历史批准等同于对当前目标有效。旧正文和记录保留在历史索引。

put 更新成果后产生传递影响候选；相关 current_valid 暂时置空，原有效版临时保留于 held_valid。按条目判断后：

```text
python -X utf8 <skill_root>/scripts/workspace.py --root <workspace_root> impact --data impact.json
```

payload：`source_id`、`source_version`、`target_id`、`result`（affected/unaffected）、`reason`、`actor`、`evidence`。证据结构同 record。affected 标待更新；unaffected 只能保留原本有效的版本，不能批准草稿，且所有待分析影响关闭才恢复指针。涉及新规则或取舍仍需人的实际决定。

## 业务阶段交接

```text
python -X utf8 <skill_root>/scripts/workspace.py --root <workspace_root> handoff --data handoff.json
```

payload 包含 requirement、from_stage、to_stage、items、actor、result=approved、conclusion、evidence。to_stage 为下一业务阶段，S5 后为 delivery。items 属于该阶段、包含 T01—T05 对应汇总成果；S4 还需 P04。必须已 promote 且当前 gate 通过，actor 是项目实际 product 责任人，证据为其真实回复或评审。脚本自动绑定版本与清单哈希。

展示成果、质量结论、未关闭问题与接续建议后取得继续决定。new 和 replan 对复用条目核对所属阶段、目标和当前有效版，并在 plan 的对应阶段记录 versions。handoff 可接收本需求成果及本期计划明确复用的同目标有效版本。恢复时查看每条交接的 current_applicable 与 applicability_errors，按范围和版本复用仍然适用的决定。测试数据中预设人员和批准均标明 TEST。

## 中文管理视图

写操作后在 `06-项目管理` 生成 `项目状态.md`、`项目版本记录.md`、`成果版本清单.md`、`变更记录.md`、`影响分析记录.md`、`阶段交接记录.md`、`待决事项.md`、`质量检查记录.md`、`交付验收记录.md`，以及固定入口 `查看与试用.html`。入口链接已登记的同版正文、原型、布局、操作记录和 SRS，分别展示候选与有效内容版本；授权失效的内容明确标为待授权复核，项目导航不替代正式包内入口。旧英文布局保留原有英文文件名，新增入口仍用上述中文名称。用 `views` 显式重建派生视图；它修复缺失或错误的视图而不改变 state revision，不新增或批准业务成果。只读接续使用 `resume`。阅读可用视图，维护仍通过 JSON 命令；不要手改视图来改变事实状态。

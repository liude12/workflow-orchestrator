# 独立视觉评审记录校验

用户 UI/UX 文档不是必需输入。`material_status=ready` 表示既有标准或具体 AI 暂定设计足以支撑本期实现；`standards` 可绑定该设计约定，`comparison` 可绑定设计条目与实际截图的配对。`brand_visual=pass` 在暂定范围仅表示该基线检查通过，不表示正式品牌批准。字段和实际证据要求不变。

先按 S4 的[资料准入与独立成品评审协议](../stages/prototype-design/references/visual-readiness-and-finish-gate.md)实际执行。该脚本仅检查提交记录及文件哈希是否自洽，不会生成评审、查看图片、认证评审者或授予阶段批准。

```text
python -X utf8 <skill_root>/scripts/ui_finish_gate.py --root <项目目录> --report <评审JSON绝对路径>
python -X utf8 <skill_root>/scripts/ui_finish_gate.py --root <项目目录> --report <原评审JSON绝对路径> --fixes <条件整改JSON绝对路径>
```

退出码：0 表示视觉评审的记录放行条件满足；2 表示有效记录仍需修改；1 表示记录或证据无效。脚本不写项目状态。执行者仍须核实真实检查、把结果登记到对应版本 I/V/Q，并独立完成原流程的功能检查、真人验证和交接。

## 评审 JSON

以下是字段示意，不是可以原样通过的记录。路径相对项目目录，SHA256 必须从实际冻结文件计算。report 保留原件，整改不覆盖原截图和实现文件。packet 可增加其他证据角色；必须有 standards、implementation、screenshot、comparison 四类。

```json
{
  "schema_version": 1,
  "reviewer": {"role": "UI Finish-Gate Reviewer", "isolated": true, "session": "实际独立会话标识"},
  "packet": {
    "id": "项目-P04-v1-视觉评审",
    "material_status": "ready",
    "material_version": "资料准入版本",
    "prototype_version": "P04-v1",
    "files": [
      {"role": "standards", "path": "04-原型验证/视觉标准/标准-v1.md", "sha256": "真实哈希"},
      {"role": "implementation", "path": "04-原型验证/视觉评审/v1/原型.html", "sha256": "真实哈希"},
      {"role": "screenshot", "path": "04-原型验证/视觉评审/v1/页面.png", "sha256": "真实哈希"},
      {"role": "comparison", "path": "04-原型验证/视觉评审/v1/并排对照.png", "sha256": "真实哈希"}
    ]
  },
  "conclusions": {
    "verdict": "go",
    "functional": {"status": "pending", "scope": "本轮未完成全部任务走查", "note": "待 A04", "evidence": ["04-原型验证/视觉评审/v1/原型.html"]},
    "brand_visual": {"status": "pass", "scope": "实际核对的页面及状态", "note": "写实际对照依据", "evidence": ["04-原型验证/视觉评审/v1/并排对照.png"]},
    "platform_adaptation": {"status": "pass", "scope": "实际检查的平台与尺寸", "note": "写实际结果，不外推", "evidence": ["04-原型验证/视觉评审/v1/页面.png"]},
    "user_validation": {"status": "pending", "scope": "未开展真人验证", "note": "AI 评审不是用户验证", "evidence": ["04-原型验证/视觉评审/v1/原型.html"]}
  },
  "opinions": []
}
```

verdict 仅 go / no-go / conditions-go。功能、品牌视觉、平台适配的 status 为 pass / fail / pending / not-applicable / conditions；用户验证为 verified / waived / pending，前两者仍须真实有效依据。每类必须说明范围、结论和包内证据。

go 要求品牌视觉 pass、平台 pass 或说明不适用，不能留下必改意见。conditions-go 的品牌/平台不能存在未解决阻塞，使用 conditions 表示有限且可验收的修改。no-go、conditions-go 都须有至少一条必改意见：

```json
{"id":"UI-01","target":"页面与具体区域","problem":"实际发现的问题","requested_change":"本轮明确修改动作","acceptance_criteria":"可检验完成标准","required":true}
```

no-go 修改后生成新版本材料和新独立评审，不能用 fixes 绕过，不设评审次数上限。评审者仅收到冻结包，无开发聊天、自评或旧评审结论；必须实际查看规范参考和页面对照。字段 isolated=true 本身不是隔离证据。

## conditions-go 的一次整改记录

保留原评审结论；执行者只核对原意见是否完成，不新增意见、不进行第二轮专家评审。未完成保持待整改。round 固定为 1，不可借多份文件把第二轮包装成第一次；阶段记录需检查唯一性。

```json
{
  "report_sha256": "原评审 JSON 真实哈希",
  "packet_id": "原评审 packet.id",
  "round": 1,
  "verification_kind": "implementation-check",
  "changes": [{"opinion_id":"UI-01","status":"done","note":"实际完成内容及验收结果","evidence":[{"path":"04-原型验证/视觉评审/v1-整改/证据.png","sha256":"真实哈希"}]}],
  "after_files": [
    {"role":"implementation","path":"04-原型验证/视觉评审/v1-整改/原型.html","sha256":"真实哈希"},
    {"role":"screenshot","path":"04-原型验证/视觉评审/v1-整改/证据.png","sha256":"真实哈希"}
  ],
  "standards_sha256": {"04-原型验证/视觉标准/标准-v1.md":"原标准真实哈希"}
}
```

`changes` 按原意见编号逐项记录实际完成情况，覆盖全部必改意见。执行者打开修改后的文件，与原验收条件逐项核对。

把本轮完整实现和截图列入 `after_files`，使用区别于原冻结包的实际路径。普通视觉修改应有内容发生变化的实现和截图。每条意见的 `changes[].evidence` 至少定位其中一份与该意见相关的变更文件。页面样式来自独立 CSS 时，把修改的 CSS 也以 `implementation` 登记。可以同时附上未涉及修改的页面或状态以便对照。

如果意见专门要求重新采集截图或补充偏离理由，评审者可在**原报告的相应意见**预先写明 `"required_changed_roles":["screenshot"]` 或 `["comparison"]`。可选类型为 `implementation`、`screenshot`、`comparison`。执行者提交完整的本轮实现和截图，逐项引用所列类型的变更文件。只改文件名或路径且内容与原冻结文件相同的附件只能用于对照。

标准继续绑定原哈希，更换规范或范围时另建版本。脚本返回 `ui_finish_gate_passed` 表示视觉评审记录的处理结果，阶段交接和用户验证各自记录。

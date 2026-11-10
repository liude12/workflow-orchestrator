# 页面结构规格与辅助校验

本规格是 T04 正文或同版附件中的实现映射，不新增成果类型、审批或第二套状态。页面继续使用既有 PAGE，任务、功能、规则继续引用 TASK/FUN/RULE 的确切版本；区域、控件、状态只是 PAGE 内的稳定标识。名称或布局变化不随意换标识；删除、合并、拆分时在既有反馈修订记录说明旧标识去向及来源决定。

设计依据、信息含义、层级、操作顺序和状态触发条件按[设计与映射规范](design-and-mapping.md)记录。下述字段承担定位与结构检查，不能替代这些语义说明。完整新原型覆盖本期范围；小改动可只列受影响页面、任务、区域与相关状态，复用未改变的有效记录。不要为了表格齐全创造新业务规则或为纯信息区域强加按钮。

## 表达形式与唯一来源

可以使用清楚的表格、YAML 或 JSON。选择团队能够维护和核对的形式；自动工具接受 JSON v1。采用表格或 YAML 时，临时导出同版 JSON 并记下来源版本/哈希、转换范围，检查后回到权威记录修正，不能手工维护两份互相冲突的规格。JSON 可直接作为 T04 附件成为唯一结构记录。

[JSON 示例模板](../assets/templates/page-structure-spec.json)是完整填写的 TEST 结构例子，配套[来源摘录](../assets/examples/page-structure/sources.md)、[规格](../assets/examples/page-structure/spec.json)和[结构 HTML](../assets/examples/page-structure/prototype.html)一起接受校验。模板中的 TEST 标签不是工作空间有效条目；用于项目时换成实际来源和版本。配套 HTML 明确不实现按钮，仅证明校验器能区分结构证据与功能证据。

## JSON v1 字段

| 字段 | 内容与核对依据 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `sources` | 引用目录：每条有 `ref`（`ID@版本`）、`kind`（T02/T03/T04/P04/SCN/PAGE/FUN/RULE/TASK/NFR）、`path`（项目根目录下相对路径）、`sha256`、`locator`。同一 ID 只采用一个适用版本；一个正文中多个条目可共享路径和哈希，用 locator 定位。有效性与授权仍从原项目索引核对，文件哈希不能证明有效。 |
| `scope` | `mode` 为 `full` 或 `partial`；`pages`、`tasks` 为本轮确切引用数组；`reason` 解释本期/局部范围及排除依据。full 必须覆盖目录中的全部 PAGE/TASK，但目录本身是否漏取上游内容仍须人工语义核对。partial 同页仍保留未改标记时，用下述 `excluded` 明确复用边界。 |
| `requirements` | 从 S3 布局/任务及适用决定独立提取的必需清单，每页一行：`page`、`tasks`、`source_refs`、`regions`、`states`、`controls`（必需操作控件，纯信息页填空数组）。不能从已做好的 HTML 反推清单，也不能为了通过检查删除未实现项。新增细节回相应主记录；真实范围调整才更新必需清单。 |
| `pages` | 实现映射，每页 `ref` 关联既有 PAGE，包含 `regions` 与 `states`；覆盖 scope 中全部页面。 |
| `pages[].regions` | 每区有稳定 `id`、`source_refs`、`controls`；controls 可为空。可在同一记录附信息含义、优先级、布局、显示条件与设计依据，不另造平行文档。 |
| `regions[].controls` | 每个控件有稳定 `id`、`source_refs`；在 PAGE 内唯一。可补名称、操作、反馈等语义，引用 S3 唯一行为来源。 |
| `pages[].states` | 每状态有稳定 `id`、`source_refs`、承载它的 `regions` 和相关 `controls`（可为空）。控件必须属于该状态所列区域；可补触发、可见信息、权限与退出/恢复条件。 |

来源引用必须精确匹配目录。必需区域、状态及控件必须存在于映射；每个本轮任务必须分配到页面；每页必需来源必须在该页区域/控件/状态中落点。稳定标识不能含空白、`/` 或 `@`。跨页面可复用区域/控件/状态的局部名称，引用时连同 PAGE 解释，不能只凭中文显示文案匹配。

### 局部修改的复用边界

局部规格可以只映射受影响区域，同时保留完整 HTML。对于同页未列入本轮映射的已有标记，`scope.excluded` 每页一项，包含 `page`、`regions`、`controls`、`states`、`source_refs`、`reason`。regions/controls 为页内标识数组；states 为 `{ "id": "empty", "regions": ["feedback"] }` 数组，按状态承载区域表达边界。例如只改列表时，可在规格中检查 list 的 empty 状态，明确复用旧版 feedback 的 empty 状态；source_refs 指向已有确切来源，reason 写清复用版本/位置及不受影响的依据。

排除项不能与本轮检查的区域、控件或状态—区域对应重叠，也不能遮蔽必需清单。未明确复用的未知标记仍报错，避免拼错 ID 被当作范围外内容。报告把遇到的复用标记列为 `unchecked_regions`、`unchecked_controls`、`unchecked_states`，整页在 scope.pages 外则列为 `unchecked_pages`；这些范围未经本轮核验，不能从局部通过推导全页/全阶段通过。无同页复用标记时无需增加空排除表。

## HTML 定位标记

在真实承载信息或行为的元素上使用属性，不在页面可见文案中暴露维护编号：

```html
<main data-ui-page="DEMO-PAGE-01">
  <section data-ui-region="task-list" data-ui-state="normal empty">
    <template>
      <button data-ui-control="open">查看</button>
    </template>
  </section>
</main>
<p data-ui-owner="DEMO-PAGE-01" data-ui-region="feedback"
   data-ui-state="saved failed" role="status"></p>
```

- `data-ui-page` 为 PAGE 的 ID 部分，不含版本；确切版本由 JSON 引用绑定，每页一个页面标记。
- `data-ui-region`、`data-ui-control`、`data-ui-state` 对应规格中的页内标识。嵌套时从祖先取得所属页面/区域。状态可用空格分隔多个已声明状态，表达该元素**承载哪些状态**，不表示这些状态现在同时发生，也不证明已实现状态切换。
- 一个状态可以同时影响多个区域，按 PAGE＋状态＋区域核对。`states[].regions` 所列每个区域都须有相应承载标记；同状态在不同区域出现合法，在同一区域重复声明报错。只把状态挂在 PAGE 根、没有区域归属不能证明覆盖。
- 共享反馈/浮层不必为了校验移动 DOM；外置元素用 `data-ui-owner="PAGE-A PAGE-B"` 明确归属。外置控件另用 `data-ui-region-owner="区域ID"`；显式归属不能与现有父级冲突。共享区域必须在每个对应 PAGE 的映射中出现。
- 动态列表同类控件保留同一 `data-ui-control`，每个实际实例增加稳定业务键 `data-ui-instance="task-123"`。同页同控件的实例键不可重复；没有实例键的重复控件报错。一个模板声明可与其实际实例同时存在。不要为每条示例数据增加一套规格控件。
- 原生 HTML `id` 按所属 DOM 树查重：主 document 和各个 `template.content` 独立；模板元素本身的 id 仍属于父树。模板内容与一个实际克隆可同名，同一 document 或同一个模板内容树内的重名仍报错。
- 工具读取 HTML 元素，不把脚本中的字符串、注释或截图当成已实现节点。可用实际渲染所用的 `<template>` 声明动态节点；报告会单列 template-only，不能把空壳模板算作交互完成。也可对浏览器实际取得的同版 DOM 快照运行结构检查，保留快照来源、视口/状态及原型哈希，避免把别版/别状态快照混用。
- 必需映射缺标记时应定位真实承载元素或修正实现；不要添加仅供过检、与实际页面无关的隐藏节点。隐藏内容本身有用途时保留，但其存在只证明声明，不证明可见性与可操作性。

## 运行与结果

```text
python -X utf8 <skill_root>/scripts/prototype_structure_check.py --root <project_root> --spec <project_root>/结构规格.json --html <project_root>/原型.html --output <project_root>/结构检查.json
```

来源路径必须位于 root 内，不允许 `..`、绝对路径或逃逸的链接；spec/HTML 也须位于 root 内。首次错误给出字段或 HTML 行号定位，退出码 `1`；通过返回 `kind=STRUCTURE_ONLY`、范围、文件哈希、标记数量、template-only 与未检查页面，退出码 `0`。输出仅是结构检查结果，不能直接驱动 promote、handoff 或 verified。

与实际证据一起纳入原 Q04：01 核对任务和适用状态范围，02 结合真实操作检查入口与反馈，03 对照信息含义、权限、规则、布局与有效方案，05 处理增量变更和相关任务复验，06 绑定规格/HTML/来源与证据版本。Q04-04 真实用户验证或有效豁免仍独立记录；静态通过、DOM 快照及内部操作都不能代替真人证据。

工具可发现错误引用/版本、源文件变化、重复标识、必需映射遗漏、HTML 标记遗漏与错误归属。它不能判定业务清单是否完整、locator 语义是否正确、规则是否真实有效、像素布局是否合理、控件是否生效或状态是否能到达。必须实际查看和操作关键任务，再将预期、实际、差异与原始证据回填唯一 T04 记录。

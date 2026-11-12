"use strict";
(() => {
  const $ = id => document.getElementById(id), data = window.CATALOG;
  if (!data) { $("status").textContent = "加载失败，请刷新页面；也可直接下载完整数字池。"; return; }
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
  const fmt = n => n.toLocaleString("en-US"), translated = text => data.zh[text];
  const sources = {regular:"普通任务", emerging_new:"Emerging · 新增", emerging_revision:"Emerging · 修订"};
  const labels = {DIGITAL:"数字候选", PHYSICAL:"物理操作", UNCERTAIN:"待审核"};
  const sampled = new Set(data.sampled_ids), report = data.report;
  let filtered = [], currentPage = 0, language = "both";
  const tasks = data.tasks, occupations = new Map(tasks.map(t => [t.occupation_code,t.occupation_title]));
  const searchIndex = new Map(tasks.map(t => [t.seed_id, [t.seed_id,t.task_id,t.original_task_id||"",t.task_text,translated(t.task_text)||"",t.occupation_code,t.occupation_title,translated(t.occupation_title)||"",t.work_domain,translated(t.work_domain)||"",...t.dwa_ids.flatMap(id=>[id,data.dwas[id],translated(data.dwas[id])||""])].join(" ").toLowerCase()]));
  function option(select, value, text) { const o = el("option",text); o.value=value; select.append(o); }
  function readable(text) { return language === "en" ? text : translated(text)||text; }
  function content(parent,text,tag="p",cls="") {
    parent.append(el(tag,readable(text),cls));
    if (language === "both" && translated(text)) parent.append(el("p",text,"original-text"));
    if (language !== "en" && !translated(text)) parent.append(el("small","暂无中文译文 · 显示官方原文","muted"));
  }
  const digital = tasks.filter(t=>t.digital_label==="DIGITAL");
  const complete = data.validation.digital_pool_complete && digital.length === report.counts.digital_tasks;
  $("status").textContent = complete ? `✓ 全量载入 ${fmt(digital.length)} 条数字候选 · 来源原文核验通过 · ${fmt(data.validation.digital_translated)} 条有中文阅读译文` : "完整性校验失败，请检查构建报告。";
  if (!complete) $("status").classList.add("error");
  [["完整数字候选池",digital.length,"全部 DIGITAL，不限于采样"],["覆盖职业",report.digital_coverage.occupations,"至少一条数字候选任务"],["SOC 职业大类",report.digital_coverage.major_groups,"按官方职业代码归类"],["Emerging 数字候选",digital.filter(t=>t.task_source!=="regular").length,"新增与修订后的有效任务"]].forEach(([label,n,note])=>{const c=el("div",undefined,"metric");c.append(el("div",label,"label"),el("div",fmt(n),"value"),el("div",note,"note"));$("metrics").append(c);});
  Object.entries(sources).forEach(([key,label])=>{const n=report.digital_coverage.source_counts[key]||0,bar=el("span");bar.style.width=(n/digital.length*100)+"%";bar.title=`${label} ${n}`;$("source-bar").append(bar);$("source-legend").append(el("span",`${label} ${fmt(n)}`));});
  const conflict = report.merge.quarantined_original_task_ids;
  $("merge-note").textContent = `${fmt(report.counts.regular_original)} 条普通任务与 ${report.counts.emerging_raw} 行 Emerging，经 ${report.counts.successful_revision_replacements} 次修订替换后得到 ${fmt(tasks.length)} 条有效任务。${conflict.length ? `冲突隔离：原 Task ${conflict.join("、")} 及其冲突修订未进入候选池。` : "没有待解决的修订冲突。"}`;
  $("pool-hash").textContent=data.validation.digital_sha256;
  function scopeRows() { const s=$("scope").value;return tasks.filter(t=>s==="ALL"||(s==="SAMPLED"?sampled.has(t.seed_id):t.digital_label===s)); }
  function refreshOptions() {
    const base=scopeRows(),group=$("group").value,occupation=$("occupation").value;
    const counts=new Map();base.forEach(t=>counts.set(t.occupation_code.slice(0,2),(counts.get(t.occupation_code.slice(0,2))||0)+1));
    $("group").replaceChildren();option($("group"),"all","全部大类");
    Object.entries(data.groups).forEach(([code,name])=>option($("group"),code,`${code} · ${readable(name)} (${fmt(counts.get(code)||0)})`));$("group").value=group;
    const occCounts=new Map();base.filter(t=>group==="all"||t.occupation_code.startsWith(group+"-")).forEach(t=>occCounts.set(t.occupation_code,(occCounts.get(t.occupation_code)||0)+1));
    $("occupation").replaceChildren();option($("occupation"),"all","全部职业");
    [...occCounts.keys()].sort().forEach(code=>option($("occupation"),code,`${code} · ${readable(occupations.get(code))} (${occCounts.get(code)})`));
    $("occupation").value=occCounts.has(occupation)?occupation:"all";
  }
  function applyFilters() {
    const terms=$("search").value.toLowerCase().trim().split(/\s+/).filter(Boolean),group=$("group").value,occupation=$("occupation").value,source=$("source").value;
    filtered=scopeRows().filter(t=>(group==="all"||t.occupation_code.startsWith(group+"-"))&&(occupation==="all"||t.occupation_code===occupation)&&(source==="all"||t.task_source===source)&&terms.every(term=>searchIndex.get(t.seed_id).includes(term)));
    currentPage=0;render();
  }
  function render() {
    const size=Number($("page-size").value),pages=Math.max(1,Math.ceil(filtered.length/size));currentPage=Math.max(0,Math.min(currentPage,pages-1));
    $("result-count").textContent=`${fmt(filtered.length)} 条任务`;
    $("result-note").textContent=`当前筛选覆盖 ${new Set(filtered.map(t=>t.occupation_code)).size} 个职业 · ${new Set(filtered.map(t=>t.occupation_code.slice(0,2))).size} 个 SOC 大类 · 顶部统计始终为完整数字池`;
    $("task-list").replaceChildren();
    filtered.slice(currentPage*size,(currentPage+1)*size).forEach(t=>{
      const card=el("article",undefined,"seed-card"),head=el("div",undefined,"task-meta");card.dataset.seedId=t.seed_id;
      head.append(el("span",sources[t.task_source],"badge source-"+t.task_source),el("span",labels[t.digital_label],"badge decision-"+t.digital_label));
      if(sampled.has(t.seed_id))head.append(el("span","已入选 200 条采样","badge sampled"));
      head.append(el("code",t.task_id,"task-id"));card.append(head);
      content(card,t.task_text,"h3","task-text");
      const context=el("div",undefined,"occupation-context"),link=el("button",`${t.occupation_code} · ${readable(t.occupation_title)}`,"occupation-link");link.type="button";link.onclick=()=>{$("group").value=t.occupation_code.slice(0,2);refreshOptions();$("occupation").value=t.occupation_code;applyFilters();};
      context.append(link,el("span",readable(t.work_domain)));card.append(context);
      const details=el("details",undefined,"seed-details");details.append(el("summary","查看来源、分类依据与工作活动"));
      const meta=t.source_metadata,annotation=meta.digital_annotation;
      details.append(el("p",`Seed ID：${t.seed_id}`,"mono"),el("p",`标签来源：${t.digital_label_source}${t.digital_label_source==="LLM"?" · GLM-5.2 辅助分类":" · 外部研究标注"}`));
      if(annotation.reason)details.append(el("p","分类理由（模型英文输出）："+annotation.reason));
      if(annotation.rule)details.append(el("p",`标注规则：${annotation.rule} · AI4Work 记录行：${annotation.annotation_row||"未匹配"}${Object.hasOwn(annotation,"original_label")?` · 上游标签：${annotation.original_label||"空"}`:""}`));
      const filename=report.record_format.source_files[t.task_source];details.append(el("p",`官方来源：${filename} · CSV 记录 ${meta.row}（含表头） · 日期 ${meta.date} · ${meta.domain_source}`));
      const a=el("a","查看官方数据字典 ↗");a.href=`https://www.onetcenter.org/dictionary/31.0/csv/${t.task_source==="regular"?"task_statements":"emerging_tasks"}.html`;a.target="_blank";a.rel="noopener";details.append(a);
      if(t.original_task_id)details.append(el("p",`Revision 替换的旧 Task ID：${t.original_task_id}。当前仅展示官方修订文本。`));
      if(meta.task_type)details.append(el("p","官方任务类型："+meta.task_type));
      details.append(el("h4","关联的详细工作活动 · DWA"));
      t.dwa_ids.forEach(id=>{const row=el("div",undefined,"dwa");row.append(el("code",id));content(row,data.dwas[id]);details.append(row);});
      if(!t.dwa_ids.length)details.append(el("p","无官方 DWA 映射；未推断或继承旧任务的关联。","muted"));
      const raw=el("details");raw.append(el("summary","查看完整 Raw Seed JSON"),el("pre",JSON.stringify(t,null,2)));details.append(raw);card.append(details);$("task-list").append(card);
    });
    if(!filtered.length)$("task-list").append(el("p","没有符合条件的任务。请调整筛选或点击“重置筛选”。","empty"));
    $("page").textContent=filtered.length?`${currentPage*size+1}–${Math.min((currentPage+1)*size,filtered.length)} / ${fmt(filtered.length)} · 第 ${currentPage+1} / ${pages} 页`:"0 条任务";
    $("prev").disabled=currentPage===0;$("next").disabled=currentPage+1>=pages;$("export").disabled=!filtered.length;
    $("page-number").max=pages;$("page-number").value=currentPage+1;
  }
  $("scope").onchange=()=>{refreshOptions();applyFilters();};$("group").onchange=()=>{refreshOptions();applyFilters();};
  $("source").onchange=$("occupation").onchange=applyFilters;
  $("language").onchange=()=>{language=$("language").value;refreshOptions();render();};
  let timer;$("search").oninput=()=>{clearTimeout(timer);timer=setTimeout(applyFilters,120);};
  $("page-size").onchange=()=>{currentPage=0;render();};
  $("prev").onclick=()=>{currentPage--;render();};$("next").onclick=()=>{currentPage++;render();};
  $("go").onclick=()=>{const n=Number($("page-number").value);currentPage=Number.isFinite(n)?Math.floor(n)-1:0;render();};
  $("page-number").onkeydown=e=>{if(e.key==="Enter")$("go").click();};
  $("reset").onclick=()=>{$("search").value="";$("scope").value="DIGITAL";$("group").value=$("occupation").value=$("source").value="all";refreshOptions();applyFilters();};
  $("export").onclick=()=>{const url=URL.createObjectURL(new Blob([filtered.map(t=>JSON.stringify(t)).join("\n")+"\n"],{type:"application/x-ndjson;charset=utf-8"})),a=el("a");a.href=url;a.download=`raw-seeds-${$("scope").value.toLowerCase()}-${filtered.length}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  refreshOptions();applyFilters();
})();

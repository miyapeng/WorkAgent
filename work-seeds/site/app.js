"use strict";
(() => {
  const $ = id => document.getElementById(id), data = window.CATALOG;
  if (!data) { $("status").textContent="目录加载失败，请确认 catalog.js 存在。"; return; }
  const fmt = n => n.toLocaleString("en-US");
  const el = (tag,text,cls) => { const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; };
  const report=data.report, dr=data.digital_report, zh=data.translations;
  const decisions=new Map(data.decisions.map(d=>[d.task_id,d])), byOccupation=new Map(), byTask=new Map(), dwas=new Map(data.dwas);
  data.tasks.forEach(t=>{if(!byOccupation.has(t[1]))byOccupation.set(t[1],[]);byOccupation.get(t[1]).push(t);});
  data.task_dwa.forEach(([t,d])=>{if(!byTask.has(t))byTask.set(t,[]);byTask.get(t).push(d);});
  const labels={DIGITAL:"数字任务候选",PHYSICAL:"现场 / 物理任务",REVIEW:"待核对"}, types={Core:"核心",Supplemental:"补充",Missing:"未标注"};
  let scope="DIGITAL",language="zh",selected=null,occupationPage=0,taskPage=0,scopedTasks=[],scopedOccupations=[],scopedByOccupation=new Map();
  const occupationSize=25, taskSize=12;
  const translated=(table,id,original)=>language==="en"?original:zh[table][id];
  function addText(parent,table,id,original,tag="p",cls=""){
    parent.append(el(tag,translated(table,id,original),cls));
    if(language==="both")parent.append(el("div",original,"original-text"));
  }
  Object.values(dr.rules).forEach(rule=>$("rule-list").append(el("li",rule)));
  const ok=report.all_checks_passed&&dr.all_checks_passed&&data.decisions.length===data.tasks.length;
  $("status").textContent=ok?"✓ 原始目录与筛选完整性检查通过 · 全量底表保留 · 中文译文不参与筛选":"数据校验未通过";
  if(!ok)$("status").classList.add("error");
  const checkNames={occupation_primary_key:"职业主键唯一",task_primary_key:"任务主键唯一",dwa_primary_key:"活动主键唯一",task_dwa_primary_key:"关联复合主键唯一",task_occupation_foreign_key:"任务职业外键完整",task_dwa_foreign_keys:"活动关联外键完整",all_occupations_preserved:"职业全量保留",all_tasks_preserved:"任务全量保留",all_observed_dwas_preserved:"工作活动全量保留",all_links_preserved:"关联全量保留",csv_roundtrip_preserves_values:"CSV 回读与原值一致"};
  Object.entries(report.checks).forEach(([k,v])=>$("checks").append(el("div",(v?"":"失败：")+(checkNames[k]||k),v?"check":"")));
  Object.entries(report.raw_files).forEach(([name,s])=>{const p=el("p");p.append(el("strong",name),el("div",`${fmt(s.raw_rows)} 原始行 / ${fmt(s.exact_duplicate_rows_removed)} 完全重复行`),el("code",s.sha256));$("hashes").append(p);});
  function setScope(){
    scopedTasks=data.tasks.filter(t=>scope==="ALL"||decisions.get(t[0]).decision===scope);
    scopedByOccupation=new Map();scopedTasks.forEach(t=>{if(!scopedByOccupation.has(t[1]))scopedByOccupation.set(t[1],[]);scopedByOccupation.get(t[1]).push(t);});
    scopedOccupations=data.occupations.filter(o=>scope==="ALL"||scopedByOccupation.has(o[0]));
    if(!scopedOccupations.some(o=>o[0]===selected))selected=scopedOccupations[0]?.[0]??null;
    occupationPage=taskPage=0;$("occupation-search").value="";$("task-search").value="";$("task-type").value="all";
    const ids=new Set(scopedTasks.map(t=>t[0])),links=data.task_dwa.filter(r=>ids.has(r[0])),activityIds=new Set(links.map(r=>r[1]));
    $("scope-note").textContent=`全量 ${fmt(report.counts.tasks)} 条：数字候选 ${fmt(dr.decisions.DIGITAL||0)} · 现场/物理 ${fmt(dr.decisions.PHYSICAL||0)} · 待核对 ${fmt(dr.decisions.REVIEW||0)}`;
    $("metrics").replaceChildren();
    [[scope==="ALL"?"全部职业":"涉及职业",scopedOccupations.length,scope==="ALL"?"含无任务记录的职业":"至少含一条当前视图任务"],["任务",scopedTasks.length,"保留官方原始任务 ID"],["详细工作活动",activityIds.size,"当前任务关联的不同 DWA"],["任务—活动关联",links.length,"保留每条任务的全部关联"]].forEach(([label,n,note])=>{const card=el("div",undefined,"metric");card.append(el("div",label,"label"),el("div",fmt(n),"value"),el("div",note,"note"));$("metrics").append(card);});
    $("type-bar").replaceChildren();$("type-legend").replaceChildren();
    ["Core","Supplemental","Missing"].forEach((type,i)=>{const count=scopedTasks.filter(t=>(t[3]||"Missing")===type).length;const bar=el("span");bar.style.width=(scopedTasks.length?count/scopedTasks.length*100:0)+"%";bar.title=types[type]+": "+count;$("type-bar").append(bar);const label=el("span"),dot=el("i");dot.style.background=["#146b56","#a2baac","#d5b77d"][i];label.append(dot,document.createTextNode(types[type]+" "+fmt(count)));$("type-legend").append(label);});
    $("coverage-note").textContent=scope==="REVIEW"?`未匹配 ID：${dr.rules_applied.R3_UNMATCHED||0}；文本或职业变更：${dr.rules_applied.R4_CHANGED||0}；未标注：${dr.rules_applied.R5_UNLABELED||0}。待核对不等于非数字任务。`:`当前视图：${scope==="ALL"?"官方全量目录":labels[scope]}。职业进入数字子集，不代表该职业所有职责均可数字化。`;
    occupations();tasks();
  }
  function occupations(){
    const query=$("occupation-search").value.toLowerCase().trim();
    const filtered=scopedOccupations.filter(o=>(o.join(" ")+" "+zh.occupations[o[0]]).toLowerCase().includes(query));
    const max=Math.max(1,Math.ceil(filtered.length/occupationSize));occupationPage=Math.min(occupationPage,max-1);
    $("occupation-total").textContent=fmt(filtered.length)+" 个";$("occupation-list").replaceChildren();
    filtered.slice(occupationPage*occupationSize,(occupationPage+1)*occupationSize).forEach(([code,title])=>{
      const button=el("button",undefined,"occupation"+(selected===code?" active":""));button.type="button";button.setAttribute("aria-pressed",String(selected===code));
      button.append(el("small",`${code} · ${(scopedByOccupation.get(code)||[]).length} 条任务`));addText(button,"occupations",code,title,"strong");
      button.onclick=()=>{selected=code;taskPage=0;$("task-search").value="";$("task-type").value="all";occupations();tasks();};$("occupation-list").append(button);
    });
    if(!filtered.length)$("occupation-list").append(el("p","当前视图没有匹配的职业。","empty"));
    $("occ-page").textContent=`${occupationPage+1} / ${max}`;$("occ-prev").disabled=occupationPage===0;$("occ-next").disabled=occupationPage+1>=max;
  }
  function tasks(){
    const occupation=data.occupations.find(o=>o[0]===selected);$("task-list").replaceChildren();
    if(!occupation){$("occupation-title").textContent="当前视图没有职业";$("occupation-original").textContent="";$("occupation-summary").textContent="";$("occupation-code").textContent="";$("task-page").textContent="0 条任务";$("task-prev").disabled=$("task-next").disabled=true;return;}
    const all=scopedByOccupation.get(selected)||[],query=$("task-search").value.toLowerCase().trim(),type=$("task-type").value;
    const filtered=all.filter(t=>(type==="all"||t[3]===type)&&(t[0]+" "+t[2]+" "+zh.tasks[t[0]]).toLowerCase().includes(query));
    const max=Math.max(1,Math.ceil(filtered.length/taskSize));taskPage=Math.min(taskPage,max-1);
    $("occupation-code").textContent="职业代码 / "+occupation[0];$("occupation-title").textContent=translated("occupations",occupation[0],occupation[1]);
    $("occupation-original").textContent=language==="both"?occupation[1]:"";
    $("occupation-summary").textContent=`当前 ${all.length} 条任务 / 该职业原始 ${(byOccupation.get(selected)||[]).length} 条 · ${new Set(all.flatMap(t=>byTask.get(t[0])||[])).size} 个关联活动`;
    filtered.slice(taskPage*taskSize,(taskPage+1)*taskSize).forEach(t=>{
      const d=decisions.get(t[0]),item=el("section",undefined,"task"),meta=el("div",undefined,"task-meta"),type=t[3]||"Missing";
      meta.append(el("span","任务 / "+t[0]),el("span",types[type],"badge "+type.toLowerCase()),el("span",labels[d.decision],"badge decision-"+d.decision));item.append(meta);addText(item,"tasks",t[0],t[2]);
      const why=el("details",undefined,"decision-detail"),summary=el("summary","筛选依据 · "+d.rule_id);why.append(summary,el("p",dr.rules[d.rule_id]));
      if(d.source_row){why.append(el("p",`AI4Work 表格第 ${d.source_row} 行 · 原始标签：${d.source_label||"空值"}`));const a=el("a","查看固定版本标注文件 ↗");a.href=dr.source.page;a.target="_blank";a.rel="noopener";why.append(a);}
      if(d.source_reason){const original=el("details");original.append(el("summary","查看上游英文原始理由"),el("p",d.source_reason));why.append(original);}item.append(why,el("div","关联的详细工作活动","dwa-label"));
      const related=byTask.get(t[0])||[];related.forEach(id=>{const row=el("div",undefined,"dwa");row.append(el("code",id));addText(row,"dwas",id,dwas.get(id),"span");item.append(row);});
      if(!related.length)item.append(el("div","原始数据未提供工作活动映射。","muted"));$("task-list").append(item);
    });
    if(!filtered.length)$("task-list").append(el("p",all.length?"没有匹配的任务。":"当前视图没有任务记录；官方职业记录仍保留。","empty"));
    $("task-page").textContent=`${filtered.length} 条任务 · ${taskPage+1} / ${max}`;$("task-prev").disabled=taskPage===0;$("task-next").disabled=taskPage+1>=max;
  }
  $("scope").onchange=()=>{scope=$("scope").value;setScope();};
  $("language").onchange=()=>{language=$("language").value;occupations();tasks();};
  $("occupation-search").oninput=()=>{occupationPage=0;occupations();};
  $("task-search").oninput=$("task-type").onchange=()=>{taskPage=0;tasks();};
  $("occ-prev").onclick=()=>{occupationPage--;occupations();};$("occ-next").onclick=()=>{occupationPage++;occupations();};
  $("task-prev").onclick=()=>{taskPage--;tasks();};$("task-next").onclick=()=>{taskPage++;tasks();};
  setScope();
})();

const $ = id => document.getElementById(id);
const form = $("form"), input = $("url"), statusText = $("status"), resultsSection = $("results");
const homeScreen = $("home"), manualScreen = $("manual"), databaseScreen = $("database");
const databaseForm = $("database-form"), methodSelect = $("method"), databaseSubmit = $("database-submit");
const batchSection = $("batch-results"), batchRows = $("batch-rows"), batchProgress = $("batch-progress");
let lastManual = null, activeScan = null, activeManual = null, batchRecords = [], batchParams = {}, batchComplete = false, methodLoad = 0;

function buildReport(scanType, records, parameters) {
    const ok = records.filter(r => !r.error), bad = records.filter(r => r.error), signals = {};
    for (const r of ok) for (const m of r.results) signals[m.word] = (signals[m.word] || 0) + m.count;
    return { schema_version: 1, scan_type: scanType, generated_at: new Date().toISOString(), parameters,
        summary: { urls: records.length, fetched: ok.length, failed: bad.length,
            total_matches: ok.reduce((sum,r) => sum + r.total,0), urls_with_matches: ok.filter(r => r.total > 0).length,
            signals: Object.fromEntries(Object.entries(signals).sort((a,b) => b[1]-a[1])) },
        results: ok.map(r => ({url:r.url,status:r.status,source:r.source,total:r.total,matches:r.results,assessment:r.assessment})),
        errors: bad.map(r => ({url:r.url,error:r.error})) };
}
function downloadBlob(blob, filename) {
    const link = document.createElement("a"), href = URL.createObjectURL(blob);
    link.href = href; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
}
function downloadReport(scanType, records, parameters) {
    const report = buildReport(scanType, records, parameters);
    downloadBlob(new Blob([JSON.stringify(report,null,2)+"\n"], {type:"application/json"}), `scan-${scanType}.json`);
}
function fetched(record) { return !record.error && record.status >= 200 && record.status < 300; }
function assessment(record) {
    return record.assessment || {score:null, level:"Not assessed", explanation:"No assessment is available for this page.",action:"Review the source manually if needed.",factors:[]};
}
function scoreLabel(a) { return Number.isFinite(a.score) ? `${a.score}/100` : "Not assessed"; }
function setPriority(element, a) {
    element.textContent = Number.isFinite(a.score) ? `${a.level} priority` : "Not assessed";
    element.className = "priority " + (Number.isFinite(a.score) ? a.level.toLowerCase() : "");
}
function explainFactors(list, a) {
    list.replaceChildren();
    for (const factor of a.factors || []) {
        const li = document.createElement("li");
        li.textContent = `${factor.name} (+${factor.points}): ${factor.evidence}`;
        list.append(li);
    }
}
async function exportPDF(button, scanType, records, parameters, complete = true) {
    const label = button.textContent; button.disabled = true; button.textContent = "Preparing PDF…";
    try {
        const response = await fetch("/api/export/pdf", {method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({scan_type:scanType,records,parameters,complete})});
        if (!response.ok) throw new Error("PDF export unavailable. Check the server's Python dependencies and try again.");
        downloadBlob(await response.blob(), `scan-${scanType}-report.pdf`);
    } catch (error) {
        statusText.textContent = error.message; statusText.classList.add("error");
    } finally { button.disabled = false; button.textContent = label; }
}
$("export-manual").addEventListener("click", () => { if(lastManual) downloadReport("web",[{url:lastManual.url,...lastManual.data}],{url:lastManual.url}); });
$("export-batch").addEventListener("click", () => downloadReport("database",batchRecords,batchParams));
$("pdf-manual").addEventListener("click", () => { if(lastManual) exportPDF($("pdf-manual"),"web",[{url:lastManual.url,...lastManual.data}],{url:lastManual.url}); });
$("pdf-batch").addEventListener("click", () => exportPDF($("pdf-batch"),"database",batchRecords,batchParams,batchComplete));

form.addEventListener("submit", async event => {
    event.preventDefault();
    const controller = new AbortController(); activeManual = controller;
    const url = input.value.trim(); lastManual = null;
    statusText.textContent = "Analyzing…"; statusText.classList.remove("error");
    resultsSection.hidden = true; $("submit").disabled = true;
    try {
        const response = await fetch("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url}),signal:controller.signal});
        if(!response.ok) throw new Error("This page could not be fetched. No score is available.");
        const data = await response.json(); lastManual = {url,data};
        statusText.textContent = "";
        const a = assessment(data);
        $("source").textContent = url;
        $("manual-score").textContent = scoreLabel(a); setPriority($("manual-level"),a);
        $("manual-explanation").textContent = a.explanation; $("manual-action").textContent = a.action;
        explainFactors($("manual-factors"),a); $("pdf-manual").disabled = !fetched(data);
        resultsSection.hidden = false;
    } catch(error) {
        if(error.name !== "AbortError") {statusText.textContent = error.message; statusText.classList.add("error");}
    } finally { $("submit").disabled = false; if(activeManual === controller) activeManual = null; }
});
function showScreen(screen) {
    if(activeScan) activeScan.abort(); if(activeManual) activeManual.abort();
    for(const item of [homeScreen,manualScreen,databaseScreen]) item.hidden = item !== screen;
    resultsSection.hidden = true; batchSection.hidden = true; statusText.textContent = ""; statusText.classList.remove("error");
    const h = screen.querySelector("h1"); if(h) {h.tabIndex = -1; h.focus();}
}
$("choose-manual").addEventListener("click",()=>showScreen(manualScreen));
$("choose-database").addEventListener("click",()=>{showScreen(databaseScreen);loadMethods();});
for(const button of document.querySelectorAll("[data-home]")) button.addEventListener("click",()=>showScreen(homeScreen));
$("reload-methods").addEventListener("click",loadMethods);
async function loadMethods() {
    const version = ++methodLoad;
    methodSelect.disabled = true; databaseSubmit.disabled = true; $("methods-status").textContent = "Loading cashout methods…";
    try {
        const response = await fetch("/api/cashout-methods",{cache:"no-store"});
        if(!response.ok) throw new Error("Methods unavailable. Check the database connection and reload.");
        const methods = await response.json(); if(version !== methodLoad) return;
        methodSelect.replaceChildren(new Option("Choose a method",""));
        for(const method of methods) methodSelect.append(new Option(method.method ?? "Unnamed method",String(method.id)));
        $("methods-status").textContent = methods.length ? "" : "No cashout methods were found.";
        methodSelect.disabled = !methods.length; databaseSubmit.disabled = !methods.length;
    } catch(error) {
        if(version !== methodLoad) return;
        methodSelect.replaceChildren(new Option("Methods unavailable","")); $("methods-status").textContent = error.message;
    }
}
function renderBatchSummary() {
    const pages = batchRecords.filter(fetched), scored = pages.filter(r=>Number.isFinite(assessment(r).score));
    $("summary-messages").textContent = batchParams.messages ?? "—";
    $("summary-fetched").textContent = pages.length;
    $("summary-flagged").textContent = scored.filter(r=>assessment(r).score >= 50).length;
    $("coverage").textContent = `${pages.length} of ${batchParams.urls ?? batchRecords.length} discovered pages fetched · ${scored.length} scored · ${pages.length-scored.length} with insufficient assessment coverage.`;
}
function appendBatchResult(data) {
    if(!fetched(data)) return;
    const a = assessment(data), article = document.createElement("article"); article.className = "scan-result";
    article.dataset.score = Number.isFinite(a.score) ? a.score : -1;
    const header = document.createElement("div"); header.className = "result-heading";
    const title = document.createElement("h3"); title.textContent = data.url;
    const badge = document.createElement("span"); setPriority(badge,a); header.append(title,badge);
    const score = document.createElement("p"); score.className = "scan-score"; score.textContent = scoreLabel(a);
    const explanation = document.createElement("p"); explanation.className = "explanation"; explanation.textContent = a.explanation;
    const action = document.createElement("p"); action.className = "recommendation"; action.textContent = a.action;
    article.append(header,score,explanation,action);
    if(a.factors?.length) {
        const details = document.createElement("details"), summary = document.createElement("summary"), list = document.createElement("ul");
        summary.textContent = "Why this score?"; explainFactors(list,a); details.append(summary,list); article.append(details);
    }
    const before = [...batchRows.children].find(item=>Number(item.dataset.score) < Number(article.dataset.score));
    batchRows.insertBefore(article,before || null);
}
$("cancel-scan").addEventListener("click",()=>activeScan?.abort());
databaseForm.addEventListener("submit", async event => {
    event.preventDefault(); if(!databaseForm.reportValidity() || activeScan) return;
    const controller = new AbortController(); activeScan = controller;
    batchParams = {cashout_method_id:Number(methodSelect.value),cashout_method:methodSelect.selectedOptions[0].textContent,limit:Number($("limit").value)};
    batchRecords = []; batchComplete = false; batchRows.replaceChildren();
    const controls = [databaseSubmit,$("reload-methods"),methodSelect,$("limit")]; controls.forEach(item=>item.disabled=true);
    $("export-batch").hidden = true; $("pdf-batch").hidden = true; $("batch-empty").hidden = true;
    batchSection.hidden = false; $("cancel-scan").hidden = false; batchProgress.removeAttribute("value");
    $("batch-summary").textContent = "Selecting messages and extracting URLs…"; renderBatchSummary();
    const handleEvent = item => {
        if(item.event === "started") {
            batchParams = {...batchParams,messages:item.messages,urls:item.urls,cashout_method:item.method};
            batchProgress.max = Math.max(item.urls,1); batchProgress.value = 0;
            $("batch-summary").textContent = `${item.method} · ${item.messages} messages selected.`;
        } else if(item.event === "result") {
            batchRecords.push(item.data); appendBatchResult(item.data); batchProgress.value = item.completed;
            $("batch-summary").textContent = `Reviewing ${item.completed} of ${item.urls} discovered pages.`;
        } else if(item.event === "completed") {
            batchComplete = true; batchProgress.value = batchProgress.max;
            $("batch-summary").textContent = `${batchParams.cashout_method} · Scan complete. Fetched pages are listed by review priority.`;
        } else if(item.event === "error") throw new Error("Scan interrupted. Available findings are shown in this partial assessment.");
        renderBatchSummary();
    };
    try {
        const response = await fetch("/api/database-scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(batchParams),signal:controller.signal});
        if(!response.ok) throw new Error("Scan could not start. Check the database connection and try again.");
        const reader = response.body.getReader(), decoder = new TextDecoder(); let pending = "";
        while(true) {
            const {value,done} = await reader.read(); pending += decoder.decode(value,{stream:!done});
            let newline;
            while((newline=pending.indexOf("\n")) !== -1) {
                const line = pending.slice(0,newline).trim(); pending=pending.slice(newline+1);
                if(line) handleEvent(JSON.parse(line));
            }
            if(done) break;
        }
        if(pending.trim()) handleEvent(JSON.parse(pending));
        if(!batchComplete) throw new Error("Scan interrupted. Available findings are shown in this partial assessment.");
    } catch(error) {
        $("batch-summary").textContent = error.name === "AbortError" ? "Scan stopped. Available findings are shown in this partial assessment." : error.message;
    } finally {
        if(activeScan===controller) activeScan=null;
        controls.forEach(item=>item.disabled=false); $("cancel-scan").hidden=true;
        $("export-batch").hidden=!batchRecords.length; $("pdf-batch").hidden=!batchRecords.length && !batchComplete;
        $("batch-empty").hidden=batchRecords.some(fetched); renderBatchSummary();
        if(!batchProgress.hasAttribute("value")) batchProgress.value=0;
    }
});

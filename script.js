const form = document.getElementById("form");
const input = document.getElementById("url");
const submitButton = document.getElementById("submit");
const statusText = document.getElementById("status");
const resultsSection = document.getElementById("results");

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    statusText.textContent = "Analyzing...";
    statusText.classList.remove("error");
    resultsSection.hidden = true;
    submitButton.disabled = true;   // one scan at a time

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: input.value.trim() })
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }
        showResults(await response.json());
    } catch (error) {
        statusText.textContent = error.message;
        statusText.classList.add("error");
    } finally {
        submitButton.disabled = false;
    }
});

function showResults(data) {
    statusText.textContent = data.status === 200
        ? "Page available"
        : "The page answered with HTTP " + data.status + ", so these results may not reflect its real content";

    document.getElementById("source").textContent = data.source;
    document.getElementById("total").textContent = data.total;
    document.getElementById("word-count").textContent = data.results.length;
    document.getElementById("http-status").textContent = data.status;

    const rows = document.getElementById("rows");
    rows.replaceChildren();

    // The crawler sorts by count, so the first result is the largest.
    const topCount = data.results.length > 0 ? data.results[0].count : 0;
    for (const item of data.results) {
        rows.append(createRow(item, topCount));
    }

    if (data.results.length === 0) {
        const tr = document.createElement("tr");
        const empty = document.createElement("td");
        empty.colSpan = 3;
        empty.className = "vacio";
        empty.textContent = "No matches";
        tr.append(empty);
        rows.append(tr);
    }

    resultsSection.hidden = false;
    resultsSection.scrollIntoView({ block: "nearest" });
}

function createRow(item, topCount) {
    const tr = document.createElement("tr");

    const word = document.createElement("td");
    word.className = "senal";
    word.textContent = item.word;   // textContent keeps HTML from running

    const barCell = document.createElement("td");
    barCell.className = "col-barra";
    const bar = document.createElement("div");
    bar.className = "barra";
    bar.style.width = (item.count / topCount) * 100 + "%";
    barCell.append(bar);

    const count = document.createElement("td");
    count.className = "num";
    count.textContent = item.count;

    tr.append(word, barCell, count);
    return tr;
}

// Entry screen and database scanning.
const homeScreen = document.getElementById("home");
const manualScreen = document.getElementById("manual");
const databaseScreen = document.getElementById("database");
const databaseForm = document.getElementById("database-form");
const methodSelect = document.getElementById("method");
const databaseSubmit = document.getElementById("database-submit");
const methodsStatus = document.getElementById("methods-status");
const batchSection = document.getElementById("batch-results");
const batchRows = document.getElementById("batch-rows");
const batchSummary = document.getElementById("batch-summary");
const batchProgress = document.getElementById("batch-progress");
const cancelButton = document.getElementById("cancel-scan");
let activeScan = null;
let methodLoad = 0;

function showScreen(screen) {
    for (const item of [homeScreen, manualScreen, databaseScreen]) item.hidden = item !== screen;
    resultsSection.hidden = true;
    batchSection.hidden = true;
    statusText.textContent = "";
    statusText.classList.remove("error");
    const heading = screen.querySelector("h1");
    if (heading) { heading.tabIndex = -1; heading.focus(); }
}
document.getElementById("choose-manual").addEventListener("click", () => showScreen(manualScreen));
document.getElementById("choose-database").addEventListener("click", () => {
    showScreen(databaseScreen);
    loadMethods();
});
for (const button of document.querySelectorAll("[data-home]")) {
    button.addEventListener("click", () => {
        if (activeScan) activeScan.abort();
        showScreen(homeScreen);
    });
}
document.getElementById("reload-methods").addEventListener("click", loadMethods);

async function loadMethods() {
    const version = ++methodLoad;
    methodSelect.disabled = true;
    databaseSubmit.disabled = true;
    methodsStatus.textContent = "Loading cashout methods…";
    try {
        const response = await fetch("/api/cashout-methods", { cache: "no-store" });
        if (!response.ok) throw new Error(await response.text());
        const methods = await response.json();
        if (version !== methodLoad) return;
        methodSelect.replaceChildren(new Option("Choose a method", ""));
        for (const method of methods) {
            methodSelect.append(new Option(method.method ?? "Unnamed method", String(method.id)));
        }
        methodsStatus.textContent = methods.length ? "" : "No cashout methods were found.";
        methodSelect.disabled = !methods.length;
        databaseSubmit.disabled = !methods.length;
    } catch (error) {
        if (version !== methodLoad) return;
        methodSelect.replaceChildren(new Option("Methods unavailable", ""));
        methodsStatus.textContent = error.message;
    }
}

function appendBatchResult(data) {
    const article = document.createElement("article");
    article.className = "scan-result";
    const title = document.createElement("h3");
    title.textContent = data.url;
    const description = document.createElement("p");
    if (data.error) {
        description.className = "scan-error";
        description.textContent = data.error;
    } else {
        description.textContent = `HTTP ${data.status} · ${data.total} matches · ${data.results.length} signals`;
        if (data.status >= 400) description.textContent += " · HTTP error page; matches may not reflect the intended content.";
    }
    article.append(title, description);
    if (!data.error && data.results.length) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "View matching signals";
        const list = document.createElement("ul");
        for (const result of data.results) {
            const item = document.createElement("li");
            item.textContent = `${result.word}: ${result.count}`;
            list.append(item);
        }
        details.append(summary, list);
        article.append(details);
    }
    batchRows.append(article);
}

cancelButton.addEventListener("click", () => activeScan?.abort());
databaseForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!databaseForm.reportValidity() || activeScan) return;
    const controller = new AbortController();
    activeScan = controller;
    const buttons = [databaseSubmit, document.getElementById("reload-methods")];
    buttons.forEach(button => button.disabled = true);
    methodSelect.disabled = true;
    document.getElementById("limit").disabled = true;
    batchRows.replaceChildren();
    batchSection.hidden = false;
    cancelButton.hidden = false;
    batchProgress.removeAttribute("value");
    batchSummary.textContent = "Selecting messages and extracting URLs…";
    let finished = false;
    let processed = 0;
    const handleEvent = event => {
        if (event.event === "started") {
            batchProgress.max = Math.max(event.urls, 1);
            batchProgress.value = 0;
            batchSummary.textContent = `${event.method}: ${event.messages} messages selected, ${event.urls} unique URLs found.`;
        } else if (event.event === "result") {
            appendBatchResult(event.data);
            processed = event.completed;
            batchProgress.value = processed;
            batchSummary.textContent = `Scanned ${processed} of ${event.urls} URLs.`;
        } else if (event.event === "completed") {
            finished = true;
            batchProgress.value = batchProgress.max;
            batchSummary.textContent = `${event.messages} messages selected · ${event.urls} unique URLs · ${event.fetched} fetched · ${event.failed} failed.`;
            if (!event.urls) batchSummary.textContent += " No URLs to scan for this selection.";
        } else if (event.event === "error") {
            throw new Error(event.error);
        }
    };
    try {
        const response = await fetch("/api/database-scan", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cashout_method_id: Number(methodSelect.value), limit: Number(document.getElementById("limit").value) }),
            signal: controller.signal
        });
        if (!response.ok) throw new Error(await response.text());
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";
        while (true) {
            const { value, done } = await reader.read();
            pending += decoder.decode(value, { stream: !done });
            let newline;
            while ((newline = pending.indexOf("\n")) !== -1) {
                const line = pending.slice(0, newline).trim();
                pending = pending.slice(newline + 1);
                if (line) handleEvent(JSON.parse(line));
            }
            if (done) break;
        }
        if (pending.trim()) handleEvent(JSON.parse(pending));
        if (!finished) throw new Error("Scan ended before completion. Results received so far are shown.");
    } catch (error) {
        if (error.name === "AbortError") batchSummary.textContent = `Scan stopped. ${processed} URL results retained.`;
        else batchSummary.textContent = error.message;
    } finally {
        if (activeScan === controller) activeScan = null;
        buttons.forEach(button => button.disabled = false);
        methodSelect.disabled = false;
        document.getElementById("limit").disabled = false;
        cancelButton.hidden = true;
        if (!batchProgress.hasAttribute("value")) batchProgress.value = 0;
    }
});

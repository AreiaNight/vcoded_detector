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

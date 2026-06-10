const DOCS = {
  guide: {
    title: "재현 가이드",
    path: "./assets/data/README.md",
  },
  dictionary: {
    title: "데이터 사전",
    path: "./assets/data/DATA_DICTIONARY.md",
  },
  summary: {
    title: "분석 요약 원문",
    path: "./assets/data/equal_vote_probability_summary.md",
  },
  qa: {
    title: "사이트 QA 기록",
    path: "./QA_REPORT.md",
  },
};

const params = new URLSearchParams(window.location.search);
const requested = params.get("file") || "guide";
const selectedKey = Object.prototype.hasOwnProperty.call(DOCS, requested) ? requested : "guide";
const selected = DOCS[selectedKey];
const title = document.querySelector("#doc-title");
const body = document.querySelector("#doc-body");
const links = document.querySelectorAll("[data-doc-link]");

links.forEach((link) => {
  link.classList.toggle("is-active", link.dataset.docLink === selectedKey);
});

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderInline(value) {
  let text = escapeHtml(value);
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => {
    const safeHref = String(href).startsWith("http") || String(href).startsWith("./")
      ? escapeHtml(href)
      : "#";
    return `<a href="${safeHref}">${label}</a>`;
  });
  return text;
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function tableCells(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => renderInline(cell.trim()));
}

function renderTable(lines, start) {
  const header = tableCells(lines[start]);
  const rows = [];
  let index = start + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(tableCells(lines[index]));
    index += 1;
  }
  const html = `
    <div class="table-wrap markdown-table">
      <table>
        <thead><tr>${header.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows
            .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return { html, next: index };
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const output = [];
  let index = 0;
  let inCode = false;
  let codeLines = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCode) {
        output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      index += 1;
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      index += 1;
      continue;
    }

    if (!trimmed) {
      closeList();
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1])) {
      closeList();
      const rendered = renderTable(lines, index);
      output.push(rendered.html);
      index = rendered.next;
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        output.push("<ul>");
      }
      output.push(`<li>${renderInline(unordered[1])}</li>`);
      index += 1;
      continue;
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        output.push("<ol>");
      }
      output.push(`<li>${renderInline(ordered[1])}</li>`);
      index += 1;
      continue;
    }

    closeList();
    output.push(`<p>${renderInline(trimmed)}</p>`);
    index += 1;
  }

  closeList();
  if (inCode) {
    output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  return output.join("\n");
}

async function loadDocument() {
  title.textContent = selected.title;
  document.title = `${selected.title} | 후보별 동일득표 분석`;
  try {
    const response = await fetch(selected.path);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const markdown = await response.text();
    body.innerHTML = renderMarkdown(markdown);
  } catch {
    body.innerHTML = "<p>문서를 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>";
  }
}

loadDocument();

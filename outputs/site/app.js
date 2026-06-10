const data = window.SITE_DATA;
const scopeItems = data.scopeItems;
const rows = data.history;
const scopeGrid = document.querySelector("#scope-grid");
const historyBody = document.querySelector("#history-body");
const filters = document.querySelectorAll(".filter");
const regionalBars = document.querySelector("#regional-bars");
const regionalProbabilityBody = document.querySelector("#regional-probability-body");
const regionalPairList = document.querySelector("#regional-pair-list");
const nearMatchBody = document.querySelector("#near-match-body");

scopeGrid.innerHTML = scopeItems
  .map(
    (item) => `
      <article class="scope-item">
        <strong>${item.value}건</strong>
        <b>${item.label}</b>
        <p>${item.text}</p>
        <span class="scope-detail">비교 기회 ${item.denominator.toLocaleString("ko-KR")} 쌍(pair)</span>
      </article>
    `,
  )
  .join("");

if (regionalBars) {
  const maxObserved = Math.max(...data.regionalObserved.regions.map((item) => item.observed));
  regionalBars.innerHTML = data.regionalObserved.regions
    .map((item) => {
      const width = Math.max(12, Math.round((item.observed / maxObserved) * 100));
      return `
        <div class="region-bar" style="--bar: ${width}%">
          <span>${item.region}</span>
          <b>${item.observed}쌍</b>
        </div>
      `;
    })
    .join("");
}

if (regionalProbabilityBody) {
  const thresholds = data.regionalThresholds.thresholds || [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  regionalProbabilityBody.innerHTML = data.regionalThresholds.regions
    .map(
      (item) => `
        <tr>
          <td>${item.region}</td>
          <td>${item.observed.toLocaleString("ko-KR")}쌍</td>
          <td>${item.modelMean.toLocaleString("ko-KR")}</td>
          ${thresholds
            .map((threshold) => {
              const entry = item.thresholdProbabilities[String(threshold)];
              return `<td>${entry ? entry.text : "-"}</td>`;
            })
            .join("")}
          <td>${item.possiblePairs.toLocaleString("ko-KR")}</td>
        </tr>
      `,
    )
    .join("");
}

if (regionalPairList) {
  const groups = data.regionalObserved.pairs.reduce((acc, item) => {
    acc[item.region] ||= [];
    acc[item.region].push(item);
    return acc;
  }, {});
  regionalPairList.innerHTML = Object.entries(groups)
    .map(
      ([region, pairs]) => `
        <details>
          <summary>${region} ${pairs.length}쌍 상세</summary>
          <div class="pair-detail-list">
            ${pairs
              .map(
                (pair) => `
                  <p>
                    <b>${pair.candidate1.toLocaleString("ko-KR")} / ${pair.candidate2.toLocaleString("ko-KR")}</b>
                    <span>${pair.place1}</span>
                    <span>${pair.place2}</span>
                  </p>
                `,
              )
              .join("")}
          </div>
        </details>
      `,
    )
    .join("");
}

if (nearMatchBody) {
  nearMatchBody.innerHTML = data.nearMatch.items
    .map(
      (item) => `
        <tr>
          <td>${item.delta}</td>
          <td>${item.observed.toLocaleString("ko-KR")}</td>
          <td>${item.mean.toLocaleString("ko-KR")}</td>
          <td>${item.ci}</td>
        </tr>
      `,
    )
    .join("");
}

function renderRows(predicate = () => true) {
  const metricCell = (row, key) => `
    <td>
      <span class="cell-main">${row[key].toLocaleString("ko-KR")}</span>
    </td>
  `;

  historyBody.innerHTML = rows
    .filter(({ dataset }) => predicate(dataset))
    .map((row) => {
      const focus = row.dataset === data.focusDataset;
      return `
        <tr data-focus="${focus}">
          <td>${row.dataset}</td>
          <td>${row.rows.toLocaleString("ko-KR")}</td>
          ${metricCell(row, "stem")}
          ${metricCell(row, "sameSigungu")}
          ${metricCell(row, "gwangjuJeonnam")}
          ${metricCell(row, "national")}
        </tr>
      `;
    })
    .join("");
}

filters.forEach((button) => {
  button.addEventListener("click", () => {
    filters.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");

    if (button.dataset.kind === "all") {
      renderRows();
      return;
    }

    if (button.dataset.kind) {
      renderRows((dataset) => dataset.startsWith(button.dataset.kind));
      return;
    }

    renderRows((dataset) => dataset.includes(button.dataset.vote));
  });
});

renderRows();

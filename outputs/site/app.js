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
const jointSummary = document.querySelector("#joint-summary");
const jointProbabilityBody = document.querySelector("#joint-probability-body");

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

if (jointSummary && data.jointProbabilities?.models?.length) {
  const base = data.jointProbabilities.models.find((item) => item.label.includes("w=0.7"));
  const first = data.jointProbabilities.models[0];
  const focus = base || first;
  const minInverse = data.jointProbabilities.models
    .map((item) => item.pAB)
    .filter(Boolean)
    .sort((a, b) => b - a)[0];
  const maxInverse = data.jointProbabilities.models
    .map((item) => item.pAB)
    .filter(Boolean)
    .sort((a, b) => a - b)[0];
  const inverseText = (value) => (value ? `1 / ${Math.round(1 / value).toLocaleString("ko-KR")}` : "-");
  jointSummary.innerHTML = `
    <span class="metric-label">결합확률 P(A∩B)</span>
    <strong>약 ${inverseText(minInverse)} ~ ${inverseText(maxInverse)}</strong>
    <p>
      200,000회 정밀화 기준 모델별 범위다. 기본 해석은 더 보수적인
      <b>${focus.label}</b>의 <b>${focus.pABInverseText}</b>을 중심에 둔다.
    </p>
  `;
}

if (jointProbabilityBody && data.jointProbabilities?.models?.length) {
  jointProbabilityBody.innerHTML = data.jointProbabilities.models
    .map(
      (item) => `
        <tr>
          <td>${item.label}</td>
          <td>${item.pAText}</td>
          <td>${item.pBText}</td>
          <td><b>${item.pABText}</b><br><span class="subtle">${item.pABInverseText}</span></td>
          <td>${item.pBGivenAText}</td>
          <td>${item.iterations.toLocaleString("ko-KR")}회</td>
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

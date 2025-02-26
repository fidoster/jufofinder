document.addEventListener("DOMContentLoaded", function () {
  let source = null;

  const searchForm = document.getElementById("searchForm");
  if (searchForm) {
    searchForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const formData = new FormData(this);
      const keywords = formData.get("keywords");
      const maxArticles = parseInt(formData.get("max_articles")) || 1000;
      const targetJufo = formData.get("target_jufo")
        ? parseInt(formData.get("target_jufo"))
        : null;
      let yearRange = formData.get("year_range");
      if (yearRange === "custom") {
        const yearStart = formData.get("year_start");
        const yearEnd = formData.get("year_end");
        yearRange = yearStart && yearEnd ? `${yearStart}-${yearEnd}` : "all";
      }
      const progressBar = document.getElementById("progress-bar");
      const progressText = document.getElementById("progress-text");
      const jufoCountText = document.getElementById("jufo-count");
      const tbody = document.querySelector("#resultsTable tbody");
      const downloadBtn = document.getElementById("downloadBtn");
      const stopBtn = document.getElementById("stopBtn");
      const searchBtn = document.getElementById("searchBtn");
      const keywordArray = keywords
        .split(",")
        .map((k) => k.trim().toLowerCase());

      progressBar.style.width = "0%";
      progressText.textContent = "Starting search...";
      jufoCountText.textContent = "JUFO 2/3: 0";
      tbody.innerHTML = "";
      downloadBtn.style.display = "none";
      stopBtn.style.display = "inline-block";
      searchBtn.style.display = "none";

      source = new EventSource(
        `/search_stream?keywords=${encodeURIComponent(
          keywords
        )}&max_articles=${maxArticles}&target_jufo=${
          targetJufo || ""
        }&year_range=${encodeURIComponent(yearRange)}`
      );

      source.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.status === "Checking") {
          progressBar.style.width = `${data.progress}%`;
          progressText.textContent = `Processing ${data.current} of ${data.total} articles`;
          jufoCountText.textContent = `JUFO 2/3: ${data.jufo_count}`;
          populateTable(data.results, keywordArray);
        } else if (data.status === "Complete" || data.status === "Stopped") {
          progressBar.style.width = "100%";
          progressText.textContent = `${
            data.status === "Stopped" ? "Stopped" : "Completed"
          } - ${data.current} articles processed`;
          jufoCountText.textContent = `JUFO 2/3: ${data.jufo_count}`;
          populateTable(data.results, keywordArray);
          downloadBtn.style.display = "block";
          stopBtn.style.display = "none";
          searchBtn.style.display = "inline-block";
          source.close();
          source = null;
        }
      };

      source.onerror = function () {
        progressText.textContent = "Error occurred during search.";
        stopBtn.style.display = "none";
        searchBtn.style.display = "inline-block";
        source.close();
        source = null;
      };
    });

    document.getElementById("stopBtn").addEventListener("click", function () {
      if (source) {
        fetch("/stop_search", { method: "POST" })
          .then((response) => response.json())
          .then((data) => {
            if (data.status === "stopped") {
              console.log("Search stopped");
            }
          })
          .catch((error) => console.error("Error stopping search:", error));
      }
    });

    document
      .getElementById("yearRange")
      .addEventListener("change", function () {
        const customYearRange = document.getElementById("customYearRange");
        customYearRange.style.display =
          this.value === "custom" ? "inline-block" : "none";
      });

    document
      .getElementById("jufoFilter")
      .addEventListener("change", applyFilter);
  }

  function populateTable(results, keywords) {
    const tbody = document.querySelector("#resultsTable tbody");
    const isHistoryPage = !!document.getElementById("deleteNotJufoBtn");
    tbody.innerHTML = "";
    results.forEach((result) => {
      const highlightedTitle = highlightKeywords(result.title, keywords);
      const highlightedJournal = highlightKeywords(result.journal, keywords);
      const row = document.createElement("tr");
      row.innerHTML = `
                <td>${highlightedTitle}</td>
                <td>${highlightedJournal}</td>
                <td>${result.year}</td>
                <td>${result.level}</td>
                <td>${
                  result.link !== "No link available"
                    ? `<a href="${result.link}" target="_blank" class="article-btn">Article</a>`
                    : "<span>No Link</span>"
                }</td>
                ${
                  isHistoryPage
                    ? `<td><button class="delete-btn delete-article-btn" data-keywords="${keywords}" data-link="${result.link}">Delete</button></td>`
                    : ""
                }
            `;
      tbody.appendChild(row);
    });
    applyFilter();
    attachDeleteListeners();
  }

  function attachDeleteListeners() {
    document.querySelectorAll(".delete-article-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const keywords = btn.getAttribute("data-keywords");
        const link = btn.getAttribute("data-link");
        fetch(
          `/delete_article/${encodeURIComponent(keywords)}/${encodeURIComponent(
            link
          )}`,
          { method: "POST" }
        )
          .then((response) => response.json())
          .then((data) => {
            console.log("Delete response:", data);
            if (data.status === "success") {
              btn.closest("tr").remove();
              updateHistoryCount(keywords, data.remaining_count);
            } else {
              console.error("Delete failed:", data.status);
            }
          })
          .catch((error) => console.error("Error deleting article:", error));
      });
    });

    const deleteNotJufoBtn = document.getElementById("deleteNotJufoBtn");
    if (deleteNotJufoBtn) {
      deleteNotJufoBtn.addEventListener("click", (e) => {
        e.preventDefault();
        const keywords = document
          .querySelector("h2")
          .textContent.replace("Results for ", "")
          .replace(/"/g, "");
        fetch(`/delete_not_jufo/${encodeURIComponent(keywords)}`, {
          method: "POST",
        })
          .then((response) => response.json())
          .then((data) => {
            console.log("Delete not JUFO response:", data);
            if (data.status === "success") {
              document
                .querySelectorAll("#resultsTable tbody tr")
                .forEach((row) => {
                  if (row.children[3].textContent === "Not JUFO Ranked") {
                    row.remove();
                  }
                });
              updateHistoryCount(keywords, data.remaining_count);
            } else {
              console.error("Delete not JUFO failed:", data.status);
            }
          })
          .catch((error) =>
            console.error("Error deleting not JUFO articles:", error)
          );
      });
    }
  }

  function highlightKeywords(text, keywords) {
    let highlighted = text;
    keywords.forEach((keyword) => {
      const regex = new RegExp(`(${keyword})`, "gi");
      highlighted = highlighted.replace(
        regex,
        '<span class="highlight">$1</span>'
      );
    });
    return highlighted;
  }

  document.querySelectorAll(".sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const table = th.closest("table");
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const index = Array.from(th.parentNode.children).indexOf(th);
      const isAsc = th.classList.contains("sort-asc");

      document.querySelectorAll(".sortable").forEach((h) => {
        h.classList.remove("sort-asc", "sort-desc");
      });
      th.classList.add(isAsc ? "sort-desc" : "sort-asc");

      rows.sort((a, b) => {
        let aValue = a.children[index].textContent;
        let bValue = b.children[index].textContent;
        if (index === 3) {
          // JUFO Level
          aValue = aValue === "Not JUFO Ranked" ? -1 : parseInt(aValue) || 0;
          bValue = bValue === "Not JUFO Ranked" ? -1 : parseInt(bValue) || 0;
          return isAsc ? bValue - aValue : aValue - bValue;
        } else if (index === 2) {
          // Year
          aValue = aValue === "N/A" ? -1 : parseInt(aValue) || 0;
          bValue = bValue === "N/A" ? -1 : parseInt(bValue) || 0;
          return isAsc ? bValue - aValue : aValue - bValue;
        }
        return isAsc
          ? bValue.localeCompare(aValue)
          : aValue.localeCompare(bValue);
      });

      tbody.innerHTML = "";
      rows.forEach((row) => tbody.appendChild(row));
      attachDeleteListeners(); // Re-attach listeners after sorting
    });
  });

  function applyFilter() {
    const filterValue = document.getElementById("jufoFilter").value;
    const rows = document.querySelectorAll("#resultsTable tbody tr");
    rows.forEach((row) => {
      const level = row.children[3].textContent;
      let show = true;
      switch (filterValue) {
        case "2_3":
          show = level === "2" || level === "3";
          break;
        case "3":
          show = level === "3";
          break;
        case "2":
          show = level === "2";
          break;
        case "1":
          show = level === "1";
          break;
        case "0":
          show = level === "0";
          break;
        case "not_ranked":
          show = level === "Not JUFO Ranked";
          break;
        case "all":
        default:
          show = true;
      }
      row.style.display = show ? "" : "none";
    });
    attachDeleteListeners(); // Re-attach listeners after filtering
  }

  function updateHistoryCount(keywords, newCount) {
    console.log(`Updated count for "${keywords}": ${newCount}`);
  }

  // Initial attachment of delete listeners
  attachDeleteListeners();
});

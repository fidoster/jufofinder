document.addEventListener("DOMContentLoaded", function () {
  let source = null;

  const searchForm = document.getElementById("searchForm");
  if (searchForm) {
    searchForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const formData = new FormData(this);
      const keywords = formData.get("keywords") || "";
      const maxArticles = parseInt(formData.get("max_articles")) || 1000;

      // Handle advanced search field:
      let targetJufoValue = formData.get("target_jufo");
      if (targetJufoValue === "custom") {
        targetJufoValue = parseInt(formData.get("custom_target_jufo")) || null;
      } else {
        targetJufoValue = targetJufoValue ? parseInt(targetJufoValue) : null;
      }

      let yearRange = formData.get("year_range") || "all";
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
        .map((k) => k.trim().toLowerCase())
        .filter((k) => k);

      if (!keywords) {
        alert("Please enter keywords to start the search.");
        return;
      }

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
          targetJufoValue || ""
        }&year_range=${encodeURIComponent(yearRange)}`
      );

      source.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.status === "Checking") {
          progressBar.style.width = `${data.progress}%`;
          progressText.textContent = `Processing ${data.current} of ${data.total} articles`;
          jufoCountText.textContent = `JUFO 2/3: ${data.jufo_count}`;
          populateTable(data.results, keywordArray);
        } else if (data.status === "Stopping") {
          progressText.textContent = "Stopping search and saving results...";
        } else if (data.status === "Complete" || data.status === "Stopped") {
          progressBar.style.width = "100%";
          progressText.textContent = `${
            data.status === "Stopped"
              ? "Search stopped manually"
              : "Search completed"
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
        if (source) {
          source.close();
          source = null;
        }
        console.error("EventSource error occurred");
      };
    });

    document.getElementById("stopBtn").addEventListener("click", function () {
      if (source) {
        const keywords =
          document.querySelector("input[name='keywords']").value || "default";
        console.log("Requesting search stop for keywords:", keywords);
        fetch(`/stop_search?keywords=${encodeURIComponent(keywords)}`, {
          method: "POST",
        })
          .then((response) => {
            if (!response.ok) throw new Error("Network response was not ok");
            return response.json();
          })
          .then((data) => {
            if (data.status === "stopped") {
              console.log("Stop requested, waiting for server confirmation");
              const timeoutId = setTimeout(() => {
                if (source) {
                  console.warn(
                    "Server response delayed or failed, forcing stop"
                  );
                  progressText.textContent =
                    "Search stopped manually (timeout)";
                  progressBar.style.width = "100%";
                  downloadBtn.style.display = "block";
                  stopBtn.style.display = "none";
                  searchBtn.style.display = "inline-block";
                  source.close();
                  source = null;
                }
              }, 10000); // 10-second timeout

              const checkStop = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === "Stopped") {
                  clearTimeout(timeoutId);
                  console.log("Server confirmed stop");
                  if (source) {
                    source.removeEventListener("message", checkStop);
                    source.close();
                    source = null;
                  }
                }
              };
              source.addEventListener("message", checkStop);
            }
          })
          .catch((error) => {
            console.error("Error stopping search:", error);
            alert("Failed to stop search due to an error. Please try again.");
            if (source) {
              source.close();
              source = null;
            }
          });
      }
    });

    document
      .getElementById("yearRange")
      .addEventListener("change", function () {
        const customYearRange = document.getElementById("customYearRange");
        customYearRange.style.display =
          this.value === "custom" ? "block" : "none";
      });

    // Handle showing/hiding the custom advanced search field
    document
      .getElementById("targetJufo")
      .addEventListener("change", function () {
        const customInput = document.getElementById("customTargetJufo");
        if (this.value === "custom") {
          customInput.style.display = "block";
        } else {
          customInput.style.display = "none";
        }
      });

    document
      .getElementById("jufoFilter")
      .addEventListener("change", applyFilter);
  }

  function populateTable(results, keywords) {
    const tbody = document.querySelector("#resultsTable tbody");
    const isHistoryPage = document.getElementById("deleteNotJufoBtn") !== null;
    const currentKeywords = isHistoryPage
      ? document
          .querySelector("h2.centered-title")
          .getAttribute("data-keywords")
      : keywords && Array.isArray(keywords)
      ? keywords.join(",")
      : "";

    tbody.innerHTML = "";
    if (results && Array.isArray(results)) {
      results.forEach((result) => {
        if (result) {
          const highlightedTitle = highlightKeywords(
            result.title || "",
            keywords || []
          );
          const highlightedJournal = highlightKeywords(
            result.journal || "",
            keywords || []
          );
          const row = document.createElement("tr");
          row.innerHTML = `
            <td>${highlightedTitle}</td>
            <td>${highlightedJournal}</td>
            <td>${result.year || "N/A"}</td>
            <td>${result.level || "N/A"}</td>
            <td>${
              result.link && result.link !== "No link available"
                ? `<a href="${result.link}" target="_blank" class="btn btn-sm btn-primary">Article</a>`
                : "<span>No Link</span>"
            }</td>
            ${
              isHistoryPage
                ? `<td><button class="btn btn-sm btn-danger delete-article-btn" data-keywords="${currentKeywords}" data-link="${
                    result.link || ""
                  }">Delete</button></td>`
                : ""
            }
          `;
          tbody.appendChild(row);
        }
      });
    }
    applyFilter();
    attachDeleteListeners();
  }

  function attachDeleteListeners() {
    document.querySelectorAll(".delete-article-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const keywords = btn.getAttribute("data-keywords") || "";
        const link = btn.getAttribute("data-link") || "";

        console.log(`Deleting article: ${link} from search: ${keywords}`);

        fetch(
          `/delete_article/${encodeURIComponent(keywords)}/${encodeURIComponent(
            link
          )}`,
          { method: "POST" }
        )
          .then((response) => {
            if (!response.ok) throw new Error("Network response was not ok");
            return response.json();
          })
          .then((data) => {
            console.log("Delete response:", data);
            if (data.status === "success") {
              btn.closest("tr").remove();
              updateHistoryCount(keywords, data.remaining_count);
            } else {
              console.error("Delete failed:", data.status);
              alert("Failed to delete the article. Please try again.");
            }
          })
          .catch((error) => {
            console.error("Error deleting article:", error);
            alert("Error occurred while deleting the article.");
          });
      });
    });

    const deleteNotJufoBtn = document.getElementById("deleteNotJufoBtn");
    if (deleteNotJufoBtn) {
      deleteNotJufoBtn.addEventListener("click", (e) => {
        e.preventDefault();
        const keywords =
          document
            .querySelector("h2.centered-title")
            ?.getAttribute("data-keywords") || "";

        if (!keywords) {
          console.error("No keywords found for delete not JUFO operation");
          alert("Could not determine search keywords. Operation aborted.");
          return;
        }

        console.log(`Deleting non-JUFO articles for: ${keywords}`);

        fetch(`/delete_not_jufo/${encodeURIComponent(keywords)}`, {
          method: "POST",
        })
          .then((response) => {
            if (!response.ok) throw new Error("Network response was not ok");
            return response.json();
          })
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
              alert(
                `Non-JUFO ranked articles have been removed. Remaining articles: ${data.remaining_count}`
              );
            } else {
              console.error("Delete not JUFO failed:", data.status);
              alert("Failed to delete non-JUFO articles. Please try again.");
            }
          })
          .catch((error) => {
            console.error("Error deleting not JUFO articles:", error);
            alert("Error occurred while deleting non-JUFO articles.");
          });
      });
    }

    // Add delete listener for history page delete buttons
    document.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const keywords = btn.getAttribute("data-keywords") || "";

        console.log(`Deleting search: ${keywords}`);

        fetch(`/delete_search/${encodeURIComponent(keywords)}`, {
          method: "POST",
        })
          .then((response) => {
            if (!response.ok) throw new Error("Network response was not ok");
            return response.json();
          })
          .then((data) => {
            console.log("Delete search response:", data);
            if (data.status === "success") {
              btn.closest("tr").remove();
            } else {
              console.error("Delete search failed:", data.status);
              alert("Failed to delete the search. Please try again.");
            }
          })
          .catch((error) => {
            console.error("Error deleting search:", error);
            alert("Error occurred while deleting the search.");
          });
      });
    });
  }

  function highlightKeywords(text, keywords) {
    if (!text || !Array.isArray(keywords) || keywords.length === 0)
      return text || "";

    let highlighted = text;
    keywords.forEach((keyword) => {
      if (keyword && keyword.trim()) {
        const regex = new RegExp(`(${keyword.trim()})`, "gi");
        highlighted = highlighted.replace(
          regex,
          '<span class="highlight">$1</span>'
        );
      }
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
        let aValue = a.children[index].textContent.trim();
        let bValue = b.children[index].textContent.trim();
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
      attachDeleteListeners();
    });
  });

  function applyFilter() {
    const filterSelect = document.getElementById("jufoFilter");
    if (!filterSelect) return;

    const filterValue = filterSelect.value;
    const rows = document.querySelectorAll("#resultsTable tbody tr");
    rows.forEach((row) => {
      const level = row.children[3].textContent.trim();
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
  }

  function updateHistoryCount(keywords, newCount) {
    console.log(`Updated count for "${keywords}": ${newCount}`);
    const countElement = document.querySelector(
      `[data-keywords="${keywords}"] .count`
    );
    if (countElement) {
      countElement.textContent = newCount;
    } else {
      console.warn(`No count element found for keywords: ${keywords}`);
    }
  }

  // Call initially to set up listeners for any buttons already on the page
  attachDeleteListeners();

  // Apply filter on page load
  if (document.getElementById("jufoFilter")) {
    applyFilter();
  }
});

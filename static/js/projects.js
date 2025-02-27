document.addEventListener("DOMContentLoaded", function () {
  console.log("Projects JS loaded.");

  // Make every card header clickable to toggle its collapse content.
  const cardHeaders = document.querySelectorAll(".card-header");
  cardHeaders.forEach(function (header) {
    header.addEventListener("click", function (e) {
      // Do not toggle if the click is on a button or within a form.
      if (
        e.target.tagName.toLowerCase() === "button" ||
        e.target.closest("form")
      ) {
        return;
      }
      const collapseDiv = header.nextElementSibling;
      if (collapseDiv && collapseDiv.classList.contains("collapse")) {
        let collapseInstance = bootstrap.Collapse.getInstance(collapseDiv);
        if (!collapseInstance) {
          collapseInstance = new bootstrap.Collapse(collapseDiv, {
            toggle: false,
          });
        }
        collapseInstance.toggle();
      }
    });
  });
});

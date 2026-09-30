(() => {
  const opener = document.querySelector("#open-receipt-export");
  const dialog = document.querySelector("#receipt-export-dialog");
  if (!opener || !dialog) return;

  const grid = dialog.querySelector("[data-export-grid]");
  const feedback = dialog.querySelector("[data-export-feedback]");
  const loading = dialog.querySelector("[data-export-loading]");
  const error = dialog.querySelector("[data-export-error]");
  const content = dialog.querySelector("[data-export-content]");
  const empty = dialog.querySelector("[data-export-empty]");
  const copySelectionButton = dialog.querySelector("[data-copy-selection]");
  const copyHeadersButton = dialog.querySelector("[data-copy-all-headers]");
  const copyAllButton = dialog.querySelector("[data-copy-all]");
  const download = dialog.querySelector("[data-export-download]");

  let matrix = [];
  let anchor = { row: 0, column: 0 };
  let active = { row: 0, column: 0 };
  let dragging = false;

  const bounds = () => ({
    firstRow: Math.min(anchor.row, active.row),
    lastRow: Math.max(anchor.row, active.row),
    firstColumn: Math.min(anchor.column, active.column),
    lastColumn: Math.max(anchor.column, active.column),
  });

  const cellAt = (row, column) =>
    grid.querySelector(`[data-row="${row}"][data-column="${column}"]`);

  function updateSelection() {
    const selected = bounds();
    grid.querySelectorAll("[data-row]").forEach((cell) => {
      const row = Number(cell.dataset.row);
      const column = Number(cell.dataset.column);
      const isSelected = row >= selected.firstRow && row <= selected.lastRow
        && column >= selected.firstColumn && column <= selected.lastColumn;
      cell.classList.toggle("is-selected", isSelected);
      cell.classList.toggle("is-active", row === active.row && column === active.column);
      cell.setAttribute("aria-selected", String(isSelected));
    });
    const rows = selected.lastRow - selected.firstRow + 1;
    const columns = selected.lastColumn - selected.firstColumn + 1;
    feedback.textContent = `Selección: ${rows} fila${rows === 1 ? "" : "s"} × ${columns} columna${columns === 1 ? "" : "s"}.`;
  }

  function setActive(row, column, extend = false, scroll = true) {
    const lastRow = Math.max(0, matrix.length - 1);
    const lastColumn = Math.max(0, (matrix[0]?.length || 1) - 1);
    active = {
      row: Math.max(0, Math.min(row, lastRow)),
      column: Math.max(0, Math.min(column, lastColumn)),
    };
    if (!extend) anchor = { ...active };
    updateSelection();
    if (scroll) {
      cellAt(active.row, active.column)?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  function safeSpreadsheetText(value) {
    const normalized = String(value ?? "").replace(/[\t\r\n]+/g, " ");
    return /^\s*[=+\-@]/.test(normalized) ? `'${normalized}` : normalized;
  }

  function selectedMatrix() {
    const selected = bounds();
    return matrix
      .slice(selected.firstRow, selected.lastRow + 1)
      .map((row) => row.slice(selected.firstColumn, selected.lastColumn + 1));
  }

  function serializeTsv(rows) {
    return rows.map((row) => row.map(safeSpreadsheetText).join("\t")).join("\n");
  }

  function serializeHtml(rows) {
    const table = document.createElement("table");
    rows.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      row.forEach((value) => {
        const cell = document.createElement(rowIndex === 0 ? "th" : "td");
        cell.textContent = safeSpreadsheetText(value);
        tr.append(cell);
      });
      table.append(tr);
    });
    return table.outerHTML;
  }

  async function writeClipboard(rows, successMessage) {
    if (!rows.length || !rows[0]?.length) return;
    const text = serializeTsv(rows);
    try {
      if (navigator.clipboard?.write && window.ClipboardItem) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/plain": new Blob([text], { type: "text/plain" }),
            "text/html": new Blob([serializeHtml(rows)], { type: "text/html" }),
          }),
        ]);
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        throw new Error("Clipboard API unavailable");
      }
      feedback.textContent = successMessage;
    } catch (_clipboardError) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.className = "clipboard-fallback";
      document.body.append(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      feedback.textContent = copied
        ? `${successMessage} Se usó el modo compatible del navegador.`
        : "El navegador bloqueó el portapapeles. Selecciona la grilla y usa Ctrl+C o Cmd+C.";
    }
  }

  function renderGrid(headers, rows) {
    grid.replaceChildren();
    matrix = [headers, ...rows];
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    headers.forEach((header, column) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = header;
      cell.dataset.row = "0";
      cell.dataset.column = String(column);
      cell.setAttribute("role", "columnheader");
      headRow.append(cell);
    });
    head.append(headRow);
    grid.append(head);

    const body = document.createElement("tbody");
    rows.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      row.forEach((value, column) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        cell.dataset.row = String(rowIndex + 1);
        cell.dataset.column = String(column);
        cell.setAttribute("role", "gridcell");
        if (column >= 8) cell.classList.add("amount");
        tr.append(cell);
      });
      body.append(tr);
    });
    grid.append(body);
    setActive(rows.length ? 1 : 0, 0, false, false);
  }

  async function loadExport() {
    loading.hidden = false;
    error.hidden = true;
    content.hidden = true;
    try {
      const response = await fetch(opener.dataset.previewUrl, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      dialog.querySelector("[data-export-organization]").textContent = data.organization;
      dialog.querySelector("[data-export-period]").textContent = data.period;
      dialog.querySelector("[data-export-filter]").textContent = data.filter_label;
      dialog.querySelector("[data-export-count]").textContent = String(data.count);
      dialog.querySelector("[data-export-scope]").textContent = data.scope_note;
      const excluded = dialog.querySelector("[data-export-excluded]");
      excluded.hidden = data.excluded_count === 0;
      excluded.textContent = `${data.excluded_count} documento${data.excluded_count === 1 ? "" : "s"} del período no se incluye${data.excluded_count === 1 ? "" : "n"} por no estar aceptado${data.excluded_count === 1 ? "" : "s"}.`;
      download.href = opener.dataset.downloadUrl;
      renderGrid(data.headers, data.rows);
      const hasRows = data.rows.length > 0;
      grid.parentElement.hidden = !hasRows;
      empty.hidden = hasRows;
      copySelectionButton.disabled = !hasRows;
      copyHeadersButton.disabled = !hasRows;
      copyAllButton.disabled = !hasRows;
      download.setAttribute("aria-disabled", String(!hasRows));
      download.classList.toggle("is-disabled", !hasRows);
      content.hidden = false;
    } catch (_requestError) {
      error.textContent = "No fue posible preparar la exportación. Cierra el modal e inténtalo nuevamente.";
      error.hidden = false;
    } finally {
      loading.hidden = true;
    }
  }

  opener.addEventListener("click", () => {
    dialog.showModal();
    loadExport();
  });
  dialog.querySelectorAll("[data-export-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  dialog.addEventListener("close", () => opener.focus());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  grid.addEventListener("mousedown", (event) => {
    const cell = event.target.closest("[data-row]");
    if (!cell) return;
    event.preventDefault();
    dragging = true;
    setActive(Number(cell.dataset.row), Number(cell.dataset.column), event.shiftKey);
    grid.focus();
  });
  grid.addEventListener("mouseover", (event) => {
    const cell = event.target.closest("[data-row]");
    if (!dragging || !cell) return;
    setActive(Number(cell.dataset.row), Number(cell.dataset.column), true);
  });
  document.addEventListener("mouseup", () => { dragging = false; });
  grid.addEventListener("keydown", (event) => {
    const movement = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    }[event.key];
    if (movement) {
      event.preventDefault();
      setActive(active.row + movement[0], active.column + movement[1], event.shiftKey);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
      event.preventDefault();
      writeClipboard(selectedMatrix(), "Selección copiada.");
    }
  });

  copySelectionButton.addEventListener("click", () =>
    writeClipboard(selectedMatrix(), "Selección copiada."));
  copyHeadersButton.addEventListener("click", () =>
    writeClipboard(matrix, "Tabla completa con encabezados copiada."));
  copyAllButton.addEventListener("click", () =>
    writeClipboard(matrix.slice(1), "Tabla completa sin encabezados copiada."));
  download.addEventListener("click", (event) => {
    if (download.getAttribute("aria-disabled") === "true") event.preventDefault();
  });
})();

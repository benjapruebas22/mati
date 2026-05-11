(function () {
  const boot = window.__ALBUM_MUNDIAL__;
  if (!boot || !Array.isArray(boot.paises)) return;

  const paises = boot.paises;
  const endpoints = boot.endpoints || {};
  const elCountries = document.getElementById("amCountries");

  const stateLabel = { 0: "Falta", 1: "Tiene", 2: "Repetida" };

  const byId = new Map();
  paises.forEach((p) => byId.set(Number(p.id), p));

  const elById = new Map();
  document.querySelectorAll(".am-country").forEach((el) => {
    elById.set(Number(el.dataset.paisId), el);
  });

  const elTotal = document.getElementById("amTotal");
  const elTiene = document.getElementById("amTiene");
  const elFaltan = document.getElementById("amFaltan");
  const elRep = document.getElementById("amRepetidas");
  const elPct = document.getElementById("amPct");
  const elComp = document.getElementById("amCompletos");
  const elProgressFill = document.getElementById("amProgressFill");
  const elProgressText = document.getElementById("amProgressText");
  const elProgressPct = document.getElementById("amProgressPct");

  const elSearch = document.getElementById("amSearch");
  const elView = document.getElementById("amView");
  const elSort = document.getElementById("amSort");
  const elReset = document.getElementById("amReset");

  const elCopyMissing = document.getElementById("amCopyMissing");
  const elCopyDup = document.getElementById("amCopyDup");

  const elImportText = document.getElementById("amImportText");
  const elImportApply = document.getElementById("amImportApply");
  const elImportClear = document.getElementById("amImportClear");
  const elImportResult = document.getElementById("amImportResult");

  const elExportBackup = document.getElementById("amExportBackup");
  const elImportBackupFile = document.getElementById("amImportBackupFile");
  const elResetAlbum = document.getElementById("amResetAlbum");
  const elBackupResult = document.getElementById("amBackupResult");

  const elSide = document.getElementById("amSide");
  const elSideClose = document.getElementById("amSideClose");
  const elSideDone = document.getElementById("amSideDone");
  const elSideTitle = document.getElementById("amSideTitle");
  const elSideCode = document.getElementById("amSideCode");
  const elSideSub = document.getElementById("amSideSub");
  const elSideTiene = document.getElementById("amSideTiene");
  const elSideFaltan = document.getElementById("amSideFaltan");
  const elSideRep = document.getElementById("amSideRep");
  const elSideTableBody = document.querySelector("#amSideTable tbody");

  function round1(n) {
    return Math.round(n * 10) / 10;
  }

  function recalcPais(p) {
    let tiene = 0;
    let faltan = 0;
    let rep = 0;
    (p.figuritas || []).forEach((f) => {
      const st = Number(f.estado || 0);
      if (st === 0) faltan += 1;
      else if (st === 1) tiene += 1;
      else rep += 1;
    });
    p.tiene = tiene;
    p.faltan = faltan;
    p.repetidas = rep;
    p.pct = round1(((tiene + rep) / 20) * 100);
    p.completo = faltan === 0;
  }

  function recalcTotals() {
    let total = 0;
    let tiene = 0;
    let rep = 0;
    let faltan = 0;
    let completos = 0;
    paises.forEach((p) => {
      total += 20;
      tiene += Number(p.tiene || 0);
      rep += Number(p.repetidas || 0);
      faltan += Number(p.faltan || 0);
      completos += p.faltan === 0 ? 1 : 0;
    });
    const pct = round1(((tiene + rep) / Math.max(total, 1)) * 100);
    return { total, tiene, rep, faltan, completos, pct };
  }

  function updateTotalsUI(t) {
    if (!t) return;
    if (elTotal) elTotal.textContent = String(t.total);
    if (elTiene) elTiene.textContent = String(t.tiene);
    if (elFaltan) elFaltan.textContent = String(t.faltan);
    if (elRep) elRep.textContent = String(t.rep);
    if (elComp) elComp.textContent = String(t.completos);
    if (elPct) elPct.textContent = `${t.pct}%`;
    if (elProgressFill) elProgressFill.style.width = `${t.pct}%`;
    if (elProgressText) elProgressText.textContent = `${t.tiene + t.rep} / ${t.total}`;
    if (elProgressPct) elProgressPct.textContent = `${t.pct}%`;
  }

  function updatePaisUI(pId) {
    const p = byId.get(pId);
    const el = elById.get(pId);
    if (!p || !el) return;

    const elTieneLocal = el.querySelector('[data-role="tiene"]');
    const elFaltanLocal = el.querySelector('[data-role="faltan"]');
    const elRepLocal = el.querySelector('[data-role="rep"]');
    const elPctLocal = el.querySelector('[data-role="pct"]');
    const elPctFill = el.querySelector('[data-role="pct-fill"]');

    if (elTieneLocal) elTieneLocal.textContent = String(p.tiene);
    if (elFaltanLocal) elFaltanLocal.textContent = String(p.faltan);
    if (elRepLocal) elRepLocal.textContent = String(p.repetidas);
    if (elPctLocal) elPctLocal.textContent = String(p.pct);
    if (elPctFill) elPctFill.style.width = `${p.pct}%`;

    el.classList.toggle("is-complete", p.faltan === 0);
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data || data.ok === false) {
      const msg = (data && data.error) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

    function toast(msg) {
      const el = document.createElement("div");
      el.className = "am-toast";
      el.textContent = msg;
      document.body.appendChild(el);
      setTimeout(() => el.classList.add("show"), 10);
      setTimeout(() => {
        el.classList.remove("show");
        setTimeout(() => el.remove(), 200);
      }, 2200);
    }

    function setInlineResult(el, kind, msg) {
      if (!el) return;
      el.classList.remove("is-ok", "is-warn", "is-bad");
      if (kind) el.classList.add(`is-${kind}`);
      el.textContent = msg || "";
    }

    function pingAnimation(btn) {
      if (!btn) return;
      btn.classList.remove("is-pop");
      // force reflow to restart animation
      // eslint-disable-next-line no-unused-expressions
      btn.offsetWidth;
      btn.classList.add("is-pop");
      btn.addEventListener(
        "animationend",
        () => {
          btn.classList.remove("is-pop");
        },
        { once: true }
      );
    }

  function setChipState(btn, st, paisId, nombrePais) {
    btn.classList.remove("st-0", "st-1", "st-2");
    btn.classList.add(`st-${st}`);
    btn.dataset.state = String(st);
    const num = Number(btn.dataset.num || 0);
    const label = stateLabel[st] || "Falta";

    const p = byId.get(paisId);
    if (p && Array.isArray(p.figuritas)) {
      const f = p.figuritas.find((x) => Number(x.numero) === num);
      if (f) {
        f.estado = st;
        const n = (f.nombre || "").trim();
        const tip = (f.tipo || "").trim();
        const pos = (f.posicion || "").trim();
        const meta = [n || "-", tip || "", pos || ""].filter(Boolean).join(" · ");
        btn.title = `Figurita #${num} · ${nombrePais} · ${meta} · Estado: ${label}`;
        pingAnimation(btn);
        return;
      }
    }
    btn.title = `Figurita #${num} · ${nombrePais} · Estado: ${label}`;
    pingAnimation(btn);
  }

  async function onChipClick(ev) {
    const btn = ev.target.closest(".am-chip");
    const card = ev.target.closest(".am-country");
    if (!btn || !card) return;

    const paisId = Number(card.dataset.paisId);
    const p = byId.get(paisId);
    if (!p) return;

    const prev = Number(btn.dataset.state || 0);
    const next = (prev + 1) % 3;

    setChipState(btn, next, paisId, p.nombre || "País");
    recalcPais(p);
    updatePaisUI(paisId);
    updateTotalsUI(recalcTotals());
    if (isSideOpenFor(paisId)) renderSide(paisId);

    try {
      await postJson(endpoints.toggle, { pais_id: paisId, numero: Number(btn.dataset.num), estado: next });
    } catch (e) {
      setChipState(btn, prev, paisId, p.nombre || "País");
      recalcPais(p);
      updatePaisUI(paisId);
      updateTotalsUI(recalcTotals());
      if (isSideOpenFor(paisId)) renderSide(paisId);
      toast("No se pudo guardar (reintentá).");
    }
  }

  // Filters & ordering
  function applyFilters() {
    if (!elCountries) return;
    const q = String((elSearch && elSearch.value) || "").trim().toLowerCase();
    const view = String((elView && elView.value) || "all");
    const sort = String((elSort && elSort.value) || "order");

    let list = paises.slice();
    if (q) {
      list = list.filter((p) => String(p.nombre || "").toLowerCase().includes(q));
    }

    if (view === "missing") list = list.filter((p) => Number(p.faltan || 0) > 0);
    if (view === "dup") list = list.filter((p) => Number(p.repetidas || 0) > 0);
    if (view === "complete") list = list.filter((p) => Number(p.faltan || 0) === 0);
    if (view === "incomplete") list = list.filter((p) => Number(p.faltan || 0) > 0);

    const byName = (a, b) => String(a.nombre || "").localeCompare(String(b.nombre || ""), "es", { sensitivity: "base" });
    if (sort === "order") list.sort((a, b) => Number(a.orden || 0) - Number(b.orden || 0));
    if (sort === "name") list.sort(byName);
    if (sort === "most") list.sort((a, b) => (Number(b.tiene || 0) + Number(b.repetidas || 0)) - (Number(a.tiene || 0) + Number(a.repetidas || 0)));
    if (sort === "least") list.sort((a, b) => Number(b.faltan || 0) - Number(a.faltan || 0));
    if (sort === "dup") list.sort((a, b) => Number(b.repetidas || 0) - Number(a.repetidas || 0));

    const frag = document.createDocumentFragment();
    list.forEach((p) => {
      const el = elById.get(Number(p.id));
      if (el) frag.appendChild(el);
    });
    elCountries.innerHTML = "";
    elCountries.appendChild(frag);

    // Ocultar los que no estén en list
    const setVisible = new Set(list.map((p) => Number(p.id)));
    elById.forEach((el, id) => {
      el.style.display = setVisible.has(id) ? "" : "none";
    });
  }

  function resetFilters() {
    if (elSearch) elSearch.value = "";
    if (elView) elView.value = "all";
    if (elSort) elSort.value = "order";
    applyFilters();
  }

  // Clipboard helpers
  async function copyText(text) {
    try {
      if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {}

    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      return false;
    }
  }

  function buildList(kind) {
    const isMissing = kind === "missing";
    const title = isMissing ? "FALTANTES ÁLBUM MUNDIAL 2026" : "REPETIDAS ÁLBUM MUNDIAL 2026";
    const lines = [title, ""];
    paises.forEach((p) => {
      const nums = (p.figuritas || [])
        .filter((f) => (isMissing ? Number(f.estado) === 0 : Number(f.estado) === 2))
        .map((f) => Number(f.numero))
        .sort((a, b) => a - b);
      if (nums.length) lines.push(`${p.nombre}: ${nums.join(", ")}`);
    });
    return lines.join("\n");
  }

    async function onCopy(kind) {
      const text = buildList(kind);
      const ok = await copyText(text);
      toast(ok ? "Copiado al portapapeles." : "No se pudo copiar.");
    }

    async function applyImportRepetidas() {
      if (!elImportText || !elImportApply) return;
      const text = String(elImportText.value || "").trim();
      if (!text) {
        setInlineResult(elImportResult, "warn", "Pegá al menos una línea para importar.");
        return;
      }

      setInlineResult(elImportResult, "", "Importando…");
      try {
        const res = await postJson(endpoints.importRep, { text });
        const updated = Array.isArray(res.updated) ? res.updated : [];
        const touchedPais = new Set();

        updated.forEach((u) => {
          const pid = Number(u.pais_id);
          const num = Number(u.numero);
          const st = Number(u.estado);
          const p = byId.get(pid);
          if (!p) return;
          touchedPais.add(pid);
          const elCard = elById.get(pid);
          if (elCard) {
            const chip = elCard.querySelector(`.am-chip[data-num="${num}"]`);
            if (chip) setChipState(chip, st, pid, p.nombre || "País");
          }
          const f = (p.figuritas || []).find((x) => Number(x.numero) === num);
          if (f) f.estado = st;
        });

        touchedPais.forEach((pid) => {
          const p = byId.get(pid);
          if (!p) return;
          recalcPais(p);
          updatePaisUI(pid);
          if (isSideOpenFor(pid)) renderSide(pid);
        });

        updateTotalsUI(recalcTotals());
        applyFilters();

        const unknown = Array.isArray(res.unknown) ? res.unknown : [];
        const invalid = Array.isArray(res.invalid) ? res.invalid : [];

        const bits = [];
        bits.push(`Listo: ${updated.length} repetidas aplicadas.`);
        if (unknown.length) {
          bits.push(
            `País no encontrado: ${unknown.slice(0, 3).join(", ")}${unknown.length > 3 ? "…" : ""}`
          );
        }
        if (invalid.length) {
          bits.push(
            `Tokens inválidos: ${invalid.slice(0, 3).join(", ")}${invalid.length > 3 ? "…" : ""}`
          );
        }

        setInlineResult(elImportResult, unknown.length || invalid.length ? "warn" : "ok", bits.join(" "));
        toast("Importación aplicada.");
      } catch (e) {
        setInlineResult(elImportResult, "bad", "No se pudo importar (reintentá).");
        toast("No se pudo importar.");
      }
    }

    function clearImportBox() {
      if (elImportText) elImportText.value = "";
      setInlineResult(elImportResult, "", "");
    }

    async function exportBackup() {
      if (!endpoints.exportBackup) return;
      setInlineResult(elBackupResult, "", "Exportando…");
      try {
        const res = await fetch(endpoints.exportBackup, { method: "GET" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data || data.ok === false) throw new Error("bad");

        const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "-");
        const fileName = `album_mundial_2026_backup_${stamp}.json`;
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        setInlineResult(elBackupResult, "ok", `Backup exportado: ${fileName}`);
        toast("Backup exportado.");
      } catch (e) {
        setInlineResult(elBackupResult, "bad", "No se pudo exportar el backup.");
        toast("No se pudo exportar.");
      }
    }

    async function importBackupFromFile(file) {
      if (!file || !endpoints.importBackup) return;
      const ok = confirm("¿Importar backup? Esto pisa estados/nombres/tipos/posiciones.");
      if (!ok) return;
      setInlineResult(elBackupResult, "", "Importando…");

      try {
        const text = await file.text();
        const payload = JSON.parse(text);
        await postJson(endpoints.importBackup, { backup: payload });
        setInlineResult(elBackupResult, "ok", "Backup importado. Recargando…");
        toast("Backup importado.");
        setTimeout(() => window.location.reload(), 400);
      } catch (e) {
        setInlineResult(elBackupResult, "bad", "No se pudo importar el backup.");
        toast("No se pudo importar.");
      }
    }

    async function resetAlbum() {
      if (!endpoints.reset) return;
      const ok = confirm("¿Resetear el álbum? Solo resetea estados (no borra nombres).");
      if (!ok) return;
      setInlineResult(elBackupResult, "", "Reseteando…");

      try {
        await postJson(endpoints.reset, {});

        paises.forEach((p) => {
          (p.figuritas || []).forEach((f) => {
            f.estado = 0;
          });
          recalcPais(p);
          updatePaisUI(Number(p.id));

          const elCard = elById.get(Number(p.id));
          if (elCard) {
            elCard.querySelectorAll(".am-chip").forEach((chip) => {
              setChipState(chip, 0, Number(p.id), p.nombre || "País");
            });
          }
        });

        updateTotalsUI(recalcTotals());
        if (sidePaisId != null) renderSide(sidePaisId);
        applyFilters();

        setInlineResult(elBackupResult, "ok", "Álbum reseteado.");
        toast("Álbum reseteado.");
      } catch (e) {
        setInlineResult(elBackupResult, "bad", "No se pudo resetear.");
        toast("No se pudo resetear.");
      }
    }

    // Side panel
    let sidePaisId = null;
    function isSideOpenFor(pId) {
      return elSide && elSide.getAttribute("aria-hidden") === "false" && sidePaisId === pId;
    }

  function openSide(pId) {
    if (!elSide) return;
    sidePaisId = pId;
    elSide.setAttribute("aria-hidden", "false");
    renderSide(pId);
  }

  function closeSide() {
    if (!elSide) return;
    elSide.setAttribute("aria-hidden", "true");
    sidePaisId = null;
    if (elSideTableBody) elSideTableBody.innerHTML = "";
  }

  function renderSide(pId) {
    const p = byId.get(pId);
    if (!p) return;
    if (elSideTitle) elSideTitle.textContent = p.nombre || "País";
    if (elSideCode) elSideCode.textContent = (p.codigo || "").toUpperCase();
    if (elSideSub) elSideSub.textContent = `Avance: ${p.pct}%`;
    if (elSideTiene) elSideTiene.textContent = String(p.tiene || 0);
    if (elSideFaltan) elSideFaltan.textContent = String(p.faltan || 0);
    if (elSideRep) elSideRep.textContent = String(p.repetidas || 0);

    if (!elSideTableBody) return;
    elSideTableBody.innerHTML = "";
    (p.figuritas || []).forEach((f) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${f.numero}</strong></td>
        <td><input data-field="nombre" data-num="${f.numero}" value="${escapeHtml(f.nombre || "")}" placeholder="(vacío)"></td>
        <td><input data-field="tipo" data-num="${f.numero}" value="${escapeHtml(f.tipo || "")}" placeholder="Jugador / Escudo / DT"></td>
        <td><input data-field="posicion" data-num="${f.numero}" value="${escapeHtml(f.posicion || "")}" placeholder=""></td>
        <td>
          <select data-field="estado" data-num="${f.numero}">
            <option value="0" ${Number(f.estado) === 0 ? "selected" : ""}>Falta</option>
            <option value="1" ${Number(f.estado) === 1 ? "selected" : ""}>Tiene</option>
            <option value="2" ${Number(f.estado) === 2 ? "selected" : ""}>Repetida</option>
          </select>
        </td>
      `;
      elSideTableBody.appendChild(tr);
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  let saveTimer = null;
  function queueSave(pId, num, patch) {
    if (!patch) return;
    if (!saveTimer) {
      saveTimer = setTimeout(async () => {
        const pending = saveQueue.splice(0, saveQueue.length);
        saveTimer = null;
        for (const item of pending) {
          try {
            await postJson(endpoints.update, item);
          } catch (e) {
            toast("No se pudo guardar un cambio.");
          }
        }
      }, 250);
    }
    saveQueue.push({ pais_id: pId, numero: num, ...patch });
  }
  const saveQueue = [];

  function onSideChange(ev) {
    if (sidePaisId == null) return;
    const target = ev.target;
    if (!target) return;
    const field = target.getAttribute("data-field");
    const num = Number(target.getAttribute("data-num") || 0);
    if (!field || !num) return;

    const p = byId.get(sidePaisId);
    if (!p) return;
    const f = (p.figuritas || []).find((x) => Number(x.numero) === num);
    if (!f) return;

    if (field === "nombre") f.nombre = target.value;
    if (field === "tipo") f.tipo = target.value;
    if (field === "posicion") f.posicion = target.value;
    if (field === "estado") {
      const prev = Number(f.estado || 0);
      const next = Number(target.value || 0);
      f.estado = next;
      recalcPais(p);
      updatePaisUI(sidePaisId);
      updateTotalsUI(recalcTotals());
      // sync chip if visible
      const elCard = elById.get(sidePaisId);
      if (elCard) {
        const chip = elCard.querySelector(`.am-chip[data-num="${num}"]`);
        if (chip) setChipState(chip, next, sidePaisId, p.nombre || "País");
      }
      // If update fails we won't revert here; rare and ok.
      if (prev !== next) queueSave(sidePaisId, num, { estado: next });
      return;
    }

    // sync chip tooltip if visible
    const elCard = elById.get(sidePaisId);
    if (elCard) {
      const chip = elCard.querySelector(`.am-chip[data-num="${num}"]`);
      if (chip) setChipState(chip, Number(f.estado || 0), sidePaisId, p.nombre || "País");
    }
    queueSave(sidePaisId, num, { [field]: target.value });
  }

  // Init
  document.addEventListener("click", (ev) => {
    if (ev.target.closest(".am-chip")) return onChipClick(ev);

    const openBtn = ev.target.closest("[data-open-pais]");
    if (openBtn) return openSide(Number(openBtn.getAttribute("data-open-pais")));

    if (ev.target === elSide) return closeSide();
  });

  if (elSearch) elSearch.addEventListener("input", applyFilters);
  if (elView) elView.addEventListener("change", applyFilters);
  if (elSort) elSort.addEventListener("change", applyFilters);
  if (elReset) elReset.addEventListener("click", resetFilters);

    if (elCopyMissing) elCopyMissing.addEventListener("click", () => onCopy("missing"));
    if (elCopyDup) elCopyDup.addEventListener("click", () => onCopy("dup"));

    if (elImportApply) elImportApply.addEventListener("click", applyImportRepetidas);
    if (elImportClear) elImportClear.addEventListener("click", clearImportBox);

    if (elExportBackup) elExportBackup.addEventListener("click", exportBackup);
    if (elImportBackupFile) {
      elImportBackupFile.addEventListener("change", (ev) => {
        const file = ev.target && ev.target.files ? ev.target.files[0] : null;
        if (ev.target) ev.target.value = "";
        if (file) importBackupFromFile(file);
      });
    }
    if (elResetAlbum) elResetAlbum.addEventListener("click", resetAlbum);

    if (elSideClose) elSideClose.addEventListener("click", closeSide);
    if (elSideDone) elSideDone.addEventListener("click", closeSide);
  if (elSideTableBody) elSideTableBody.addEventListener("change", onSideChange);
  if (elSideTableBody) elSideTableBody.addEventListener("input", (ev) => {
    const t = ev.target;
    if (!t || t.tagName !== "INPUT") return;
    // debounce saves for typing
    onSideChange(ev);
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeSide();
  });

  // Basic totals bootstrap (in case backend changes)
  paises.forEach(recalcPais);
  updateTotalsUI(recalcTotals());
  applyFilters();
})();

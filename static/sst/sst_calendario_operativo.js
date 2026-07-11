(function () {
  const payloadNode = document.getElementById('sstCalendarPayload');
  const sidePanel = document.getElementById('sstCalendarSidePanel');
  const tooltip = document.getElementById('sstCalendarTooltip');
  if (!payloadNode || !sidePanel) return;

  let payload = {};
  try {
    payload = JSON.parse(payloadNode.textContent || '{}');
  } catch (error) {
    payload = {};
  }

  const meta = payload.__meta__ || {};
  const links = Array.from(document.querySelectorAll('.js-sst-calendar-group'));
  let activeLink = null;

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const parts = raw.split('-');
    if (parts.length !== 3) return raw;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  function getCell(cellKey) {
    const cell = payload[cellKey];
    if (!cell || typeof cell !== 'object') return null;
    return cell;
  }

  function getGroup(cellKey, groupKey) {
    const cell = getCell(cellKey);
    if (!cell) return null;
    return (cell.groups || []).find((group) => String(group.type_key || '') === String(groupKey || '')) || null;
  }

  function setActive(link) {
    if (activeLink) activeLink.classList.remove('is-active');
    activeLink = link || null;
    if (activeLink) activeLink.classList.add('is-active');
  }

  function renderRecords(records) {
    if (!Array.isArray(records) || !records.length) return '';
    return [
      '<ul class="sst-calendar-side-records">',
      records.map((record) => {
        const label = escapeHtml(record.label || 'Registro');
        const detail = escapeHtml(record.detail || '');
        return `<li><strong>${label}</strong>${detail ? `<span>${detail}</span>` : ''}</li>`;
      }).join(''),
      '</ul>'
    ].join('');
  }

  function renderEventItem(event) {
    const title = escapeHtml(event.title || event.type_label || 'Evento');
    const detail = escapeHtml(event.detail || '');
    const dateValue = formatDate(event.fecha_evento || '');
    const responsible = escapeHtml(event.responsible || '');
    const records = renderRecords(event.records || []);
    return [
      '<article class="sst-calendar-side-event">',
      `<div class="sst-calendar-side-event-head"><strong>${title}</strong><span>${dateValue || '-'}</span></div>`,
      detail ? `<p>${detail}</p>` : '',
      responsible ? `<small>${responsible}</small>` : '',
      records,
      '</article>'
    ].join('');
  }

  function renderPanel(group) {
    if (!group) {
      sidePanel.innerHTML = '<p class="sst-op-empty">No hay evento seleccionado.</p>';
      return;
    }
    const typeVisibleCount = Number((meta.type_counts || {})[group.type_key] || 0);
    const dateValue = formatDate(group.fecha_evento || '');
    const groupTitle = escapeHtml(group.title || group.type_label || 'Evento');
    const groupDetail = escapeHtml(group.detail || '');
    const eventItems = Array.isArray(group.events) ? group.events : [];
    const actionUrl = escapeHtml(group.url_detail || '#');
    const actionLabel = escapeHtml(group.action_label || 'Abrir');
    sidePanel.innerHTML = [
      '<section class="sst-calendar-side-detail">',
      '<div class="sst-calendar-side-top">',
      `<span class="sst-cal-group-link is-${escapeHtml(group.state_class || 'muted')} is-static"><span class="sst-cal-group-icon">${escapeHtml(group.type_icon || '')}</span><span class="sst-cal-group-code">${escapeHtml(group.type_short || '')}</span>${Number(group.count || 0) > 1 ? `<b>${Number(group.count || 0)}</b>` : ''}</span>`,
      `<span class="sst-calendar-side-state">${escapeHtml(group.state_icon || '')} ${escapeHtml(group.state_label || '')}</span>`,
      '</div>',
      `<h3>${escapeHtml(group.type_label || 'Evento')}</h3>`,
      `<p class="sst-calendar-side-place">${escapeHtml(group.sede_codigo || '')} - ${escapeHtml(group.sede_nombre || '')}</p>`,
      `<p class="sst-calendar-side-month">${escapeHtml(group.month_label || '')} ${escapeHtml(String((eventItems[0] && eventItems[0].year) || meta.selected_year || ''))}</p>`,
      '<div class="sst-calendar-side-metrics">',
      `<span>${Number(group.count || 0)} visibles en esta celda</span>`,
      `<span>${typeVisibleCount} visibles con filtros</span>`,
      '</div>',
      `<p class="sst-calendar-side-title">${groupTitle}</p>`,
      groupDetail ? `<p class="sst-calendar-side-text">${groupDetail}</p>` : '',
      dateValue ? `<p class="sst-calendar-side-date">Fecha: ${dateValue}</p>` : '',
      eventItems.length ? `<div class="sst-calendar-side-list">${eventItems.map(renderEventItem).join('')}</div>` : '',
      `<div class="sst-calendar-side-actions"><a class="sst-op-btn" href="${actionUrl}">${actionLabel}</a></div>`,
      '</section>'
    ].join('');
  }

  function renderTooltip(group) {
    if (!tooltip || !group) return;
    const dateValue = formatDate(group.fecha_evento || '');
    tooltip.innerHTML = [
      `<strong>${escapeHtml(group.type_icon || '')} ${escapeHtml(group.type_label || 'Evento')}</strong>`,
      `<span>${escapeHtml(group.sede_codigo || '')}</span>`,
      `<span>${escapeHtml(group.title || group.detail || '')}</span>`,
      dateValue ? `<span>${dateValue}</span>` : '',
      `<span>Estado: ${escapeHtml(group.state_label || '')}</span>`,
      '<span>Click para abrir.</span>'
    ].join('');
  }

  function placeTooltip(link, event) {
    if (!tooltip || tooltip.hidden) return;
    const rect = link.getBoundingClientRect();
    const offsetX = event && Number.isFinite(event.clientX) ? event.clientX : rect.left + (rect.width / 2);
    const offsetY = event && Number.isFinite(event.clientY) ? event.clientY : rect.top;
    const left = Math.max(12, Math.min(window.innerWidth - tooltip.offsetWidth - 12, offsetX + 12));
    const top = Math.max(12, offsetY - tooltip.offsetHeight - 14);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function showTooltip(link, group, event) {
    if (!tooltip || !group) return;
    renderTooltip(group);
    tooltip.hidden = false;
    placeTooltip(link, event);
  }

  function hideTooltip() {
    if (!tooltip) return;
    tooltip.hidden = true;
  }

  function selectLink(link, options) {
    if (!link) return;
    const cellKey = link.dataset.cellKey;
    const groupKey = link.dataset.groupKey;
    const group = getGroup(cellKey, groupKey);
    if (!group) return;
    setActive(link);
    renderPanel(group);
    if (options && options.showTooltip) showTooltip(link, group, options.event || null);
  }

  links.forEach((link) => {
    link.addEventListener('mouseenter', (event) => {
      selectLink(link, { showTooltip: true, event });
    });
    link.addEventListener('mousemove', (event) => {
      const group = getGroup(link.dataset.cellKey, link.dataset.groupKey);
      if (group) showTooltip(link, group, event);
    });
    link.addEventListener('mouseleave', hideTooltip);
    link.addEventListener('focus', () => {
      selectLink(link, { showTooltip: true });
    });
    link.addEventListener('blur', hideTooltip);
    link.addEventListener('click', () => {
      selectLink(link, { showTooltip: false });
    });
  });

  const preferredLink = document.querySelector('.sst-calendar-matrix td.is-current-month .js-sst-calendar-group')
    || document.querySelector('.sst-calendar-matrix .js-sst-calendar-group')
    || links[0];

  if (preferredLink) {
    selectLink(preferredLink, { showTooltip: false });
  } else {
    renderPanel(null);
  }

  window.addEventListener('scroll', hideTooltip, { passive: true });
  window.addEventListener('resize', hideTooltip);
})();

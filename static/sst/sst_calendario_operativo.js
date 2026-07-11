(function () {
  const payloadNode = document.getElementById('sstCalendarPayload');
  const tooltip = document.getElementById('sstCalendarTooltip');
  if (!payloadNode || !tooltip) return;

  let payload = {};
  try {
    payload = JSON.parse(payloadNode.textContent || '{}');
  } catch (error) {
    payload = {};
  }

  const links = Array.from(document.querySelectorAll('.js-sst-calendar-group'));

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

  function getGroup(link) {
    const cellKey = link.dataset.cellKey;
    const groupKey = link.dataset.groupKey;
    const cell = payload[cellKey];
    if (!cell) return null;
    return (cell.groups || []).find((group) => String(group.type_key || '') === String(groupKey || '')) || null;
  }

  function pushIf(lines, value) {
    const text = String(value || '').trim();
    if (text) lines.push(text);
  }

  function buildTooltipLines(group) {
    const event = Array.isArray(group.events) && group.events.length ? group.events[0] : null;
    const lines = [];

    if (group.type_key === 'matafuegos') {
      lines.push(`${Number(group.count || 0)} equipo${Number(group.count || 0) === 1 ? '' : 's'}`);
      pushIf(lines, group.title || '');
      if (event && event.last_service_date) {
        lines.push(`Última recarga: ${formatDate(event.last_service_date)}`);
      }
    } else if (group.type_key === 'visita') {
      pushIf(lines, (event && event.visit_type) || group.title || '');
      if (event && event.responsible) {
        lines.push(`Responsable: ${event.responsible}`);
      }
      lines.push((event && event.observaciones) ? event.observaciones : 'Sin observaciones');
    } else if (group.type_key === 'documentacion') {
      const detail = String(group.detail || '');
      if (detail.toLowerCase().startsWith('falta:')) {
        lines.push('Falta:');
        detail.replace(/^Falta:\s*/i, '').split(',').forEach((item) => pushIf(lines, item.trim()));
      } else if (detail) {
        detail.split('|').forEach((item) => pushIf(lines, item.trim()));
      }
    } else {
      pushIf(lines, group.title || '');
      String(group.detail || '').split('|').forEach((item) => pushIf(lines, item.trim()));
    }

    const dateValue = formatDate(group.fecha_evento || '');
    if (dateValue) lines.push(dateValue);
    lines.push('Estado:');
    lines.push(group.state_label || '');
    lines.push('Click para abrir.');
    return lines;
  }

  function renderTooltip(group) {
    const lines = buildTooltipLines(group);
    tooltip.innerHTML = [
      `<strong>${escapeHtml(group.type_icon || '')} ${escapeHtml(group.type_label || 'Evento')}</strong>`,
      `<span>${escapeHtml(group.sede_codigo || '')} - ${escapeHtml(group.sede_nombre || '')}</span>`,
      ...lines.map((line) => `<span>${escapeHtml(line)}</span>`)
    ].join('');
  }

  function placeTooltip(link, event) {
    const rect = link.getBoundingClientRect();
    const anchorX = event && Number.isFinite(event.clientX) ? event.clientX : rect.left + rect.width / 2;
    const anchorY = event && Number.isFinite(event.clientY) ? event.clientY : rect.top;
    const left = Math.max(12, Math.min(window.innerWidth - tooltip.offsetWidth - 12, anchorX + 12));
    const top = Math.max(12, anchorY - tooltip.offsetHeight - 14);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function showTooltip(link, event) {
    const group = getGroup(link);
    if (!group) return;
    renderTooltip(group);
    tooltip.hidden = false;
    placeTooltip(link, event);
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  links.forEach((link) => {
    link.addEventListener('mouseenter', (event) => showTooltip(link, event));
    link.addEventListener('mousemove', (event) => showTooltip(link, event));
    link.addEventListener('mouseleave', hideTooltip);
    link.addEventListener('focus', () => showTooltip(link));
    link.addEventListener('blur', hideTooltip);
  });

  window.addEventListener('scroll', hideTooltip, { passive: true });
  window.addEventListener('resize', hideTooltip);
})();

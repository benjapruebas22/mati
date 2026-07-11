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

  function splitDetailText(value) {
    return String(value || '')
      .split(/\||\u00B7|\u00C2\u00B7/)
      .map((item) => String(item || '').trim())
      .filter(Boolean);
  }

  function firstEvent(group) {
    return Array.isArray(group.events) && group.events.length ? group.events[0] : null;
  }

  function firstRecord(group) {
    const event = firstEvent(group);
    if (!event || !Array.isArray(event.records) || !event.records.length) return null;
    return event.records[0];
  }

  function buildTooltipLines(group) {
    const event = firstEvent(group);
    const lines = [];

    if (group.type_key === 'matafuegos') {
      const record = firstRecord(group);
      if (record && record.label) lines.push(record.label);
      splitDetailText(group.detail || '')
        .filter((item) => item.toLowerCase().startsWith('lote'))
        .forEach((item) => pushIf(lines, item));
      lines.push(`${Number(group.count || 0)} equipo${Number(group.count || 0) === 1 ? '' : 's'}`);
      if (group.fecha_evento) lines.push(`Vence: ${formatDate(group.fecha_evento)}`);
      if (event && event.last_service_date) lines.push(`Ultima recarga: ${formatDate(event.last_service_date)}`);
    } else if (group.type_key === 'visita') {
      if (group.fecha_evento) lines.push(`Ultima visita: ${formatDate(group.fecha_evento)}`);
      pushIf(lines, event && event.visit_type);
      lines.push(event && event.art_loaded ? 'ART cargada' : 'ART pendiente');
      lines.push((event && event.observaciones) ? event.observaciones : 'Sin observaciones');
    } else if (group.type_key === 'desinfeccion') {
      pushIf(lines, group.title || '');
      if (event && event.start_date) lines.push(`Inicio: ${formatDate(event.start_date)}`);
      if (event && event.end_date) lines.push(`Finalizacion: ${formatDate(event.end_date)}`);
      splitDetailText(group.detail || '').forEach((item) => pushIf(lines, item));
    } else {
      pushIf(lines, group.title || '');
      splitDetailText(group.detail || '').forEach((item) => pushIf(lines, item));
      const dateValue = formatDate(group.fecha_evento || '');
      if (dateValue) lines.push(dateValue);
    }

    if (group.state_label) lines.push(`Estado: ${group.state_label}`);
    lines.push('Click para abrir.');
    return lines;
  }

  function renderTooltip(group) {
    const lines = buildTooltipLines(group);
    const label = group.type_key === 'visita' ? 'Visita' : (group.type_label || 'Evento');
    tooltip.innerHTML = [
      `<strong>${escapeHtml(group.type_icon || '')} ${escapeHtml(label)}</strong>`,
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

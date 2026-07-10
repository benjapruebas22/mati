(function () {
  const payloadNode = document.getElementById('sstCalendarPayload');
  const dialog = document.getElementById('sstCalendarDetailDialog');
  const dialogTitle = document.getElementById('sstCalendarDialogTitle');
  const dialogBody = document.getElementById('sstCalendarDialogBody');
  const closeTop = document.getElementById('sstCalendarDialogCloseTop');
  const closeBottom = document.getElementById('sstCalendarDialogClose');
  if (!payloadNode || !dialog || !dialogTitle || !dialogBody) return;

  let payload = {};
  try {
    payload = JSON.parse(payloadNode.textContent || '{}');
  } catch (error) {
    payload = {};
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function groupEvents(events) {
    const grouped = {};
    (events || []).forEach((event) => {
      const key = String(event.type_key || 'otro');
      if (!grouped[key]) {
        grouped[key] = {
          typeLabel: event.type_label || 'Otro control SG-SST',
          typeShort: event.type_short || 'OT',
          items: [],
          totalUnits: 0
        };
      }
      grouped[key].items.push(event);
      grouped[key].totalUnits += Number(event.units || 1);
    });
    return Object.values(grouped).sort((a, b) => a.typeLabel.localeCompare(b.typeLabel, 'es'));
  }

  function renderEventItem(event) {
    const detail = escapeHtml(event.detail || '');
    const responsible = escapeHtml(event.responsible || '');
    const stateLabel = escapeHtml(event.state_label || '');
    const actionLabel = escapeHtml(event.action_label || 'Abrir');
    const actionUrl = String(event.url_detail || '').trim();
    const dateValue = escapeHtml(event.fecha_evento || '');
    return [
      '<article class="sst-calendar-event-item">',
      `<div class="sst-calendar-event-meta"><span class="sst-cal-indicator is-${escapeHtml(event.state_class || 'muted')}">${escapeHtml(event.type_short || 'OT')}</span><strong>${escapeHtml(event.title || '')}</strong><span class="sst-calendar-event-state">${stateLabel}</span></div>`,
      detail ? `<p>${detail}</p>` : '',
      '<div class="sst-calendar-event-foot">',
      `<span>${dateValue}${responsible ? ` · ${responsible}` : ''}</span>`,
      actionUrl ? `<a class="sst-op-btn" href="${escapeHtml(actionUrl)}">${actionLabel}</a>` : '',
      '</div>',
      '</article>'
    ].join('');
  }

  function renderCell(cellKey) {
    const cell = payload[cellKey];
    if (!cell) return;
    dialogTitle.textContent = cell.title || 'Detalle';
    const grouped = groupEvents(cell.events || []);
    if (!grouped.length) {
      dialogBody.innerHTML = '<p class="sst-op-empty">No hay eventos para esta celda.</p>';
    } else {
      dialogBody.innerHTML = grouped.map((group) => [
        '<section class="sst-calendar-event-group">',
        `<div class="sst-calendar-event-group-head"><span class="sst-cal-indicator">${escapeHtml(group.typeShort || 'OT')}</span><h3>${escapeHtml(group.typeLabel || '')}</h3><small>${group.totalUnits} registro${group.totalUnits === 1 ? '' : 's'}</small></div>`,
        '<div class="sst-calendar-event-group-list">',
        group.items.map(renderEventItem).join(''),
        '</div>',
        '</section>'
      ].join('')).join('');
    }
    if (!dialog.open) dialog.showModal();
  }

  document.querySelectorAll('.js-sst-calendar-cell').forEach((button) => {
    button.addEventListener('click', () => renderCell(button.dataset.cellKey));
    button.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        renderCell(button.dataset.cellKey);
      }
    });
  });

  [closeTop, closeBottom].forEach((button) => {
    if (!button) return;
    button.addEventListener('click', () => dialog.close());
  });

  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
})();

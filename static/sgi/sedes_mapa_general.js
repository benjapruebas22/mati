(function () {
  const root = document.querySelector('.mpd-map-app');
  const dataNode = document.getElementById('sedesMapData');
  if (!root || !dataNode) return;

  const sedes = JSON.parse(dataNode.textContent || '[]');
  const sedesByCode = new Map(sedes.map((sede) => [sede.codigo, sede]));
  const searchInput = document.getElementById('mapSearch');
  const searchResults = document.getElementById('mapSearchResults');
  const locationPicker = document.getElementById('mapLocationPicker');
  const locationPickerTitle = document.getElementById('mapLocationPickerTitle');
  const locationPickerOptions = document.getElementById('mapLocationPickerOptions');
  const susquesNode = document.getElementById('susquesItinerancia');
  const susquesTitle = document.getElementById('susquesHoverTitle');
  const susquesDialog = document.getElementById('susquesDialog');
  const susquesDialogClose = document.getElementById('susquesDialogClose');
  const susquesForm = document.getElementById('susquesForm');
  const susquesStatus = document.getElementById('susquesFormStatus');
  const susquesUltimoFecha = document.getElementById('susquesUltimoFecha');
  const susquesUltimoChofer = document.getElementById('susquesUltimoChofer');
  const susquesProximoFecha = document.getElementById('susquesProximoFecha');
  const susquesProximoChofer = document.getElementById('susquesProximoChofer');
  const guardiaNode = document.getElementById('guardiaMensualReference');
  const guardiaTitle = document.getElementById('guardiaMensualTitle');
  const guardiaDialog = document.getElementById('guardiaDialog');
  const guardiaDialogClose = document.getElementById('guardiaDialogClose');
  let susquesLoaded = false;
  const guardiaActual = {
    periodo: 'Julio 2026',
    responsable: 'Mat\u00edas Calderari'
  };

  const elements = {
    code: document.getElementById('panelCode'),
    name: document.getElementById('panelName'),
    address: document.getElementById('panelAddress'),
    fuero: document.getElementById('panelFuero'),
    maps: document.getElementById('panelMapsLink'),
    plan: document.getElementById('panelPlan'),
    planLink: document.getElementById('panelPlanLink'),
    depositCount: document.getElementById('panelDepositCount'),
    deposits: document.getElementById('panelDeposits'),
    news: document.getElementById('panelNews'),
    detail: document.getElementById('panelDetailLink'),
    metricDeposits: document.getElementById('metricDeposits'),
    metricPersonal: document.getElementById('metricPersonal'),
    metricInventory: document.getElementById('metricInventory'),
    metricAires: document.getElementById('metricAires'),
    metricLights: document.getElementById('metricLights'),
    metricExtinguishers: document.getElementById('metricExtinguishers')
  };

  const normalize = (value) => String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();

  const FUERO_COLORS = {
    'penal': '#6666CC',
    'juridico social': '#F14B94',
    'menores e incapaces': '#65BFF4',
    'central menores e incapaces': '#65BFF4',
    'administracion': '#F58A5E',
    'equipo interdisciplinario': '#F58A5E'
  };

  function updateUrl(code) {
    const url = new URL(window.location.href);
    url.searchParams.set('sede', code);
    window.history.replaceState({}, '', url);
  }

  function selectSite(code, options) {
    const sede = sedesByCode.get(code);
    if (!sede) return;
    const opts = options || {};

    document.querySelectorAll('.map-location').forEach((node) => {
      const selected = (node.dataset.siteCodes || '').split(',').includes(code);
      node.classList.toggle('is-selected', selected);
      node.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    document.querySelectorAll('.quick-site').forEach((node) => {
      node.classList.toggle('is-selected', node.dataset.siteCode === code);
    });
    document.querySelectorAll('.operativa-nav-shell .sede-nav [data-code]').forEach((node) => {
      const selected = node.dataset.code === code;
      node.classList.toggle('active', selected);
      if (selected) {
        node.setAttribute('aria-current', 'page');
      } else {
        node.removeAttribute('aria-current');
      }
    });
    document.querySelectorAll('.operativa-nav-shell [data-href-template]').forEach((node) => {
      const template = String(node.dataset.hrefTemplate || '').trim();
      if (!template) return;
      node.setAttribute('href', template.replace(/__SEDE__/g, code));
    });

    elements.code.textContent = sede.codigo;
    elements.name.textContent = sede.nombre;
    elements.address.textContent = [sede.ciudad, sede.direccion].filter(Boolean).join(' · ');
    elements.fuero.textContent = sede.fuero_label;
    const fueroColor = FUERO_COLORS[normalize(sede.fuero_label)] || '#6666CC';
    elements.code.style.color = fueroColor;
    elements.fuero.style.color = fueroColor;
    elements.plan.src = sede.plano_url;
    elements.plan.alt = `Plano de ${sede.codigo}, ${sede.nombre}`;
    elements.depositCount.textContent = `${sede.depositos_total} depositos`;
    elements.detail.href = sede.detalle_url;

    if (sede.url_maps) {
      elements.maps.href = sede.url_maps;
      elements.maps.hidden = false;
    } else {
      elements.maps.hidden = true;
    }

    const metrics = [
      ['metricDeposits', sede.depositos_total], ['metricPersonal', sede.personal],
      ['metricInventory', sede.inventario], ['metricAires', sede.aires],
      ['metricLights', sede.luminarias], ['metricExtinguishers', sede.matafuegos]
    ];
    metrics.forEach(([key, value]) => { elements[key].textContent = Number(value || 0).toLocaleString('es-AR'); });

    elements.deposits.replaceChildren();
    sede.depositos.slice(0, 12).forEach((deposito) => {
      const link = document.createElement('div');
      link.className = 'deposit-item';
      const codeNode = document.createElement('strong');
      codeNode.textContent = deposito.codigo_local;
      const description = document.createElement('span');
      description.textContent = deposito.descripcion;
      link.append(codeNode, description);
      elements.deposits.appendChild(link);
    });
    if (sede.depositos.length > 12) {
      const more = document.createElement('div');
      more.className = 'deposit-item';
      more.innerHTML = `<strong>+${sede.depositos.length - 12}</strong><span>Depositos adicionales</span>`;
      elements.deposits.appendChild(more);
    }

    elements.news.replaceChildren();
    if (sede.novedades.length) {
      sede.novedades.forEach((novedad) => {
        const item = document.createElement('li');
        item.textContent = [novedad.fecha, novedad.texto].filter(Boolean).join(' · ');
        elements.news.appendChild(item);
      });
      if (Number(sede.novedades_total || 0) > 3) {
        const historyItem = document.createElement('li');
        historyItem.className = 'news-history';
        historyItem.textContent = `+${Number(sede.novedades_total || 0) - sede.novedades.length} novedades anteriores`;
        elements.news.appendChild(historyItem);
      }
    } else {
      const item = document.createElement('li');
      item.className = 'empty';
      item.textContent = 'Sin novedades recientes registradas para esta sede.';
      elements.news.appendChild(item);
    }

    root.dataset.selectedCode = code;
    const operativaNav = document.querySelector('.operativa-nav-shell');
    if (operativaNav) {
      operativaNav.style.setProperty('--operativa-accent', FUERO_COLORS[normalize(sede.fuero_label)] || '#6666CC');
    }
    if (locationPickerOptions) {
      locationPickerOptions.querySelectorAll('button').forEach((button) => {
        button.classList.toggle('is-selected', button.dataset.siteCode === code);
      });
    }
    updateUrl(code);
    if (opts.focusPanel && window.matchMedia('(max-width: 1050px)').matches) {
      document.querySelector('.mpd-site-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  document.addEventListener('operativa-nav:select', (event) => {
    const code = String((event.detail || {}).code || '').trim().toUpperCase();
    if (!code) return;
    if (!root.contains((event.detail || {}).shell || null) && !document.querySelector('.operativa-nav-shell')) return;
    selectSite(code);
  });

  function openLocation(node) {
    const codes = (node.dataset.siteCodes || '').split(',').filter(Boolean);
    if (!codes.length) return;
    if (codes.length === 1) {
      if (locationPicker) locationPicker.hidden = true;
      selectSite(codes[0], { focusPanel: true });
      return;
    }
    locationPickerTitle.textContent = node.dataset.locationName || 'Localidad';
    locationPickerOptions.replaceChildren();
    codes.forEach((code) => {
      const sede = sedesByCode.get(code);
      if (!sede) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.siteCode = code;
      button.classList.toggle('is-selected', root.dataset.selectedCode === code);
      const name = document.createElement('strong');
      name.textContent = `${sede.codigo} · ${sede.nombre}`;
      const fuero = document.createElement('span');
      fuero.textContent = sede.fuero_label;
      button.append(name, fuero);
      button.addEventListener('click', () => selectSite(code, { focusPanel: true }));
      locationPickerOptions.appendChild(button);
    });
    locationPicker.hidden = false;
  }

  function formatDate(value) {
    const parts = String(value || '').split('-');
    return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : '-';
  }

  function fillDriverSelect(select, drivers, selectedValue) {
    if (!select) return;
    select.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = 'Sin asignar';
    select.appendChild(empty);
    const values = [...drivers];
    if (selectedValue && !values.includes(selectedValue)) values.push(selectedValue);
    values.forEach((driver) => {
      const option = document.createElement('option');
      option.value = driver;
      option.textContent = driver;
      option.selected = driver === selectedValue;
      select.appendChild(option);
    });
  }

  function renderSusques(data) {
    const last = data.ultimo || {};
    const next = data.proximo || {};
    const drivers = data.choferes || [];
    if (susquesTitle) {
      susquesTitle.textContent = last.fecha || last.chofer
        ? `Susques · Última itinerancia: ${formatDate(last.fecha)} · Chofer: ${last.chofer || 'Sin asignar'}`
        : 'Susques · Sin itinerancias registradas';
    }
    if (susquesUltimoFecha) susquesUltimoFecha.value = last.fecha || '';
    if (susquesProximoFecha) susquesProximoFecha.value = next.fecha || '';
    fillDriverSelect(susquesUltimoChofer, drivers, last.chofer || '');
    fillDriverSelect(susquesProximoChofer, drivers, next.chofer || '');
    susquesLoaded = true;
  }

  async function loadSusques(openDialog) {
    if (!susquesNode) return;
    if (openDialog && susquesDialog && !susquesDialog.open) susquesDialog.showModal();
    if (susquesLoaded) return;
    if (susquesStatus) susquesStatus.textContent = 'Cargando información...';
    try {
      const response = await fetch(susquesNode.dataset.summaryUrl, { credentials: 'same-origin' });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo consultar la itinerancia.');
      renderSusques(data);
      if (susquesStatus) susquesStatus.textContent = '';
    } catch (error) {
      if (susquesStatus) {
        susquesStatus.textContent = error.message;
        susquesStatus.className = 'susques-form-status is-error';
      }
    }
  }

  if (susquesNode) {
    susquesNode.addEventListener('mouseenter', () => loadSusques(false));
    susquesNode.addEventListener('click', () => loadSusques(true));
    susquesNode.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        loadSusques(true);
      }
    });
    loadSusques(false);
  }

  function openGuardiaDialog() {
    if (guardiaDialog && !guardiaDialog.open) guardiaDialog.showModal();
  }

  if (guardiaTitle) {
    guardiaTitle.textContent = [
      'Guardia mensual',
      guardiaActual.periodo,
      guardiaActual.responsable,
      'Click para ver turnero'
    ].join('\n');
  }

  if (guardiaNode) {
    guardiaNode.addEventListener('click', openGuardiaDialog);
    guardiaNode.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openGuardiaDialog();
      }
    });
  }

  if (susquesDialogClose) susquesDialogClose.addEventListener('click', () => susquesDialog.close());
  if (susquesDialog) {
    susquesDialog.addEventListener('click', (event) => {
      if (event.target === susquesDialog) susquesDialog.close();
    });
  }
  if (guardiaDialogClose) guardiaDialogClose.addEventListener('click', () => guardiaDialog.close());
  if (guardiaDialog) {
    guardiaDialog.addEventListener('click', (event) => {
      if (event.target === guardiaDialog) guardiaDialog.close();
    });
  }
  if (susquesForm) {
    susquesForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = susquesForm.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      susquesStatus.className = 'susques-form-status';
      susquesStatus.textContent = 'Guardando...';
      try {
        const response = await fetch(susquesNode.dataset.saveUrl, {
          method: 'POST',
          body: new FormData(susquesForm),
          credentials: 'same-origin'
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo guardar.');
        renderSusques(data);
        susquesStatus.className = 'susques-form-status is-success';
        susquesStatus.textContent = 'Itinerancia actualizada.';
      } catch (error) {
        susquesStatus.className = 'susques-form-status is-error';
        susquesStatus.textContent = error.message;
      } finally {
        if (submit) submit.disabled = false;
      }
    });
  }

  document.querySelectorAll('.map-location').forEach((node) => {
    node.addEventListener('click', () => openLocation(node));
    node.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openLocation(node);
      }
    });
  });

  document.querySelectorAll('.quick-site').forEach((node) => {
    node.addEventListener('click', () => selectSite(node.dataset.siteCode, { focusPanel: true }));
    node.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectSite(node.dataset.siteCode, { focusPanel: true });
      }
    });
  });

  function searchMatches(query) {
    const needle = normalize(query);
    if (!needle) return [];
    const matches = [];
    sedes.forEach((sede) => {
      const siteText = normalize([sede.codigo, sede.nombre, sede.ciudad, sede.direccion, sede.fuero_label].join(' '));
      if (siteText.includes(needle)) matches.push({ sede, deposito: null });
      sede.depositos.forEach((deposito) => {
        const depositText = normalize(`${sede.codigo}-${deposito.codigo_local} ${deposito.codigo_local} ${deposito.descripcion}`);
        if (depositText.includes(needle)) matches.push({ sede, deposito });
      });
    });
    return matches.slice(0, 8);
  }

  function renderSearchResults() {
    const matches = searchMatches(searchInput.value);
    searchResults.replaceChildren();
    if (!searchInput.value.trim()) {
      searchResults.hidden = true;
      return;
    }
    if (!matches.length) {
      const empty = document.createElement('div');
      empty.style.padding = '10px';
      empty.textContent = 'No se encontraron sedes o depositos.';
      searchResults.appendChild(empty);
      searchResults.hidden = false;
      return;
    }
    matches.forEach(({ sede, deposito }) => {
      const button = document.createElement('button');
      button.type = 'button';
      const label = document.createElement('strong');
      label.textContent = deposito ? `${sede.codigo}-${deposito.codigo_local}` : `${sede.codigo} · ${sede.nombre}`;
      const detail = document.createElement('small');
      detail.textContent = deposito ? deposito.descripcion : `${sede.ciudad} · ${sede.fuero_label}`;
      button.append(label, detail);
      button.addEventListener('click', () => {
        selectSite(sede.codigo, { focusPanel: true });
        searchResults.hidden = true;
      });
      searchResults.appendChild(button);
    });
    searchResults.hidden = false;
  }

  if (searchInput) {
    searchInput.addEventListener('input', renderSearchResults);
    searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        searchInput.value = '';
        searchResults.hidden = true;
      }
    });
  }
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.mpd-map-search') && !event.target.closest('.mpd-map-search-results')) {
      searchResults.hidden = true;
    }
  });

  selectSite(root.dataset.selectedCode || (sedes[0] && sedes[0].codigo));
})();

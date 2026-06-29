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

    elements.code.textContent = sede.codigo;
    elements.name.textContent = sede.nombre;
    elements.address.textContent = [sede.ciudad, sede.direccion].filter(Boolean).join(' · ');
    elements.fuero.textContent = sede.fuero_label;
    elements.fuero.style.color = FUERO_COLORS[normalize(sede.fuero_label)] || '#6666CC';
    elements.plan.src = sede.plano_url;
    elements.plan.alt = `Plano de ${sede.codigo}, ${sede.nombre}`;
    elements.planLink.href = `${sede.detalle_url}?tab=depositos`;
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
      const link = document.createElement('a');
      link.href = `${sede.detalle_url}?tab=depositos&local=${encodeURIComponent(deposito.codigo_local)}`;
      const codeNode = document.createElement('strong');
      codeNode.textContent = deposito.codigo_local;
      const description = document.createElement('span');
      description.textContent = deposito.descripcion;
      link.append(codeNode, description);
      elements.deposits.appendChild(link);
    });
    if (sede.depositos.length > 12) {
      const more = document.createElement('a');
      more.href = `${sede.detalle_url}?tab=depositos`;
      more.innerHTML = `<strong>+${sede.depositos.length - 12}</strong><span>Ver depositos restantes</span>`;
      elements.deposits.appendChild(more);
    }

    elements.news.replaceChildren();
    if (sede.novedades.length) {
      sede.novedades.forEach((novedad) => {
        const item = document.createElement('li');
        item.textContent = [novedad.fecha, novedad.texto].filter(Boolean).join(' · ');
        elements.news.appendChild(item);
      });
    } else {
      const item = document.createElement('li');
      item.className = 'empty';
      item.textContent = 'Sin novedades recientes registradas para esta sede.';
      elements.news.appendChild(item);
    }

    root.dataset.selectedCode = code;
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
        if (deposito) window.location.href = `${sede.detalle_url}?tab=depositos&local=${encodeURIComponent(deposito.codigo_local)}`;
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

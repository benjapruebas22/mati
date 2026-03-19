(function () {
  function ready(fn){ document.readyState !== "loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  ready(() => {
    const mapEl = document.getElementById("map_unificado") || document.getElementById("map");
    if (!mapEl) return;

    // Si Leaflet no cargó, no explota: solo no inicia
    if (typeof L === "undefined") {
      console.error("Leaflet (L) no cargó. Revisá que los <script defer> estén en block scripts.");
      return;
    }

    // Helpers
    function toNum(v) {
      if (v === null || v === undefined) return null;
      if (typeof v === "number") return isFinite(v) ? v : null;
      const s = String(v).trim().replace(",", ".").replace(/,$/, "");
      const n = parseFloat(s);
      return isFinite(n) ? n : null;
    }

    function iconPin(colorHex) {
      const c = colorHex || "#64748b";
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24">
        <path fill="${c}" d="M12 2c-4.97 0-9 4.03-9 9c0 7 9 11 9 11s9-4 9-11c0-4.97-4.03-9-9-9m0 12.75a3.75 3.75 0 1 1 0-7.5a3.75 3.75 0 0 1 0 7.5Z"/>
      </svg>`;
      return L.divIcon({ className: "pin", html: svg, iconSize: [28, 28], iconAnchor: [14, 24] });
    }

    // MAPA
    const map = L.map(mapEl, { zoomControl: true }).setView([-23.7, -65.3], 8);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    }).addTo(map);

    const JUJUY_BOUNDS = L.latLngBounds(
      L.latLng(-24.60, -67.40),
      L.latLng(-21.60, -64.10)
    );
    map.setMaxBounds(JUJUY_BOUNDS);
    map.setMinZoom(7);
    map.setMaxZoom(19);

    // Capas (MarkerCluster)
    const layerAsistidos     = L.markerClusterGroup();
    const layerProveedores   = L.markerClusterGroup();
    const layerSedesMPD      = L.markerClusterGroup();
    const layerInstituciones = L.markerClusterGroup();
    const layerOtros         = L.markerClusterGroup();

    map.addLayer(layerAsistidos);
    map.addLayer(layerProveedores);
    map.addLayer(layerSedesMPD);
    map.addLayer(layerInstituciones);
    map.addLayer(layerOtros);

    L.control.layers(null, {
      "Asistidos": layerAsistidos,
      "Proveedores": layerProveedores,
      "Sedes MPD": layerSedesMPD,
      "Instituciones": layerInstituciones,
      "Otros": layerOtros,
    }).addTo(map);

    // Inputs
    const aLat = document.getElementById("a-lat");
    const aLng = document.getElementById("a-lng");
    const btnModo = document.getElementById("btn-modo-marcar");

    const qBuscar  = document.getElementById("q-buscar");
    const btnBusca = document.getElementById("btn-buscar");

    let modoMarcar = false;
    let pinManual = null;

    if (btnModo){
      btnModo.addEventListener("click", () => {
        modoMarcar = !modoMarcar;
        btnModo.textContent = modoMarcar ? "Marcador ACTIVO (click en mapa)" : "Activar marcador (click en mapa)";
      });
    }

    map.on("click", (e) => {
      if (!modoMarcar) return;
      if (aLat) aLat.value = e.latlng.lat.toFixed(6);
      if (aLng) aLng.value = e.latlng.lng.toFixed(6);

      if (pinManual) map.removeLayer(pinManual);
      pinManual = L.marker([e.latlng.lat, e.latlng.lng], { icon: iconPin("#eab308") }).addTo(map);
    });

    // Buscador (Nominatim)
    async function geocode(q){
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=1`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j || !j.length) return null;
      return { lat: parseFloat(j[0].lat), lng: parseFloat(j[0].lon) };
    }

    if (btnBusca && qBuscar){
      btnBusca.addEventListener("click", async () => {
        const q = (qBuscar.value || "").trim();
        if (!q) return;
        try{
          const pos = await geocode(q + ", Jujuy, Argentina");
          if (!pos) return;
          map.setView([pos.lat, pos.lng], 13);
        }catch(e){
          console.error("Error buscando:", e);
        }
      });
    }

    // Colores
    function colorForEstado(est) {
      const s = (est || "").toUpperCase();
      if (s === "NO_REALIZADA") return "#94a3b8";
      if (s === "A_VOLVER")     return "#2563eb";
      if (s === "PROBLEMA")     return "#dc2626";
      if (s === "CERRADA")      return "#16a34a";
      return "#6b7280";
    }

    // Popups
    function popupAsistido(a) {
      const lat = toNum(a.lat), lng = toNum(a.lng);
      const maps = (lat !== null && lng !== null) ? `https://www.google.com/maps?q=${lat},${lng}` : null;
      return `
        <div style="min-width:240px">
          <strong>${a.nombre || ""}</strong><br>
          <small>${a.barrio || ""}</small><br>
          <small>${a.direccion || ""}</small><br>
          ${a.referencia ? `<small>Ref: ${a.referencia}</small><br>` : ``}
          ${a.telefono ? `<small>Tel: ${a.telefono}</small><br>` : ``}
          ${maps ? `<a target="_blank" href="${maps}">Abrir en Google Maps</a>` : ``}
        </div>`;
    }

    function popupPunto(p) {
      const lat = toNum(p.lat), lng = toNum(p.lng);
      const maps = (lat !== null && lng !== null) ? `https://www.google.com/maps?q=${lat},${lng}` : null;
      return `
        <div style="min-width:240px">
          <strong>${p.nombre || ""}</strong><br>
          ${p.ciudad ? `<small>${p.ciudad}</small><br>` : ``}
          ${p.direccion ? `<small>${p.direccion}</small><br>` : ``}
          ${p.telefono ? `<small>Tel: ${p.telefono}</small><br>` : ``}
          ${maps ? `<a target="_blank" href="${maps}">Abrir en Google Maps</a>` : ``}
        </div>`;
    }

    // Loads
    async function loadAsistidos() {
      layerAsistidos.clearLayers();
      const r = await fetch("/api/asistidos");
      const data = await r.json();

      data.forEach((a) => {
        const lat = toNum(a.lat), lng = toNum(a.lng);
        if (lat !== null && lng !== null) {
          L.marker([lat, lng], { icon: iconPin(colorForEstado(a.estado)) })
            .bindPopup(popupAsistido(a))
            .addTo(layerAsistidos);
        }
      });
    }

    async function loadPuntos() {
      layerProveedores.clearLayers();
      layerInstituciones.clearLayers();
      layerOtros.clearLayers();

      const r = await fetch("/api/puntos_mapa");
      const data = await r.json();

      data.forEach((p) => {
        const lat = toNum(p.lat), lng = toNum(p.lng);
        if (lat !== null && lng !== null) {
          const t = (p.tipo || "OTRO").toUpperCase();
          let layer = layerOtros;
          let color = "#334155";

          if (t === "PROVEEDOR") { layer = layerProveedores; color = "#f97316"; }
          else if (t === "INSTITUCION") { layer = layerInstituciones; color = "#8b5cf6"; }
          else if (t === "SEDE") { layer = layerOtros; color = "#0ea5e9"; }

          L.marker([lat, lng], { icon: iconPin(color) })
            .bindPopup(popupPunto(p))
            .addTo(layer);
        }
      });
    }

    async function loadSedesMPD() {
      layerSedesMPD.clearLayers();
      const r = await fetch("/api/sedes_mpd");
      const data = await r.json();

      data.forEach((s) => {
        const lat = toNum(s.lat), lng = toNum(s.lng);
        if (lat !== null && lng !== null) {
          const html = `
            <div style="min-width:240px">
              <strong>${s.codigo} — ${s.nombre || ""}</strong><br>
              <small>${s.ciudad || ""}</small><br>
              <small>${s.direccion || ""}</small>
              ${s.maps_url ? `<br><a target="_blank" href="${s.maps_url}">Abrir en Google Maps</a>` : ``}
            </div>
          `;
          L.marker([lat, lng], { icon: iconPin("#0ea5e9") })
            .bindPopup(html)
            .addTo(layerSedesMPD);
        }
      });
    }

    async function reloadAll() {
      const results = await Promise.allSettled([loadAsistidos(), loadPuntos(), loadSedesMPD()]);
      results.forEach((r, i) => {
        if (r.status === "rejected") {
          const nombre = i === 0 ? "asistidos" : (i === 1 ? "puntos_mapa" : "sedes_mpd");
          console.error(`Error cargando ${nombre}:`, r.reason);
        }
      });
    }

    reloadAll();
  });
})();

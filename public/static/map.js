/* Interaction bridge for the Python-generated Folium map. */
(() => {
  "use strict";
  const config = window.ATLAS_MAP_CONFIG;
  if (!config || !window.L) return;
  const map = config.map;
  let selectedSpecies = null;
  let currentBasemap = "street";
  let lastTileError = 0;

  function notify(message) {
    if (window.parent !== window) window.parent.postMessage(message, window.location.origin);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function shownRecords(locationId) {
    return config.locations[locationId].filter(record => !selectedSpecies || record.species_id === selectedSpecies);
  }

  function makePopup(records, startIndex, popup) {
    const container = element("article", "observation-popup");
    let index = startIndex;
    function render() {
      container.replaceChildren();
      const record = records[index];
      const species = config.species[record.species_id];
      if (record.image) {
        const figure = element("figure", "observation-photo");
        const image = element("img");
        image.src = record.image + "?size=640";
        image.alt = record.name + " representative species photograph";
        image.loading = "lazy";
        image.addEventListener("load", () => popup.update());
        image.addEventListener("error", () => { figure.remove(); popup.update(); });
        figure.append(image, element("figcaption", "", "Representative species photo"));
        container.append(figure);
      }
      const body = element("div", "observation-body");
      const eyebrow = element("div", "observation-eyebrow");
      const dot = element("span", "observation-dot");
      dot.style.backgroundColor = species.color;
      eyebrow.append(dot, document.createTextNode("FIELD OBSERVATION"));
      body.append(eyebrow, element("h2", "observation-name", record.name));
      if (record.scientific_name) body.append(element("p", "observation-scientific", record.scientific_name));

      const coordinates = element("dl", "observation-coordinates");
      const latitude = element("div");
      latitude.append(element("dt", "", "Latitude"), element("dd", "", Number(record.latitude).toFixed(6) + "°"));
      const longitude = element("div");
      longitude.append(element("dt", "", "Longitude"), element("dd", "", Number(record.longitude).toFixed(6) + "°"));
      coordinates.append(latitude, longitude);
      body.append(coordinates);
      if (record.elevation !== undefined && record.elevation !== null) {
        body.append(element("p", "observation-extra", "Elevation: " + record.elevation));
      }
      body.append(element("p", "observation-source", "Record " + record.id + " · Source row " + record.source_row));
      container.append(body);

      if (records.length > 1) {
        const pager = element("div", "observation-pager");
        const previous = element("button", "observation-page-button", "←");
        previous.type = "button";
        previous.setAttribute("aria-label", "Previous observation at this location");
        const next = element("button", "observation-page-button", "→");
        next.type = "button";
        next.setAttribute("aria-label", "Next observation at this location");
        previous.addEventListener("click", event => { event.stopPropagation(); index = (index - 1 + records.length) % records.length; render(); });
        next.addEventListener("click", event => { event.stopPropagation(); index = (index + 1) % records.length; render(); });
        const label = element("span", "observation-page-label", (index + 1) + " of " + records.length + " at this location");
        pager.append(previous, label, next);
        container.append(pager);
      }
      requestAnimationFrame(() => popup.update());
    }
    render();
    L.DomEvent.disableClickPropagation(container);
    L.DomEvent.disableScrollPropagation(container);
    return container;
  }

  config.markers.forEach(item => {
    const marker = item.layer;
    marker.on("click", () => {
      const records = shownRecords(item.locationId);
      if (!records.length) return;
      const first = Math.max(0, records.findIndex(record => record.species_id === item.speciesId));
      const popup = L.popup({
        className: "atlas-popup", maxWidth: 298, minWidth: 260,
        maxHeight: Math.max(180, Math.min(510, map.getSize().y - 70)),
        autoPanPadding: [24, 24], closeButton: true,
      });
      popup.setLatLng(marker.getLatLng());
      popup.setContent(makePopup(records, first, popup));
      popup.openOn(map);
    });
    function enableKeyboard() {
      const path = marker.getElement();
      if (!path || path.dataset.atlasKeyboard) return;
      path.dataset.atlasKeyboard = "true";
      path.setAttribute("tabindex", "0");
      path.setAttribute("role", "button");
      path.setAttribute("aria-label", config.species[item.speciesId].name + ", open observations");
      path.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); marker.fire("click"); }
      });
    }
    marker.on("add", enableKeyboard);
    enableKeyboard();
  });

  function fitBounds(bounds) {
    map.invalidateSize();
    map.fitBounds(bounds, {padding: [42, 42], maxZoom: 18, animate: !matchMedia("(prefers-reduced-motion: reduce)").matches});
  }

  function fitSelection() {
    if (!selectedSpecies) { fitBounds(config.bounds); return; }
    const points = Object.values(config.locations).flat().filter(record => record.species_id === selectedSpecies).map(record => [record.latitude, record.longitude]);
    if (points.length) fitBounds(points);
  }

  function selectSpecies(id) {
    if (id && !Object.hasOwn(config.groups, id)) return false;
    selectedSpecies = id || null;
    map.closePopup();
    Object.entries(config.groups).forEach(([speciesId, group]) => {
      if (!selectedSpecies || selectedSpecies === speciesId) {
        if (!map.hasLayer(group)) map.addLayer(group);
      } else if (map.hasLayer(group)) map.removeLayer(group);
    });
    fitSelection();
    return true;
  }

  function setBasemap(name) {
    if (!Object.hasOwn(config.basemaps, name) || name === currentBasemap) return false;
    map.removeLayer(config.basemaps[currentBasemap]);
    config.basemaps[name].addTo(map);
    currentBasemap = name;
    return true;
  }

  Object.values(config.basemaps).forEach(layer => {
    layer.on("tileerror", () => {
      if (Date.now() - lastTileError > 15000) {
        lastTileError = Date.now();
        notify({type: "atlas:tile-error", basemap: currentBasemap});
      }
    });
  });

  function publishPosition() {
    const center = map.getCenter();
    notify({type: "atlas:move", latitude: center.lat, longitude: center.lng, zoom: map.getZoom()});
  }
  map.on("moveend", publishPosition);
  map.on("popupopen", () => notify({type: "atlas:popup", open: true}));
  map.on("popupclose", () => notify({type: "atlas:popup", open: false}));
  map.on("mousemove", event => notify({type: "atlas:cursor", latitude: event.latlng.lat, longitude: event.latlng.lng}));
  window.AtlasMap = {
    selectSpecies,
    fitAll: () => fitBounds(config.bounds),
    fitSelection,
    setBasemap,
    zoomIn: () => map.zoomIn(),
    zoomOut: () => map.zoomOut(),
    invalidateSize: () => map.invalidateSize(),
  };
  window.addEventListener("resize", () => map.invalidateSize());
  notify({type: "atlas:ready"});
  publishPosition();
})();

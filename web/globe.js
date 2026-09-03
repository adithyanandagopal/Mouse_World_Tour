// Mouse World Tour -- Cesium globe controller.
// Exposes window.initJourney / addWaypoint / updateCurrentPosition /
// updateOverlayStats / clearJourney / replayReset / replayStep, all called
// from Python via QWebEngineView.runJavaScript.

Cesium.Ion.defaultAccessToken = undefined; // no ion account needed

// Cesium ships its own offline "Natural Earth II" imagery -- using it
// instead of a live tile server means the globe always renders a full,
// colourful world (no blank/grey tiles if a map server is unreachable).
// TileMapServiceImageryProvider.fromUrl() is async (Cesium >= 1.104), so the
// viewer is created with no base layer and the imagery is attached once it
// resolves.
const viewer = new Cesium.Viewer('cesiumContainer', {
  baseLayer: false,
  terrainProvider: new Cesium.EllipsoidTerrainProvider(),
  baseLayerPicker: false,
  geocoder: false,
  homeButton: true,
  sceneModePicker: true,
  navigationHelpButton: false,
  animation: false,
  timeline: false,
  fullscreenButton: false,
  infoBox: false,
  selectionIndicator: false,
  shouldAnimate: true,
});
viewer.scene.globe.enableLighting = false;
viewer.scene.skyAtmosphere.hueShift = 0.0;
viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a2a43');

Cesium.TileMapServiceImageryProvider.fromUrl(
  Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')
).then(function (imageryProvider) {
  viewer.imageryLayers.addImageryProvider(imageryProvider);
  document.getElementById('loadingMsg').style.display = 'none';
}).catch(function (err) {
  document.getElementById('loadingMsg').textContent = 'Globe imagery failed to load.';
  console.error('Failed to load Natural Earth II imagery:', err);
});

const DIRECTION_COLORS = {
  N: Cesium.Color.DODGERBLUE,
  E: Cesium.Color.LIMEGREEN,
  S: Cesium.Color.CRIMSON,
  W: Cesium.Color.GOLD,
};
const DIRECTION_ARROWS = { N: '⬆', E: '➡', S: '⬇', W: '⬅' };

function emojiCanvas(emoji, size) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.font = `${Math.round(size * 0.8)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, size / 2, size / 2 + size * 0.05);
  return canvas;
}

let homeEntity = null;
let currentEntity = null;
let arrowEntity = null;
let lastPoint = null; // [lat, lon]

// Route rendering: consecutive same-direction segments are merged into one
// polyline entity so long straight runs don't create thousands of entities.
let activePolyline = null;
let activePolylineDirection = null;
let activePolylinePositions = []; // flat [lon, lat, lon, lat, ...]
let allRouteEntities = [];

function addRouteSegment(from, to, direction) {
  const color = DIRECTION_COLORS[direction] || Cesium.Color.WHITE;
  if (activePolyline && activePolylineDirection === direction) {
    activePolylinePositions.push(to[1], to[0]);
    activePolyline.polyline.positions = Cesium.Cartesian3.fromDegreesArray(activePolylinePositions);
    return;
  }
  activePolylinePositions = [from[1], from[0], to[1], to[0]];
  activePolylineDirection = direction;
  activePolyline = viewer.entities.add({
    polyline: {
      positions: Cesium.Cartesian3.fromDegreesArray(activePolylinePositions),
      width: 3,
      material: color,
      clampToGround: false,
    },
  });
  allRouteEntities.push(activePolyline);
}

function placeMarkers(lat, lon) {
  currentEntity = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lon, lat),
    billboard: { image: emojiCanvas('🖱️', 64), width: 36, height: 36 },
  });
  arrowEntity = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lon, lat),
    label: {
      text: '',
      font: '28px sans-serif',
      pixelOffset: new Cesium.Cartesian2(0, -42),
    },
  });
}

window.initJourney = function (data) {
  window.clearJourney();
  const [homeLat, homeLon] = data.home;
  homeEntity = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(homeLon, homeLat),
    billboard: { image: emojiCanvas('🏠', 64), width: 32, height: 32 },
    description: 'Starting point',
  });

  let prev = [homeLat, homeLon];
  (data.waypoints || []).forEach((wp) => {
    addRouteSegment(prev, [wp.lat, wp.lon], wp.direction);
    prev = [wp.lat, wp.lon];
  });
  lastPoint = prev;

  placeMarkers(prev[0], prev[1]);
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(prev[1], prev[0], 4000000),
  });
  updateCoordsText(prev[0], prev[1]);
};

window.addWaypoint = function (lat, lon, direction) {
  if (!lastPoint) lastPoint = [lat, lon];
  addRouteSegment(lastPoint, [lat, lon], direction);
  lastPoint = [lat, lon];
};

window.updateCurrentPosition = function (lat, lon, direction) {
  if (!currentEntity) placeMarkers(lat, lon);
  currentEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat);
  if (arrowEntity) {
    arrowEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat);
    arrowEntity.label.text = DIRECTION_ARROWS[direction] || '';
  }
  updateCoordsText(lat, lon);
};

function updateCoordsText(lat, lon) {
  const el = document.getElementById('statCoords');
  if (el) el.textContent = `Lat ${lat.toFixed(3)}, Lon ${lon.toFixed(3)}`;
}

window.updateOverlayStats = function (distanceKm, city, timeStr) {
  const d = document.getElementById('statDistance');
  const c = document.getElementById('statCity');
  const t = document.getElementById('statTime');
  if (d) d.textContent = `${distanceKm.toFixed(2)} km`;
  if (c) c.textContent = city;
  if (t) t.textContent = timeStr;
};

window.clearJourney = function () {
  allRouteEntities.forEach((e) => viewer.entities.remove(e));
  allRouteEntities = [];
  activePolyline = null;
  activePolylineDirection = null;
  activePolylinePositions = [];
  if (homeEntity) { viewer.entities.remove(homeEntity); homeEntity = null; }
  if (currentEntity) { viewer.entities.remove(currentEntity); currentEntity = null; }
  if (arrowEntity) { viewer.entities.remove(arrowEntity); arrowEntity = null; }
  lastPoint = null;
};

// ---- Replay support ----
window.replayReset = function (homeLat, homeLon) {
  window.clearJourney();
  homeEntity = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(homeLon, homeLat),
    billboard: { image: emojiCanvas('🏠', 64), width: 32, height: 32 },
  });
  placeMarkers(homeLat, homeLon);
  lastPoint = [homeLat, homeLon];
  updateCoordsText(homeLat, homeLon);
  viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(homeLon, homeLat, 4000000) });
};

window.replayStep = function (lat, lon, direction) {
  window.addWaypoint(lat, lon, direction);
  window.updateCurrentPosition(lat, lon, direction);
};

// ---- Idle auto-rotation: keeps the globe feeling alive when nobody is
// dragging it, without fighting the user's own camera control. ----
let lastInteraction = Date.now();
const IDLE_DELAY_MS = 3000;
const IDLE_ROTATE_RATE = 0.00025; // radians per frame, gentle spin

// Only actual drag/zoom counts as "interacting" -- otherwise the globe
// covering the whole window would never be considered idle.
['pointerdown', 'wheel'].forEach((evt) => {
  viewer.scene.canvas.addEventListener(evt, () => {
    lastInteraction = Date.now();
  });
});

viewer.clock.onTick.addEventListener(() => {
  if (Date.now() - lastInteraction > IDLE_DELAY_MS) {
    viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, -IDLE_ROTATE_RATE);
  }
});

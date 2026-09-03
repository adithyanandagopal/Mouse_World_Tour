// Mouse World Tour -- Cesium globe controller.
// Exposes window.initJourney / addWaypoint / updateCurrentPosition /
// updateOverlayStats / setDistanceHidden / clearJourney / replayReset /
// replayStep, all called from Python via QWebEngineView.runJavaScript.

Cesium.Ion.defaultAccessToken = undefined; // no ion account needed

// ESRI's World Imagery (free, no API key) gives real satellite-resolution
// detail at every zoom level -- the earlier bundled offline basemap looked
// blurry once you zoomed past continent-scale. ArcGisMapServerImageryProvider
// is async (Cesium >= 1.104), so the viewer starts with no base layer and
// the imagery is attached once it resolves.
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
viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a2a43');
// Smoother edges/lines and crisper text on high-DPI displays.
viewer.scene.msaaSamples = 4;
if (viewer.scene.postProcessStages.fxaa) {
  viewer.scene.postProcessStages.fxaa.enabled = true;
}
viewer.resolutionScale = window.devicePixelRatio || 1;

Cesium.ArcGisMapServerImageryProvider.fromUrl(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
).then(function (imageryProvider) {
  viewer.imageryLayers.addImageryProvider(imageryProvider);
  document.getElementById('loadingMsg').style.display = 'none';
}).catch(function (err) {
  document.getElementById('loadingMsg').textContent = 'Globe imagery failed to load.';
  console.error('Failed to load World Imagery basemap:', err);
});

const ROUTE_COLOR = Cesium.Color.RED;
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

function glowMaterial(color) {
  return new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.18, color });
}

// ---- Route state ----
// finalizedCorners holds one entry per direction RUN, not per raw tick:
// consecutive same-direction waypoints are colinear, so they're compressed
// into a single leg and only the point where the direction actually changes
// becomes a "corner". Each corner's `direction` is the OUTGOING run it
// starts (corner[0] = starting location). Rounding a fraction of an actual
// multi-kilometre leg (rather than a fraction of the ~tick-sized gap between
// individual raw waypoints) is what makes the fillet visible at all.
//
// Corners are rendered via corner-cutting (a small quadratic-Bezier fillet
// at each turn) rather than an interpolating spline -- an interpolating
// spline (e.g. Catmull-Rom) is guaranteed to still pass exactly through
// every sharp corner, so it doesn't actually look rounded. Cutting the
// corner (not visiting the exact vertex) is what reads as smooth.
let finalizedCorners = [];
let nextCornerToFinalize = 1; // finalizedCorners[i] is finalizable once i+1 exists
let lastDrawnPoint = null; // {lon, lat} -- where the drawn polyline currently ends
let allRouteEntities = [];
let routePolylineEntity = null; // single continuous polyline for the whole finalized route
let routePositions = []; // flat [lon, lat, lon, lat, ...]
let liveTailEntity = null; // straight "in progress" edge from the drawn route's end to the live cursor

let currentEntity = null;
let arrowEntity = null;

const FILLET_FRACTION = 0.3; // how far into each leg the corner rounding extends
const FILLET_STEPS = 16; // samples per curved fillet arc

function lerpPoint(a, b, t) {
  return { lon: a.lon + (b.lon - a.lon) * t, lat: a.lat + (b.lat - a.lat) * t };
}

function quadraticBezierPoint(p0, p1, p2, t) {
  const mt = 1 - t;
  return {
    lon: mt * mt * p0.lon + 2 * mt * t * p1.lon + t * t * p2.lon,
    lat: mt * mt * p0.lat + 2 * mt * t * p1.lat + t * t * p2.lat,
  };
}

function appendFinalized(flatDegreePoints) {
  if (routePolylineEntity) {
    routePositions.push(...flatDegreePoints.slice(2)); // skip duplicate join point
    routePolylineEntity.polyline.positions = Cesium.Cartesian3.fromDegreesArray(routePositions);
    return;
  }
  routePositions = flatDegreePoints.slice();
  routePolylineEntity = viewer.entities.add({
    polyline: {
      positions: Cesium.Cartesian3.fromDegreesArray(routePositions),
      width: 6,
      material: glowMaterial(ROUTE_COLOR),
    },
  });
  allRouteEntities.push(routePolylineEntity);
}

// Finalizes the turn at finalizedCorners[i]: draws the straight leg-in up
// to the fillet, then a rounded arc (using the corner itself as the
// Bezier control point) that cuts across the corner instead of touching it.
function finalizeCorner(i) {
  const A = finalizedCorners[i - 1]; // start of the incoming leg
  const C = finalizedCorners[i]; // the corner itself (start of the outgoing leg)
  const B = finalizedCorners[i + 1]; // start of the leg after that (defines how far the outgoing leg runs)
  const filletStart = lerpPoint(A, C, 1 - FILLET_FRACTION);
  const filletEnd = lerpPoint(C, B, FILLET_FRACTION);

  const legFrom = lastDrawnPoint || { lon: A.lon, lat: A.lat };
  appendFinalized([legFrom.lon, legFrom.lat, filletStart.lon, filletStart.lat]);

  const arcPts = [filletStart.lon, filletStart.lat];
  for (let s = 1; s <= FILLET_STEPS; s++) {
    const t = s / FILLET_STEPS;
    const p = quadraticBezierPoint(filletStart, C, filletEnd, t);
    arcPts.push(p.lon, p.lat);
  }
  appendFinalized(arcPts);

  lastDrawnPoint = filletEnd;
}

function redrawLiveTail(lat, lon) {
  const from = lastDrawnPoint || (finalizedCorners.length ? finalizedCorners[0] : null);
  if (!from) return;
  const positions = Cesium.Cartesian3.fromDegreesArray([from.lon, from.lat, lon, lat]);
  if (liveTailEntity) {
    liveTailEntity.polyline.positions = positions;
  } else {
    liveTailEntity = viewer.entities.add({
      polyline: { positions, width: 6, material: glowMaterial(ROUTE_COLOR) },
    });
  }
}

function pushPoint(lat, lon, direction) {
  if (finalizedCorners.length === 0) {
    finalizedCorners.push({ lon, lat, direction });
  } else {
    const active = finalizedCorners[finalizedCorners.length - 1];
    if (direction !== active.direction) {
      finalizedCorners.push({ lon, lat, direction });
    }
    // else: still the same direction -- nothing new to compress into a
    // corner, the live tail below already reflects how far this run has grown.
  }
  const n = finalizedCorners.length;
  while (nextCornerToFinalize <= n - 2) {
    finalizeCorner(nextCornerToFinalize);
    nextCornerToFinalize++;
  }
  redrawLiveTail(lat, lon);
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

function updateCoordsText(lat, lon) {
  const el = document.getElementById('statCoords');
  if (el) el.textContent = `Lat ${lat.toFixed(3)}, Lon ${lon.toFixed(3)}`;
}

window.initJourney = function (data) {
  window.clearJourney();
  const [homeLat, homeLon] = data.home;
  const waypoints = data.waypoints || [];
  const firstDirection = waypoints.length > 0 ? waypoints[0].direction : null;
  finalizedCorners = [{ lon: homeLon, lat: homeLat, direction: firstDirection }];
  let last = { lat: homeLat, lon: homeLon, direction: firstDirection };
  waypoints.forEach((wp) => {
    const active = finalizedCorners[finalizedCorners.length - 1];
    if (wp.direction !== active.direction) {
      finalizedCorners.push({ lon: wp.lon, lat: wp.lat, direction: wp.direction });
    }
    last = wp;
  });
  nextCornerToFinalize = 1;
  const n = finalizedCorners.length;
  while (nextCornerToFinalize <= n - 2) {
    finalizeCorner(nextCornerToFinalize);
    nextCornerToFinalize++;
  }
  placeMarkers(last.lat, last.lon);
  redrawLiveTail(last.lat, last.lon);
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(last.lon, last.lat, 4000000),
  });
  updateCoordsText(last.lat, last.lon);
};

window.addWaypoint = function (lat, lon, direction) {
  pushPoint(lat, lon, direction);
};

window.updateCurrentPosition = function (lat, lon, direction) {
  if (!currentEntity) placeMarkers(lat, lon);
  currentEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat);
  if (arrowEntity) {
    arrowEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat);
    arrowEntity.label.text = DIRECTION_ARROWS[direction] || '';
  }
  updateCoordsText(lat, lon);
  redrawLiveTail(lat, lon);
};

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
  routePolylineEntity = null;
  routePositions = [];
  if (liveTailEntity) { viewer.entities.remove(liveTailEntity); liveTailEntity = null; }
  if (currentEntity) { viewer.entities.remove(currentEntity); currentEntity = null; }
  if (arrowEntity) { viewer.entities.remove(arrowEntity); arrowEntity = null; }
  finalizedCorners = [];
  nextCornerToFinalize = 1;
  lastDrawnPoint = null;
};

// ---- Replay support ----
window.replayReset = function (homeLat, homeLon) {
  window.clearJourney();
  finalizedCorners = [{ lon: homeLon, lat: homeLat, direction: null }];
  nextCornerToFinalize = 1;
  placeMarkers(homeLat, homeLon);
  updateCoordsText(homeLat, homeLon);
  viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(homeLon, homeLat, 4000000) });
};

window.replayStep = function (lat, lon, direction) {
  pushPoint(lat, lon, direction);
  window.updateCurrentPosition(lat, lon, direction);
};

// ---- "Guess the distance" mini-game support ----
// The actual Q&A happens in a Qt dialog; this side just hides the distance
// figure on the corner card while a guess is pending, so it isn't a
// trivial giveaway, and restores it once Python pushes fresh stats.
window.setDistanceHidden = function (hidden) {
  const d = document.getElementById('statDistance');
  if (d) d.textContent = hidden ? '❓ km' : d.textContent;
};

// ---- Idle auto-rotation: keeps the globe feeling alive when nobody is
// dragging it, without fighting the user's own camera control. ----
let lastInteraction = Date.now();
const IDLE_DELAY_MS = 3000;
const IDLE_ROTATE_RATE = 0.00025; // radians per frame, gentle spin

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

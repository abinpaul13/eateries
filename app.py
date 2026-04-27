"""Flask web frontend for the Eateries restaurant finder."""

import os

from flask import Flask, jsonify, render_template_string, request

from Eateries import find_restaurants, geocode

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Eateries — Find Nearby Restaurants</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
           margin: 0; background: #f6f7f9; color: #1d1f23; }
    header { background: #1f6feb; color: #fff; padding: 18px 24px; }
    header h1 { margin: 0; font-size: 22px; font-weight: 600; }
    header p { margin: 4px 0 0; opacity: .85; font-size: 14px; }
    main { max-width: 1100px; margin: 0 auto; padding: 24px; }
    form { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    form input[type=text] { flex: 1 1 320px; padding: 10px 12px; font-size: 15px;
           border: 1px solid #ccd1d9; border-radius: 6px; }
    form input[type=number] { width: 110px; padding: 10px 12px; font-size: 15px;
           border: 1px solid #ccd1d9; border-radius: 6px; }
    form button { padding: 10px 18px; font-size: 15px; background: #1f6feb; color: #fff;
           border: 0; border-radius: 6px; cursor: pointer; }
    form button:disabled { background: #9aaed4; cursor: wait; }
    #status { margin: 8px 0 16px; font-size: 14px; color: #555; min-height: 20px; }
    #status.error { color: #c0392b; }
    .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 800px) { .layout { grid-template-columns: 1fr; } }
    #map { height: 540px; border-radius: 8px; border: 1px solid #ddd; }
    #results { background: #fff; border: 1px solid #ddd; border-radius: 8px;
               max-height: 540px; overflow-y: auto; }
    .item { padding: 12px 14px; border-bottom: 1px solid #eee; cursor: pointer; }
    .item:hover { background: #f0f4fb; }
    .item.active { background: #e3edff; }
    .item h3 { margin: 0 0 4px; font-size: 15px; }
    .meta { font-size: 12px; color: #666; }
    .dist { float: right; font-weight: 600; color: #1f6feb; font-size: 13px; }
    .empty { padding: 24px; text-align: center; color: #888; }
  </style>
</head>
<body>
  <header>
    <h1>Eateries</h1>
    <p>Find restaurants near any address (data: OpenStreetMap)</p>
  </header>
  <main>
    <form id="searchForm">
      <input type="text" id="address" name="address"
             placeholder="Enter an address, e.g. 350 5th Ave, New York, NY" required>
      <input type="number" id="radius" name="radius" value="5" min="0.1" max="25" step="0.1" title="Radius (miles)">
      <button type="submit" id="submitBtn">Search</button>
    </form>
    <div id="status"></div>
    <div class="layout">
      <div id="map"></div>
      <div id="results"><div class="empty">Enter an address above to begin.</div></div>
    </div>
  </main>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const map = L.map('map').setView([39.5, -98.35], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    let markersLayer = L.layerGroup().addTo(map);
    let centerMarker = null;
    let radiusCircle = null;
    let markersByIndex = {};

    const form = document.getElementById('searchForm');
    const submitBtn = document.getElementById('submitBtn');
    const statusEl = document.getElementById('status');
    const resultsEl = document.getElementById('results');

    function setStatus(msg, isError = false) {
      statusEl.textContent = msg;
      statusEl.className = isError ? 'error' : '';
    }

    function clearMap() {
      markersLayer.clearLayers();
      if (centerMarker) { map.removeLayer(centerMarker); centerMarker = null; }
      if (radiusCircle) { map.removeLayer(radiusCircle); radiusCircle = null; }
      markersByIndex = {};
    }

    function highlight(idx) {
      document.querySelectorAll('.item').forEach(el => el.classList.remove('active'));
      const el = document.querySelector(`.item[data-idx="${idx}"]`);
      if (el) { el.classList.add('active'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
      const m = markersByIndex[idx];
      if (m) m.openPopup();
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const address = document.getElementById('address').value.trim();
      const radius = parseFloat(document.getElementById('radius').value) || 5;
      if (!address) return;

      submitBtn.disabled = true;
      setStatus('Searching… (geocoding + Overpass query, ~5–20s)');
      resultsEl.innerHTML = '<div class="empty">Loading…</div>';
      clearMap();

      try {
        const resp = await fetch(`/api/search?address=${encodeURIComponent(address)}&radius=${radius}`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);

        const { center, restaurants } = data;
        setStatus(`Found ${restaurants.length} result(s) within ${radius} mi of ${center.display}`);

        const radiusMeters = radius * 1609.344;
        centerMarker = L.marker([center.lat, center.lon], { title: 'Search center' })
          .addTo(map).bindPopup('<b>You searched here</b><br>' + center.display);
        radiusCircle = L.circle([center.lat, center.lon], {
          radius: radiusMeters, color: '#1f6feb', fillOpacity: 0.05
        }).addTo(map);
        map.fitBounds(radiusCircle.getBounds());

        if (!restaurants.length) {
          resultsEl.innerHTML = '<div class="empty">No restaurants found in this area.</div>';
          return;
        }

        const html = restaurants.map((r, i) => `
          <div class="item" data-idx="${i}">
            <span class="dist">${r.distance_miles.toFixed(2)} mi</span>
            <h3>${escapeHtml(r.name)}</h3>
            <div class="meta">
              ${escapeHtml(r.category)}${r.cuisine ? ' · ' + escapeHtml(r.cuisine) : ''}
            </div>
            ${r.address ? `<div class="meta">${escapeHtml(r.address)}</div>` : ''}
          </div>
        `).join('');
        resultsEl.innerHTML = html;

        restaurants.forEach((r, i) => {
          const m = L.marker([r.lat, r.lon]).addTo(markersLayer)
            .bindPopup(`<b>${escapeHtml(r.name)}</b><br>${r.distance_miles.toFixed(2)} mi away`
                       + (r.address ? '<br>' + escapeHtml(r.address) : ''));
          m.on('click', () => highlight(i));
          markersByIndex[i] = m;
        });

        document.querySelectorAll('.item').forEach(el => {
          el.addEventListener('click', () => {
            const idx = parseInt(el.dataset.idx, 10);
            highlight(idx);
            const r = restaurants[idx];
            map.setView([r.lat, r.lon], 16);
          });
        });
      } catch (err) {
        setStatus('Error: ' + err.message, true);
        resultsEl.innerHTML = '<div class="empty">Search failed.</div>';
      } finally {
        submitBtn.disabled = false;
      }
    });

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[c]));
    }
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/search")
def api_search():
    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify(error="address is required"), 400
    try:
        radius = float(request.args.get("radius", 5))
    except ValueError:
        return jsonify(error="radius must be a number"), 400
    radius = max(0.1, min(radius, 25))

    try:
        lat, lon, display = geocode(address)
        restaurants = find_restaurants(lat, lon, radius)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    except OSError as e:
        return jsonify(error=f"upstream service error: {e}"), 502

    return jsonify(
        center={"lat": lat, "lon": lon, "display": display},
        radius_miles=radius,
        restaurants=restaurants,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

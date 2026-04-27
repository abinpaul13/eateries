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
    form select { padding: 10px 12px; font-size: 15px; border: 1px solid #ccd1d9;
           border-radius: 6px; background: #fff; }
    form button { padding: 10px 18px; font-size: 15px; background: #1f6feb; color: #fff;
           border: 0; border-radius: 6px; cursor: pointer; }
    form button:disabled { background: #9aaed4; cursor: wait; }
    #filters { display: none; gap: 8px; flex-wrap: wrap; align-items: center;
               margin-bottom: 12px; font-size: 14px; color: #555; }
    #filters.visible { display: flex; }
    #status { margin: 8px 0 16px; font-size: 14px; color: #555; min-height: 20px; }
    #status.error { color: #c0392b; }
    .dish { font-size: 12px; color: #2a7a3a; margin-top: 2px; }
    .links { font-size: 12px; margin-top: 4px; }
    .links a { color: #1f6feb; text-decoration: none; margin-right: 12px; }
    .links a:hover { text-decoration: underline; }
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
    <div id="filters">
      <label for="cuisineFilter">Filter by cuisine:</label>
      <select id="cuisineFilter"><option value="">All</option></select>
      <span id="filterCount"></span>
    </div>
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
    let lastResults = [];
    let lastCity = '';

    const form = document.getElementById('searchForm');
    const submitBtn = document.getElementById('submitBtn');
    const statusEl = document.getElementById('status');
    const resultsEl = document.getElementById('results');
    const filtersEl = document.getElementById('filters');
    const cuisineFilterEl = document.getElementById('cuisineFilter');
    const filterCountEl = document.getElementById('filterCount');

    // Common dishes by cuisine — best-effort generic hints, not per-restaurant data.
    const DISHES = {
      italian: 'Pasta, pizza, risotto', pizza: 'Pizza, calzone',
      mexican: 'Tacos, burritos, enchiladas', chinese: 'Fried rice, dumplings, kung pao',
      japanese: 'Sushi, ramen, tempura', sushi: 'Sushi, sashimi, maki',
      ramen: 'Ramen, gyoza', indian: 'Curry, biryani, naan',
      thai: 'Pad thai, green curry, tom yum', vietnamese: 'Pho, banh mi, spring rolls',
      korean: 'Bibimbap, bulgogi, kimchi', american: 'Burgers, BBQ, sandwiches',
      burger: 'Burgers, fries, milkshakes', bbq: 'Ribs, brisket, pulled pork',
      barbecue: 'Ribs, brisket, pulled pork', steak_house: 'Steak, prime rib',
      seafood: 'Fish, lobster, oysters', french: 'Croissant, steak frites, ratatouille',
      greek: 'Gyros, souvlaki, moussaka', mediterranean: 'Hummus, falafel, kebab',
      lebanese: 'Hummus, falafel, shawarma', middle_eastern: 'Hummus, falafel, kebab',
      turkish: 'Kebab, baklava, pide', spanish: 'Paella, tapas, jamón',
      ethiopian: 'Injera, doro wat, kitfo', cafe: 'Coffee, sandwiches, pastries',
      coffee_shop: 'Coffee, pastries', bakery: 'Bread, pastries, cakes',
      ice_cream: 'Ice cream, sundaes', breakfast: 'Pancakes, eggs, bacon',
      sandwich: 'Sandwiches, subs', vegetarian: 'Salads, vegetable curries',
      vegan: 'Plant-based bowls, tofu', chicken: 'Fried chicken, wings',
      noodle: 'Noodles, broth bowls', asian: 'Stir-fry, noodles, rice bowls',
      pakistani: 'Biryani, kebabs, karahi', filipino: 'Adobo, lumpia, pancit',
      caribbean: 'Jerk chicken, rice & peas', donut: 'Donuts, coffee',
      dessert: 'Cakes, pastries, ice cream', tex-mex: 'Fajitas, nachos, quesadillas',
    };

    function dishesFor(cuisineTag) {
      if (!cuisineTag) return '';
      const parts = cuisineTag.toLowerCase().split(/[;,]/).map(s => s.trim());
      for (const p of parts) if (DISHES[p]) return DISHES[p];
      return '';
    }

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

        lastResults = restaurants;
        lastCity = (center.display.split(',')[1] || '').trim();
        populateCuisineFilter(restaurants);

        if (!restaurants.length) {
          resultsEl.innerHTML = '<div class="empty">No restaurants found in this area.</div>';
          filtersEl.classList.remove('visible');
          return;
        }
        filtersEl.classList.add('visible');
        renderResults();
      } catch (err) {
        setStatus('Error: ' + err.message, true);
        resultsEl.innerHTML = '<div class="empty">Search failed.</div>';
      } finally {
        submitBtn.disabled = false;
      }
    });

    function populateCuisineFilter(restaurants) {
      const counts = new Map();
      for (const r of restaurants) {
        if (!r.cuisine) continue;
        for (const c of r.cuisine.split(/[;,]/).map(s => s.trim()).filter(Boolean)) {
          counts.set(c, (counts.get(c) || 0) + 1);
        }
      }
      const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      cuisineFilterEl.innerHTML = `<option value="">All (${restaurants.length})</option>`
        + sorted.map(([c, n]) => `<option value="${escapeHtml(c)}">${escapeHtml(c)} (${n})</option>`).join('');
    }

    function renderResults() {
      const filter = cuisineFilterEl.value;
      const filtered = filter
        ? lastResults.filter(r => (r.cuisine || '').toLowerCase().split(/[;,]/).map(s => s.trim()).includes(filter.toLowerCase()))
        : lastResults;

      filterCountEl.textContent = filter ? `(${filtered.length} of ${lastResults.length})` : '';

      markersLayer.clearLayers();
      markersByIndex = {};

      if (!filtered.length) {
        resultsEl.innerHTML = '<div class="empty">No matches for this cuisine.</div>';
        return;
      }

      resultsEl.innerHTML = filtered.map((r, i) => {
        const dishes = dishesFor(r.cuisine);
        const q = encodeURIComponent(`${r.name} ${lastCity} popular dishes`.trim());
        return `
          <div class="item" data-idx="${i}">
            <span class="dist">${r.distance_miles.toFixed(2)} mi</span>
            <h3>${escapeHtml(r.name)}</h3>
            <div class="meta">${escapeHtml(r.category)}${r.cuisine ? ' · ' + escapeHtml(r.cuisine) : ''}</div>
            ${r.address ? `<div class="meta">${escapeHtml(r.address)}</div>` : ''}
            ${dishes ? `<div class="dish">Typical dishes: ${escapeHtml(dishes)}</div>` : ''}
            <div class="links">
              <a href="https://www.google.com/search?q=${q}" target="_blank" rel="noopener">Popular dishes ↗</a>
              <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name + ' ' + (r.address || ''))}" target="_blank" rel="noopener">Open in Maps ↗</a>
            </div>
          </div>
        `;
      }).join('');

      filtered.forEach((r, i) => {
        const m = L.marker([r.lat, r.lon]).addTo(markersLayer)
          .bindPopup(`<b>${escapeHtml(r.name)}</b><br>${r.distance_miles.toFixed(2)} mi away`
                     + (r.address ? '<br>' + escapeHtml(r.address) : ''));
        m.on('click', () => highlight(i));
        markersByIndex[i] = m;
      });

      document.querySelectorAll('.item').forEach(el => {
        el.addEventListener('click', (e) => {
          if (e.target.tagName === 'A') return;
          const idx = parseInt(el.dataset.idx, 10);
          highlight(idx);
          const r = filtered[idx];
          map.setView([r.lat, r.lon], 16);
        });
      });
    }

    cuisineFilterEl.addEventListener('change', renderResults);

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

// Dynamic Module: Scouted Intelligence & Vehicle Dossiers
import { formatLKR, switchTab } from '../app.js';
import { icon, liquidityIcon, starRow } from './icons.js';
import { escapeHtml } from './sanitize.js';

const TIER_BADGE_CLASS = {
  1: 'liquidity-tier-1',
  2: 'liquidity-tier-2',
  3: 'liquidity-tier-3',
  4: 'liquidity-tier-4',
};

export const DOSSIER_MODELS = {
  'aqua_2014': {
    name: 'Toyota Aqua (2014)',
    make: 'Toyota',
    model: 'Aqua',
    year: 2014,
    market_avg: 8125000,
    national_floor: 7280000,
    fuel_city: '19–23 km/l',
    fuel_highway: '26–30 km/l',
    fuel_rating: 5,
    fuel_label: 'Hybrid Flagship',
    reliability_rating: '4.8 / 5.0 · Top Sri Lankan Resale',
    turnover_tier: 1,
    turnover_velocity: 'Tier 1: Instant Cash (3–7 Days)',
    gotchas: [
      'ABS Actuator Accumulator: Listen for rapid pump buzzing every 5–10s when idle (~Rs. 110k to replace).',
      'Hybrid Battery: Check individual cell voltages via OBD2 Hybrid Assistant (keep delta < 0.2V).',
      'Trim Verification: S Grade vs G Grade (G Grade has soft-touch dash, push-start, cruise control).'
    ],
    target_buy_range: 'Rs. 7,150,000 – 7,350,000',
    target_resale_range: 'Rs. 7,650,000 – 7,850,000',
    est_net_profit: 'Rs. 450,000 – 550,000 (7.5% ROI)'
  },
  'celerio_2015': {
    name: 'Suzuki Celerio (2015)',
    make: 'Suzuki',
    model: 'Celerio',
    year: 2015,
    market_avg: 5366667,
    national_floor: 4975000,
    fuel_city: '16–18 km/l',
    fuel_highway: '22–25 km/l',
    fuel_rating: 5,
    fuel_label: 'Budget Fuel King',
    reliability_rating: '4.9 / 5.0 · Indestructible City Runabout',
    turnover_tier: 1,
    turnover_velocity: 'Tier 1: Instant Cash (3–5 Days)',
    gotchas: [
      'K10B Timing Chain: Bulletproof engine, inspect for noisy idler pulleys.',
      'AMT Gearbox (if Automatic): Test smooth low-speed creep and reverse gear engagement.',
      'AC Cooling Coil: Common dust buildup in Colombo traffic (~Rs. 15k clean).'
    ],
    target_buy_range: 'Rs. 4,950,000 – 5,050,000',
    target_resale_range: 'Rs. 5,300,000 – 5,350,000',
    est_net_profit: 'Rs. 280,000 – 330,000 (6.2% ROI)'
  },
  'swift_2010': {
    name: 'Suzuki Swift (2010)',
    make: 'Suzuki',
    model: 'Swift',
    year: 2010,
    market_avg: 4945000,
    national_floor: 4125000,
    fuel_city: '12–14 km/l',
    fuel_highway: '16–18 km/l',
    fuel_rating: 4,
    fuel_label: 'Enthusiast Hatch',
    reliability_rating: '4.7 / 5.0 · High Demand Japanese Shape',
    turnover_tier: 2,
    turnover_velocity: 'Tier 2: High Demand (7–10 Days)',
    gotchas: [
      'EPS Steering Rack: Check for clicking or rattle when turning full lock on rough roads.',
      'Lower Arm Bushes & Engine Mounts: Inspect front rubber bushings.',
      'Fuel Injector Cleaning: Carbon buildup common on 150k+ km units.'
    ],
    target_buy_range: 'Rs. 4,050,000 – 4,150,000',
    target_resale_range: 'Rs. 4,700,000 – 4,750,000',
    est_net_profit: 'Rs. 550,000 – 620,000 (13.5% ROI)'
  },
  'vitz_2011': {
    name: 'Toyota Vitz KSP90 (2011)',
    make: 'Toyota',
    model: 'Vitz',
    year: 2011,
    market_avg: 6100000,
    national_floor: 5500000,
    fuel_city: '13–15 km/l',
    fuel_highway: '18–20 km/l',
    fuel_rating: 5,
    fuel_label: 'Ultra-Reliable',
    reliability_rating: '5.0 / 5.0 · Gold Standard Resale',
    turnover_tier: 1,
    turnover_velocity: 'Tier 1: Instant Cash (3–7 Days)',
    gotchas: [
      'Engine Mount Vibration: 1KR-FE 3-cyl idle shudder at stops (cheap fix: rear mount ~Rs. 8,000).',
      'CVT Fluid Service History: Ensure fluid was replaced with genuine Toyota TC/FE.',
      'Water Pump & Thermostat: Check for pink coolant crusting around water pump pulley.'
    ],
    target_buy_range: 'Rs. 5,450,000 – 5,550,000',
    target_resale_range: 'Rs. 5,900,000 – 6,000,000',
    est_net_profit: 'Rs. 400,000 – 470,000 (8.1% ROI)'
  },
  'wagonr_2015': {
    name: 'Suzuki Wagon R Stingray (2015)',
    make: 'Suzuki',
    model: 'Wagon R',
    year: 2015,
    market_avg: 6450000,
    national_floor: 5850000,
    fuel_city: '18–21 km/l',
    fuel_highway: '24–27 km/l',
    fuel_rating: 5,
    fuel_label: 'Semi-Hybrid',
    reliability_rating: '4.8 / 5.0 · Highest Volume in SL',
    turnover_tier: 1,
    turnover_velocity: 'Tier 1: Instant Cash (3–7 Days)',
    gotchas: [
      'Auxiliary Lithium Battery: Under passenger seat; test charge hold via dashboard eco-meter.',
      'Radar Brake Support: Calibrate laser sensor on windshield if replaced.',
      'Front Strut Mounts: Inspect for squeaking over road bumps.'
    ],
    target_buy_range: 'Rs. 5,750,000 – 5,850,000',
    target_resale_range: 'Rs. 6,300,000 – 6,350,000',
    est_net_profit: 'Rs. 450,000 – 520,000 (8.8% ROI)'
  }
};

// Curated mechanic/fuel notes, indexed by normalized "make|model|year" so any live search
// result that happens to match one of the hand-authored profiles above still gets the
// real inspection notes attached — the market numbers themselves always come from the
// live database, never from these hardcoded figures (which is what caused the stale
// "10M+ for a 2011 Sorento" bug in the first place).
function curatedKey(make, model, year) {
  return `${make}|${model}|${year}`.toLowerCase().replace(/\s+/g, '');
}
const CURATED_BY_KEY = {};
Object.values(DOSSIER_MODELS).forEach(d => {
  CURATED_BY_KEY[curatedKey(d.make, d.model, d.year)] = d;
});

let currentSelectedData = null;
let modelListCache = null;
let searchBound = false;

// Pulls every (make, base_model, year) cohort with enough live ads to benchmark,
// sorted by inventory volume (already handled server-side) — this is the full
// searchable universe, not a fixed shortlist of 5 models.
async function ensureModelListLoaded() {
  if (modelListCache) return modelListCache;
  try {
    const res = await fetch('/api/market-trends?limit=500&offset=0');
    const json = await res.json();
    modelListCache = (json.items || []).filter(r => r.total_ads >= 2 && r.avg_price > 0);
  } catch (e) {
    modelListCache = [];
  }
  return modelListCache;
}

// Builds a full dossier data object from a live market-trends row. Numbers (market
// average, floor price, buy/resale targets, profit) are always computed from real
// listings; curated gotchas/fuel/reliability notes are attached on top when available.
function buildLiveDossierData(row) {
  const curated = CURATED_BY_KEY[curatedKey(row.make, row.model, row.year)];
  const marketAvg = row.avg_price;
  const nationalFloor = row.min_price;

  const buyLow = nationalFloor;
  const buyHigh = Math.round(nationalFloor * 1.02);
  const resaleLow = Math.round(marketAvg * 0.96);
  const resaleHigh = Math.round(marketAvg * 0.99);
  const refurb = 80000;
  const profitLow = Math.max(0, resaleLow - buyHigh - refurb);
  const profitHigh = Math.max(0, resaleHigh - buyLow - refurb);
  const roiPct = buyHigh > 0 ? ((profitLow / buyHigh) * 100).toFixed(1) : '0.0';
  const badgeToTier = { 'liquidity-tier-1': 1, 'liquidity-tier-2': 2, 'liquidity-tier-3': 3, 'liquidity-tier-4': 4 };

  return {
    name: `${row.make} ${row.model} (${row.year})`,
    make: row.make,
    model: row.model,
    year: row.year,
    market_avg: marketAvg,
    national_floor: nationalFloor,
    sample_size: row.total_ads,
    fuel_city: curated ? curated.fuel_city : 'Not yet catalogued',
    fuel_highway: curated ? curated.fuel_highway : '',
    fuel_rating: curated ? curated.fuel_rating : 3,
    fuel_label: curated ? curated.fuel_label : 'Uncatalogued',
    reliability_rating: curated ? curated.reliability_rating : 'No curated notes for this exact model/year yet — use the general checklist below.',
    turnover_tier: badgeToTier[row.liquidity_badge_class] || 4,
    turnover_velocity: `${row.liquidity_tier} (${row.liquidity_tag})`,
    gotchas: curated ? curated.gotchas : [
      'No model-specific mechanic notes catalogued yet for this exact year — run a full general pre-purchase inspection.',
      'Check full service history, and accident/flood damage history.',
      'Inspect rust in wheel wells, sills and boot floor, test suspension play, and check AC + electrical function.'
    ],
    target_buy_range: `${formatLKR(buyLow)} – ${formatLKR(buyHigh)}`,
    target_resale_range: `${formatLKR(resaleLow)} – ${formatLKR(resaleHigh)}`,
    est_net_profit: `${formatLKR(profitLow)} – ${formatLKR(profitHigh)} (${roiPct}% ROI)`
  };
}

function initDossierSearch() {
  if (searchBound) return;
  searchBound = true;
  const input = document.getElementById('dossierSearchInput');
  const results = document.getElementById('dossierSearchResults');
  if (!input || !results) return;

  const renderResults = async (q) => {
    const list = await ensureModelListLoaded();
    const query = q.trim().toLowerCase();
    const matches = query
      ? list.filter(r => `${r.make} ${r.model} ${r.year}`.toLowerCase().includes(query)).slice(0, 15)
      : list.slice(0, 15);

    results.innerHTML = matches.length === 0
      ? `<div class="dossier-search-empty">No indexed models match "${escapeHtml(q)}".</div>`
      : matches.map(r => `
        <div class="dossier-search-item" data-make="${escapeHtml(r.make)}" data-model="${escapeHtml(r.model)}" data-year="${r.year}">
          <span class="dossier-search-item-name">${escapeHtml(r.make)} ${escapeHtml(r.model)}<span class="dossier-search-item-year">${r.year}</span></span>
          <span class="dossier-search-item-meta">${formatLKR(r.avg_price)} · ${r.total_ads} ads</span>
        </div>
      `).join('');
    results.style.display = 'block';
  };

  input.addEventListener('focus', () => renderResults(input.value));
  input.addEventListener('input', () => renderResults(input.value));
  input.addEventListener('blur', () => {
    setTimeout(() => { results.style.display = 'none'; }, 150);
  });

  results.addEventListener('mousedown', (e) => {
    const item = e.target.closest('.dossier-search-item');
    if (!item) return;
    e.preventDefault();
    const make = item.dataset.make, model = item.dataset.model, year = parseInt(item.dataset.year, 10);
    const row = (modelListCache || []).find(r => r.make === make && r.model === model && r.year === year);
    if (!row) return;
    input.value = `${row.make} ${row.model} ${row.year}`;
    results.style.display = 'none';
    loadDossierTab(buildLiveDossierData(row));
  });
}

export async function loadDossierTab(selection = null) {
  initDossierSearch();
  if (selection) currentSelectedData = selection;
  if (!currentSelectedData) {
    currentSelectedData = DOSSIER_MODELS['aqua_2014'];
    const input = document.getElementById('dossierSearchInput');
    if (input) input.value = currentSelectedData.name;
  }
  const data = currentSelectedData;

  // Render Model Intelligence Specs Cards
  renderDossierSpecs(data);

  // Fetch live matching ads from database/API
  await fetchAndRenderDossierListings(data);
}

function renderDossierSpecs(data) {
  const container = document.getElementById('dossierModelSpecs');
  if (!container) return;

  container.innerHTML = `
    <div class="stat-card" style="grid-column: 1 / -1; border-color: var(--signal); background: var(--surface-card);">
      <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem;">
        <div>
          <span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--signal); font-weight: 700; text-transform: uppercase;">
            ${icon('target', { size: 12 })} Model Acquisition Dossier
          </span>
          <h2 style="font-size: 1.4rem; font-weight: 800; color: var(--ink); margin-top: 0.2rem;">
            ${data.name}
          </h2>
        </div>
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          <span class="badge-liquidity" style="font-size: 0.78rem; padding: 0.3rem 0.75rem;">
            ${liquidityIcon(TIER_BADGE_CLASS[data.turnover_tier])} ${data.turnover_velocity}
          </span>
          <span class="badge-deal good" style="font-size: 0.78rem; padding: 0.3rem 0.75rem; position: static;">
            ${starRow(data.fuel_rating, { size: 11 })} ${data.fuel_label}
          </span>
        </div>
      </div>

      <!-- Financial & Fuel Metrics Strip -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--border);">
        <div>
          <div class="stat-label">Market Benchmark Avg</div>
          <div class="stat-value" style="font-size: 1.2rem; color: var(--signal);">${formatLKR(data.market_avg)}</div>
        </div>
        <div>
          <div class="stat-label">National Floor Price</div>
          <div class="stat-value success" style="font-size: 1.2rem;">${formatLKR(data.national_floor)}</div>
        </div>
        <div>
          <div class="stat-label">Real Fuel Economy</div>
          <div style="font-family: var(--font-mono); font-size: 0.95rem; font-weight: 700; color: var(--ink); margin-top: 0.25rem; display: flex; align-items: center; gap: 0.4rem;">
            <span style="display:inline-flex; align-items:center; gap:0.25rem;">${icon('building', { size: 13 })} ${data.fuel_city}</span>
            <span style="color: var(--ink-tertiary);">·</span>
            <span style="display:inline-flex; align-items:center; gap:0.25rem;">${icon('route', { size: 13 })} ${data.fuel_highway}</span>
          </div>
        </div>
        <div>
          <div class="stat-label">Disciplined Flip Margin</div>
          <div class="stat-value success" style="font-size: 1.1rem;">
            ${data.est_net_profit}
          </div>
        </div>
      </div>

      <!-- Buy vs Resale Strategy Range -->
      <div style="margin-top: 1rem; padding: 0.85rem 1.1rem; background: var(--surface-subtle); border-radius: var(--radius-sm); border: 1px solid var(--border); display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.75rem; font-family: var(--font-mono); font-size: 0.8rem;">
        <div>
          <span style="color: var(--ink-secondary);">${icon('target', { size: 12 })} Target Buy Range:</span>
          <strong style="color: var(--success); margin-left: 0.3rem;">${data.target_buy_range}</strong>
        </div>
        <div>
          <span style="color: var(--ink-secondary);">${icon('zap', { size: 12 })} Conservative Fast Resale:</span>
          <strong style="color: var(--signal); margin-left: 0.3rem;">${data.target_resale_range}</strong>
        </div>
      </div>

      <!-- Sri Lankan Mechanic & Inspection Gotchas -->
      <div style="margin-top: 1rem;">
        <div class="stat-label" style="margin-bottom: 0.4rem; color: var(--danger); font-weight: 700; display: flex; align-items: center; gap: 0.3rem;">
          ${icon('alertTriangle', { size: 13 })} Sri Lankan Pre-Purchase Gotchas & Checklist:
        </div>
        <ul style="margin: 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.82rem; color: var(--ink-secondary);">
          ${data.gotchas.map(g => `<li>${g}</li>`).join('')}
        </ul>
      </div>
    </div>
  `;
}

async function fetchAndRenderDossierListings(data) {
  const grid = document.getElementById('dossierCarGrid');
  const countEl = document.getElementById('dossierListingsCount');
  if (!grid) return;

  grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p class="font-mono">Loading verified listings for ${data.name}...</p></div>`;

  try {
    const res = await fetch(`/api/cars?make=${encodeURIComponent(data.make)}&model=${encodeURIComponent(data.model)}&min_year=${data.year}&max_year=${data.year}&limit=50&sort_by=price_asc`);
    const json = await res.json();
    const items = json.items || [];

    if (countEl) countEl.innerText = `${items.length} live listings`;

    if (items.length === 0) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1/-1;">
          <p class="font-mono">No listings currently indexed for ${data.name}.</p>
          <button class="btn-primary" style="margin-top: 1rem;" onclick="window.openScrapeModal()">Fetch Market Ads for ${data.model}</button>
        </div>
      `;
      return;
    }

    grid.innerHTML = items.map((car, idx) => {
      const isFloor = idx === 0;
      const isColombo = (car.district || '').toLowerCase().includes('colombo') || (car.location || '').toLowerCase().includes('colombo');
      const isUnpriced = car.is_negotiable || car.price <= 0;

      const imageHtml = car.image_url
        ? `<img src="${escapeHtml(car.image_url)}" alt="${escapeHtml(car.title)}" class="car-img" onerror="this.outerHTML='<div class=\\'car-img-fallback\\'>NO PREVIEW</div>'">`
        : `<div class="car-img-fallback">NO PREVIEW</div>`;

      // Conservative buy/resale math
      const targetBuy = Math.round((car.price || data.market_avg) * 0.94);
      const estResale = Math.round(data.market_avg * 0.97);
      const estProfit = Math.max(0, estResale - (targetBuy + 45000));

      return `
        <div class="car-card ${isFloor ? 'hot-deal' : ''}">
          <div class="car-media">
            ${imageHtml}
            <span class="badge-source">${car.source === 'riyasewana' ? 'Riyasewana' : 'Ikman.lk'}</span>
            ${isFloor ? `<span class="badge-deal hot" style="top: 0.65rem; right: 0.65rem;">${icon('award', { size: 12 })} Absolute Floor</span>` : (isColombo ? `<span class="badge-deal good" style="top: 0.65rem; right: 0.65rem;">${icon('mapPin', { size: 12 })} Colombo Deal</span>` : '')}
          </div>

          <div class="car-card-body">
            <div>
              <h3 class="car-title" title="${escapeHtml(car.title)}">${escapeHtml(car.title)}</h3>
              <div class="car-meta-line" style="margin-top: 0.35rem;">
                <span>${escapeHtml(car.district || car.location || 'Sri Lanka')}</span>
                ${car.year ? `<span>· ${car.year}</span>` : ''}
                ${car.mileage_display ? `<span>· ${car.mileage_display}</span>` : ''}
              </div>
              <div style="margin-top: 0.35rem; display: flex; align-items: center; gap: 0.4rem;">
                <span class="badge-liquidity">${liquidityIcon(car.liquidity_badge_class)} ${car.liquidity_tag || '3–7d Turnover'}</span>
                <span style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-secondary);">${car.liquidity_tier || ''}</span>
              </div>
            </div>

            <div class="car-price-row">
              <div>
                <div class="car-price ${isUnpriced ? 'unpriced' : ''}">
                  ${isUnpriced ? 'Price on request' : (car.price_display || 'Price on request')}
                </div>
                <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-secondary); margin-top: 2px;">
                  Benchmark: ${formatLKR(data.market_avg)}
                </div>
              </div>
              <div style="text-align: right;">
                <span class="stat-label">Target Buy</span>
                <strong style="color: var(--success); font-family: var(--font-mono); font-size: 0.95rem;">${formatLKR(targetBuy)}</strong>
              </div>
            </div>

            <div class="flip-estimate-box">
              <span class="label">Est. Net Flip Profit (at ${formatLKR(estResale)})</span>
              <span class="value">+${formatLKR(estProfit)}</span>
            </div>

            <div class="car-actions">
              <a href="${escapeHtml(car.url)}" target="_blank" rel="noopener" class="btn-card-link">
                View Ad
                <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
              </a>
              <button class="btn-card-track" onclick="window.openPipelineModal(${car.id})">
                + Track Lead
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

  } catch (e) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Failed to load dossier listings: ${e.message}</p></div>`;
  }
}

// Kept for backward compatibility with any external caller still passing a curated
// DOSSIER_MODELS key (e.g. 'aqua_2014') instead of a live search selection.
export function selectDossierModel(modelKey) {
  const data = DOSSIER_MODELS[modelKey];
  if (data) loadDossierTab(data);
}

export function refreshDossierData() {
  loadDossierTab();
}

// Lanka Car Hunter · Main Application Controller

import { parseNaturalLanguageQuery, renderParsedChips } from './modules/nluSearch.js';
import { ScoutMascot } from './modules/mascot.js';

let currentCars = [];
let currentOffset = 0;
const pageLimit = 20;
let currentDealFilter = '';
let currentNLU = {};
let activeTab = 'deals';
let mascot = null;

// Lazy module loaders
let pipelineModule = null;
let marketModule = null;
let scraperModule = null;
let calcModule = null;
let dossierModule = null;

async function getPipelineModule() {
  if (!pipelineModule) pipelineModule = await import('./modules/pipeline.js');
  return pipelineModule;
}
async function getMarketModule() {
  if (!marketModule) marketModule = await import('./modules/marketTrends.js');
  return marketModule;
}
async function getScraperModule() {
  if (!scraperModule) scraperModule = await import('./modules/scraper.js');
  return scraperModule;
}
async function getCalcModule() {
  if (!calcModule) calcModule = await import('./modules/calculator.js');
  return calcModule;
}
async function getDossierModule() {
  if (!dossierModule) dossierModule = await import('./modules/dossier.js');
  return dossierModule;
}

// Global Currency Formatter
export function formatLKR(val) {
  if (!val || isNaN(val)) return 'Rs. 0';
  return 'Rs. ' + Math.round(val).toLocaleString('en-US');
}

export function parseFormattedNumber(str) {
  if (!str) return null;
  const cleaned = String(str).replace(/[^\d.]/g, '');
  const num = parseFloat(cleaned);
  return isNaN(num) ? null : num;
}

export function formatLiveNumberInput(input) {
  const cursor = input.selectionStart;
  const raw = input.value.replace(/[^\d]/g, '');
  if (!raw) {
    input.value = '';
    return;
  }
  const formatted = Number(raw).toLocaleString('en-US');
  input.value = formatted;
}
window.formatLiveNumberInput = formatLiveNumberInput;

// Tab Switcher
export async function switchTab(tabId) {
  activeTab = tabId;
  const tabDeals = document.getElementById('tabDeals');
  const tabPipeline = document.getElementById('tabPipeline');
  const tabMarket = document.getElementById('tabMarket');
  const tabDossier = document.getElementById('tabDossier');

  const viewDeals = document.getElementById('viewDeals');
  const viewPipeline = document.getElementById('viewPipeline');
  const viewMarket = document.getElementById('viewMarket');
  const dossierContent = document.getElementById('dossierTabContent');

  if (tabDeals) tabDeals.classList.toggle('active', tabId === 'deals');
  if (tabPipeline) tabPipeline.classList.toggle('active', tabId === 'pipeline');
  if (tabMarket) tabMarket.classList.toggle('active', tabId === 'market');
  if (tabDossier) tabDossier.classList.toggle('active', tabId === 'dossier');

  if (viewDeals) viewDeals.style.display = tabId === 'deals' ? 'block' : 'none';
  if (viewPipeline) viewPipeline.style.display = tabId === 'pipeline' ? 'block' : 'none';
  if (viewMarket) viewMarket.style.display = tabId === 'market' ? 'block' : 'none';
  if (dossierContent) dossierContent.style.display = tabId === 'dossier' ? 'flex' : 'none';

  if (mascot) {
    mascot.triggerState('inspecting', 1800);
  }

  if (tabId === 'pipeline') {
    const mod = await getPipelineModule();
    mod.loadPipeline();
  } else if (tabId === 'market') {
    const mod = await getMarketModule();
    mod.loadMarketTrends(0);
  } else if (tabId === 'dossier') {
    const mod = await getDossierModule();
    mod.loadDossierView();
  }
}
window.switchTab = switchTab;

// Load Stats
export async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('statTotalCars').innerText = data.total_cars.toLocaleString();
    document.getElementById('statHotDeals').innerText = data.hot_deals_count.toLocaleString();
    document.getElementById('statPotentialProfit').innerText = formatLKR(data.total_potential_profit);
    document.getElementById('statActiveLeads').innerText = data.active_leads.toLocaleString();

    if (data.active_leads > 0) {
      const badge = document.getElementById('pipelineCountBadge');
      if (badge) {
        badge.innerText = data.active_leads;
        badge.style.display = 'inline-block';
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') return;
    console.error('Error fetching stats:', e);
  }
}

// NLU Search Handlers
export function handleSearchInput(e) {
  const q = e.target.value;
  const clearBtn = document.getElementById('clearSearchBtn');
  if (clearBtn) {
    clearBtn.style.display = q ? 'block' : 'none';
  }
}

export function handleSearchKey(e) {
  if (e.key === 'Enter') {
    executeNLUSearch();
  }
}

export function clearSearchQuery() {
  const input = document.getElementById('filterQuery');
  if (input) input.value = '';
  const clearBtn = document.getElementById('clearSearchBtn');
  if (clearBtn) clearBtn.style.display = 'none';
  currentNLU = {};
  renderActiveNLUChips();
  loadCars(0);
}

export function executeNLUSearch() {
  if (mascot) mascot.triggerState('searching', 2500);

  const query = (document.getElementById('filterQuery')?.value || '').trim();
  if (query) {
    currentNLU = parseNaturalLanguageQuery(query);
    
    if (currentNLU.make) {
      const makeEl = document.getElementById('filterMake');
      if (makeEl) makeEl.value = currentNLU.make;
    }
    if (currentNLU.district) {
      const distEl = document.getElementById('filterDistrict');
      if (distEl) distEl.value = currentNLU.district;
    }
    if (currentNLU.min_price) {
      const minP = document.getElementById('filterMinPrice');
      if (minP) minP.value = Number(currentNLU.min_price).toLocaleString('en-US');
    }
    if (currentNLU.max_price) {
      const maxP = document.getElementById('filterMaxPrice');
      if (maxP) maxP.value = Number(currentNLU.max_price).toLocaleString('en-US');
    }
    if (currentNLU.deal_filter) {
      currentDealFilter = currentNLU.deal_filter;
      document.querySelectorAll('.val-pill').forEach(p => p.classList.remove('active'));
      const pillMap = { 'hot': 'pillHot', 'good': 'pillGood', 'negotiable': 'pillNeg' };
      const pillId = pillMap[currentNLU.deal_filter];
      if (pillId && document.getElementById(pillId)) {
        document.getElementById(pillId).classList.add('active');
      }
    }
  } else {
    currentNLU = {};
  }

  renderActiveNLUChips();
  loadCars(0);
}

export function renderActiveNLUChips() {
  const container = document.getElementById('nluChipsContainer');
  if (!container) return;

  const html = renderParsedChips(currentNLU);
  if (html) {
    container.innerHTML = html;
    container.style.display = 'flex';
  } else {
    container.innerHTML = '';
    container.style.display = 'none';
  }
}

export function removeNLUFilter(key) {
  if (key === 'make') {
    currentNLU.make = '';
    const el = document.getElementById('filterMake');
    if (el) el.value = '';
  } else if (key === 'model') {
    currentNLU.model = '';
  } else if (key === 'year' || key === 'year_range' || key === 'min_year') {
    currentNLU.year = null;
    currentNLU.min_year = null;
    currentNLU.max_year = null;
  } else if (key === 'price_range' || key === 'max_price' || key === 'min_price') {
    currentNLU.min_price = null;
    currentNLU.max_price = null;
    const minP = document.getElementById('filterMinPrice');
    if (minP) minP.value = '';
    const maxP = document.getElementById('filterMaxPrice');
    if (maxP) maxP.value = '';
  } else if (key === 'district') {
    currentNLU.district = '';
    const el = document.getElementById('filterDistrict');
    if (el) el.value = '';
  } else if (key === 'deal_filter') {
    currentNLU.deal_filter = '';
    currentDealFilter = '';
    document.querySelectorAll('.val-pill').forEach(p => p.classList.remove('active'));
    document.getElementById('pillAll')?.classList.add('active');
  }

  renderActiveNLUChips();
  loadCars(0);
}

export function toggleMobileFilters() {
  const drawer = document.getElementById('filtersDrawer');
  if (!drawer) return;
  drawer.classList.toggle('open');
}

window.executeNLUSearch = executeNLUSearch;
window.handleSearchInput = handleSearchInput;
window.handleSearchKey = handleSearchKey;
window.clearSearchQuery = clearSearchQuery;
window.removeNLUFilter = removeNLUFilter;
window.toggleMobileFilters = toggleMobileFilters;

// Build query params
export function getFilterParams(offset = 0) {
  const query = (document.getElementById('filterQuery')?.value || '').trim();
  const make = document.getElementById('filterMake')?.value || currentNLU.make;
  const district = document.getElementById('filterDistrict')?.value || currentNLU.district;
  const minPriceRaw = parseFormattedNumber(document.getElementById('filterMinPrice')?.value) || currentNLU.min_price;
  const maxPriceRaw = parseFormattedNumber(document.getElementById('filterMaxPrice')?.value) || currentNLU.max_price;
  const source = document.getElementById('filterSource')?.value;
  const sortBy = document.getElementById('sortBy')?.value || 'date_desc';

  const params = new URLSearchParams({
    limit: pageLimit,
    offset: offset,
    sort_by: sortBy
  });

  if (currentNLU.model) params.append('model', currentNLU.model);
  if (currentNLU.min_year) params.append('min_year', currentNLU.min_year);
  if (currentNLU.max_year) params.append('max_year', currentNLU.max_year);

  if (currentNLU.cleaned_query) {
    params.append('query', currentNLU.cleaned_query);
  } else if (query && !currentNLU.make && !currentNLU.model && !currentNLU.year) {
    params.append('query', query);
  }

  if (make) params.append('make', make);
  if (district) params.append('district', district);
  if (minPriceRaw > 0) params.append('min_price', minPriceRaw);
  if (maxPriceRaw > 0) params.append('max_price', maxPriceRaw);
  if (source) params.append('source', source);
  if (currentDealFilter) params.append('deal_filter', currentDealFilter);

  return params;
}

// Load Cars Feed
let currentFetchController = null;

export async function loadCars(offset = 0) {
  currentOffset = offset;
  const grid = document.getElementById('carGrid');
  if (!grid) return;

  if (currentFetchController) {
    currentFetchController.abort();
  }
  currentFetchController = new AbortController();
  grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p class="font-mono" style="font-size:0.85rem;">Retrieving active inventory...</p></div>`;

  try {
    const params = getFilterParams(offset);
    const res = await fetch(`/api/cars?${params.toString()}`, { signal: currentFetchController.signal });
    const data = await res.json();
    currentCars = data.items || [];

    document.getElementById('feedCount').innerText = `(${data.total.toLocaleString()} listings)`;
    
    const currentPage = Math.floor(offset / pageLimit) + 1;
    const totalPages = Math.ceil(data.total / pageLimit) || 1;
    document.getElementById('pageIndicator').innerText = `Page ${currentPage} of ${totalPages}`;
    document.getElementById('prevPageBtn').disabled = offset <= 0;
    document.getElementById('nextPageBtn').disabled = offset + pageLimit >= data.total;

    if (currentCars.length === 0) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1/-1;">
          <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--ink);">No listings match the current filters</h3>
          <p style="font-size: 0.85rem; color: var(--ink-secondary); max-width: 480px; margin-top: 0.25rem;">
            Try clearing criteria or click <strong>"Fetch Ads"</strong> to index fresh inventory.
          </p>
          <button class="btn-primary" style="margin-top: 0.75rem;" onclick="window.openScrapeModal()">Fetch Ads</button>
        </div>
      `;
      return;
    }

    // Check if hot deals are found and excite mascot
    const hasHotDeals = currentCars.some(c => c.valuation_rating === 'HOT_DEAL');
    if (hasHotDeals && mascot) {
      mascot.triggerState('excited', 3000);
    }

    grid.innerHTML = currentCars.map(c => renderCarCard(c)).join('');
  } catch (e) {
    if (e.name === 'AbortError') return;
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Failed to load listings: ${e.message}</p></div>`;
  }
}
window.loadCars = loadCars;

function renderCarCard(car) {
  const isHot = car.valuation_rating === 'HOT_DEAL';
  const isGood = car.valuation_rating === 'GOOD_DEAL';
  const isUnpriced = car.is_negotiable || car.price <= 0;

  let dealBadgeHtml = '';
  if (isHot) {
    dealBadgeHtml = `<span class="badge-deal hot">${car.deal_tag || 'HOT FLIP DEAL'}</span>`;
  } else if (isGood) {
    dealBadgeHtml = `<span class="badge-deal good">GOOD DEAL</span>`;
  } else if (isUnpriced) {
    dealBadgeHtml = `<span class="badge-deal unpriced">PRICE ON REQUEST</span>`;
  }

  const mediaHtml = car.image_url 
    ? `<img src="${car.image_url}" alt="${car.title}" class="car-img" loading="lazy" onerror="this.outerHTML='<div class=\\'car-img-fallback\\'>Image Unavailable</div>'">`
    : `<div class="car-img-fallback">No Preview Image</div>`;

  let priceHtml = '';
  if (isUnpriced) {
    priceHtml = `<span class="car-price unpriced">Negotiable</span>`;
  } else {
    priceHtml = `<span class="car-price">${formatLKR(car.price)}</span>`;
  }

  let flipBoxHtml = '';
  if (car.estimated_profit && car.estimated_profit > 0) {
    flipBoxHtml = `
      <div class="flip-estimate-box">
        <span class="label">Est. Net Profit:</span>
        <span class="value">+${formatLKR(car.estimated_profit)}</span>
      </div>
    `;
  }

  let liquidityBadge = '';
  if (car.liquidity_tier) {
    liquidityBadge = `<span class="badge-liquidity" title="${car.liquidity_days_est || ''}">⚡ ${car.liquidity_tier}</span>`;
  }

  return `
    <div class="car-card ${isHot ? 'hot-deal' : ''}">
      <div class="car-media">
        <span class="badge-source">${car.source.toUpperCase()}</span>
        ${dealBadgeHtml}
        ${mediaHtml}
      </div>
      <div class="car-card-body">
        <h3 class="car-title">${car.title}</h3>
        <div class="car-meta-line">
          ${car.year ? `<span>${car.year}</span> • ` : ''}
          ${car.mileage_km ? `<span>${car.mileage_km.toLocaleString()} km</span> • ` : ''}
          <span>${car.location || car.district || 'Sri Lanka'}</span>
        </div>
        ${liquidityBadge ? `<div style="margin-top: -0.25rem;">${liquidityBadge}</div>` : ''}
        ${flipBoxHtml}
        <div class="car-price-row">
          <div>
            <div style="font-size: 0.68rem; font-family: var(--font-mono); color: var(--ink-secondary);">ASKING PRICE</div>
            ${priceHtml}
          </div>
          ${car.market_avg_price ? `
            <div class="market-avg-info">
              <div>Market Avg: <strong>${formatLKR(car.market_avg_price)}</strong></div>
              ${car.discount_percentage ? `<div style="color: var(--success); font-weight: 700;">${car.discount_percentage}% below market</div>` : ''}
            </div>
          ` : ''}
        </div>
        <div class="car-actions">
          <a href="${car.url}" target="_blank" rel="noopener noreferrer" class="btn-card-link">
            <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
            View Ad
          </a>
          <button class="btn-card-track" onclick="window.openTrackPipelineModal(${car.id})">+ Track Lead</button>
        </div>
      </div>
    </div>
  `;
}

// Preset Filters
export function applyPreset(presetType, btn) {
  document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');

  const make = document.getElementById('filterMake');
  const district = document.getElementById('filterDistrict');
  const minP = document.getElementById('filterMinPrice');
  const maxP = document.getElementById('filterMaxPrice');
  const query = document.getElementById('filterQuery');

  if (make) make.value = '';
  if (district) district.value = '';
  if (minP) minP.value = '';
  if (maxP) maxP.value = '';
  if (query) query.value = '';
  currentDealFilter = '';
  currentNLU = {};
  renderActiveNLUChips();

  if (presetType === 'hot') {
    currentDealFilter = 'hot';
  } else if (presetType === 'alto') {
    if (make) make.value = 'Suzuki';
    if (query) query.value = 'Alto';
  } else if (presetType === 'wagonr') {
    if (make) make.value = 'Suzuki';
    if (query) query.value = 'Wagon R';
  } else if (presetType === 'vitz_aqua') {
    if (make) make.value = 'Toyota';
    if (query) query.value = 'Aqua';
  } else if (presetType === 'budget') {
    if (maxP) maxP.value = '3,500,000';
  } else if (presetType === 'colombo') {
    if (district) district.value = 'Colombo';
  }

  loadCars(0);
}
window.applyPreset = applyPreset;

export function setDealFilter(filterVal, btn) {
  document.querySelectorAll('.val-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  currentDealFilter = filterVal;
  loadCars(0);
}
window.setDealFilter = setDealFilter;

export function resetFilters() {
  document.getElementById('filterQuery').value = '';
  document.getElementById('filterMake').value = '';
  document.getElementById('filterDistrict').value = '';
  document.getElementById('filterMinPrice').value = '';
  document.getElementById('filterMaxPrice').value = '';
  document.getElementById('filterSource').value = '';
  currentDealFilter = '';
  currentNLU = {};
  renderActiveNLUChips();
  document.querySelectorAll('.val-pill').forEach(p => p.classList.remove('active'));
  document.getElementById('pillAll')?.classList.add('active');
  document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
  document.querySelector('.preset-chip')?.classList.add('active');
  loadCars(0);
}
window.resetFilters = resetFilters;

export function changePage(dir) {
  const newOffset = currentOffset + dir * pageLimit;
  if (newOffset >= 0) loadCars(newOffset);
}
window.changePage = changePage;

// Export CSV
export function exportData() {
  window.open('/api/export/csv', '_blank');
}
window.exportData = exportData;

// Modal Wrappers
window.openScrapeModal = async function() {
  const mod = await getScraperModule();
  mod.openScrapeModal();
};
window.closeScrapeModal = async function() {
  const mod = await getScraperModule();
  mod.closeScrapeModal();
};
window.openTrackPipelineModal = async function(carId) {
  const mod = await getPipelineModule();
  mod.openTrackPipelineModal(carId);
};
window.closePipelineModal = async function() {
  const mod = await getPipelineModule();
  mod.closePipelineModal();
};
window.openCalcModal = async function(carId) {
  const mod = await getCalcModule();
  mod.openCalcModal(carId);
};
window.closeCalcModal = async function() {
  const mod = await getCalcModule();
  mod.closeCalcModal();
};
window.changeMarketPage = async function(dir) {
  const mod = await getMarketModule();
  mod.changeMarketPage(dir);
};
window.selectDossierModel = async function(modelKey) {
  const mod = await getDossierModule();
  mod.selectDossierModel(modelKey);
};
window.refreshDossierData = async function() {
  const mod = await getDossierModule();
  mod.refreshDossierData();
};

// Global Window Bindings for Inline Handlers
window.loadCars = loadCars;
window.loadStats = loadStats;
window.switchTab = switchTab;
window.applyPreset = applyPreset;
window.setDealFilter = setDealFilter;
window.resetFilters = resetFilters;
window.changePage = changePage;
window.exportData = exportData;
window.executeNLUSearch = executeNLUSearch;
window.handleSearchInput = handleSearchInput;
window.handleSearchKey = handleSearchKey;
window.clearSearchQuery = clearSearchQuery;
window.removeNLUFilter = removeNLUFilter;
window.toggleMobileFilters = toggleMobileFilters;
window.formatLiveNumberInput = formatLiveNumberInput;

// Robust App Initialization
function initializeApp() {
  try {
    mascot = new ScoutMascot('mascotContainer');
  } catch (e) {
    console.warn('Mascot init fallback:', e);
  }
  loadStats();
  loadCars(0);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  initializeApp();
}

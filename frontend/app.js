// Lanka Car Hunter · Core Shell (Code-Split Dynamic Runtime < 8KB)

let currentOffset = 0;
export const pageLimit = 20;
let currentDealFilter = '';
let currentCars = [];

// Dynamic Module Cache
const modules = {
  pipeline: null,
  marketTrends: null,
  calculator: null,
  scraper: null
};

// Format Sri Lankan Rupees (JetBrains Mono output)
export function formatLKR(amount) {
  if (!amount || isNaN(amount) || amount <= 0) return 'Rs. 0';
  return 'Rs. ' + Math.round(amount).toLocaleString('en-LK');
}

// Parse any string with commas into a clean number
export function parseFormattedNumber(val) {
  if (typeof val === 'number') return val;
  if (!val) return 0;
  const clean = String(val).replace(/[^0-9.]/g, '');
  return parseFloat(clean) || 0;
}

// Live Number Input Formatter (Inserts commas every 3 digits while keeping cursor intact)
export function formatLiveNumberInput(inputEl) {
  if (!inputEl) return;
  const cursorPosition = inputEl.selectionStart;
  const originalLength = inputEl.value.length;
  
  // Strip all non-digits
  const rawDigits = inputEl.value.replace(/\D/g, '');
  if (!rawDigits) {
    inputEl.value = '';
    return;
  }
  
  const formatted = Number(rawDigits).toLocaleString('en-US');
  inputEl.value = formatted;
  
  // Restore cursor position smoothly
  const newLength = formatted.length;
  const delta = newLength - originalLength;
  const newPosition = Math.max(0, cursorPosition + delta);
  try {
    inputEl.setSelectionRange(newPosition, newPosition);
  } catch (e) {}
}

// Lazy Loaders for Feature Chunks
async function getPipelineModule() {
  if (!modules.pipeline) {
    modules.pipeline = await import('./modules/pipeline.js');
  }
  return modules.pipeline;
}

async function getMarketTrendsModule() {
  if (!modules.marketTrends) {
    modules.marketTrends = await import('./modules/marketTrends.js');
  }
  return modules.marketTrends;
}

async function getCalculatorModule() {
  if (!modules.calculator) {
    modules.calculator = await import('./modules/calculator.js');
  }
  return modules.calculator;
}

async function getScraperModule() {
  if (!modules.scraper) {
    modules.scraper = await import('./modules/scraper.js');
  }
  return modules.scraper;
}

async function getDossierModule() {
  if (!modules.dossier) {
    modules.dossier = await import('./modules/dossier.js');
  }
  return modules.dossier;
}

document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadCars(0);
});

// Navigation Tab Switcher (Loads View Chunks Lazily)
export async function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.view-section').forEach(v => v.style.display = 'none');
  const dossierContainer = document.getElementById('dossierTabContent');
  if (dossierContainer) dossierContainer.style.display = 'none';

  if (tab === 'deals') {
    document.getElementById('tabDeals').classList.add('active');
    document.getElementById('viewDeals').style.display = 'block';
    loadCars(currentOffset);
  } else if (tab === 'pipeline') {
    document.getElementById('tabPipeline').classList.add('active');
    document.getElementById('viewPipeline').style.display = 'block';
    const mod = await getPipelineModule();
    mod.loadPipeline();
  } else if (tab === 'market') {
    document.getElementById('tabMarket').classList.add('active');
    document.getElementById('viewMarket').style.display = 'block';
    const mod = await getMarketTrendsModule();
    mod.loadMarketTrends(0);
  } else if (tab === 'dossier') {
    document.getElementById('tabDossier').classList.add('active');
    if (dossierContainer) dossierContainer.style.display = 'flex';
    const mod = await getDossierModule();
    mod.loadDossierTab();
  }
}

window.selectDossierModel = async (key) => {
  const mod = await getDossierModule();
  mod.selectDossierModel(key);
};
window.refreshDossierData = async () => {
  const mod = await getDossierModule();
  mod.refreshDossierData();
};

// Load Top KPI Stats
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
      badge.innerText = data.active_leads;
      badge.style.display = 'inline-block';
    }
  } catch (e) {
    console.error('Error fetching stats:', e);
  }
}

import { parseNaturalLanguageQuery, renderParsedChips } from './modules/nluSearch.js';

let currentNLU = {};

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
  const query = (document.getElementById('filterQuery')?.value || '').trim();
  if (query) {
    currentNLU = parseNaturalLanguageQuery(query);
    
    // Sync dropdowns if NLU extracted them
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

  if (currentNLU.model) {
    params.append('model', currentNLU.model);
  }
  if (currentNLU.min_year) {
    params.append('min_year', currentNLU.min_year);
  }
  if (currentNLU.max_year) {
    params.append('max_year', currentNLU.max_year);
  }

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
export async function loadCars(offset = 0) {
  currentOffset = offset;
  const grid = document.getElementById('carGrid');
  grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p class="font-mono" style="font-size:0.85rem;">Retrieving active inventory...</p></div>`;

  try {
    const params = getFilterParams(offset);
    const res = await fetch(`/api/cars?${params.toString()}`);
    const data = await res.json();
    currentCars = data.items || [];

    document.getElementById('feedCount').innerText = `(${data.total.toLocaleString()} listings)`;
    
    // Pagination updates
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
            Try clearing specific criteria or click <strong>"Fetch Market Ads"</strong> to index fresh inventory from Riyasewana and Ikman.lk.
          </p>
          <button class="btn-primary" style="margin-top: 0.75rem;" onclick="window.openScrapeModal()">Fetch Market Ads</button>
        </div>
      `;
      return;
    }

    grid.innerHTML = currentCars.map(c => renderCarCard(c)).join('');
  } catch (e) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Failed to load listings: ${e.message}</p></div>`;
  }
}

// Render Individual Car Card
function renderCarCard(car) {
  const isHot = car.valuation_rating === 'HOT_DEAL';
  const isGood = car.valuation_rating === 'GOOD_DEAL';
  const isUnpriced = car.is_negotiable || car.price <= 0;

  let dealBadgeHtml = '';
  if (isHot) {
    dealBadgeHtml = `<span class="badge-deal hot">${car.deal_tag}</span>`;
  } else if (isGood) {
    dealBadgeHtml = `<span class="badge-deal good">${car.deal_tag}</span>`;
  } else if (isUnpriced) {
    dealBadgeHtml = `<span class="badge-deal unpriced">Price on request</span>`;
  }

  const imageHtml = car.image_url 
    ? `<img src="${car.image_url}" alt="${car.title}" class="car-img" onerror="this.outerHTML='<div class=\\'car-img-fallback\\'>NO PREVIEW AVAILABLE</div>'">`
    : `<div class="car-img-fallback">NO PREVIEW AVAILABLE</div>`;

  const profitStripHtml = (car.potential_profit_lkr && car.potential_profit_lkr > 0) ? `
    <div class="flip-estimate-box">
      <span class="label">Est. Gross Margin</span>
      <span class="value">+${formatLKR(car.potential_profit_lkr)}</span>
    </div>
  ` : '';

  const trackedStage = car.pipeline_stage;
  const stageLabels = {
    'saved': 'Saved',
    'to_call': 'Seller Contact',
    'inspecting': 'Inspection',
    'offered': 'Negotiation',
    'detailing': 'In Prep',
    'sold': 'Sold'
  };
  const trackBtnText = trackedStage ? `Stage: ${stageLabels[trackedStage] || trackedStage}` : `+ Track Record`;

  return `
    <div class="car-card ${isHot ? 'hot-deal' : ''}">
      <div class="car-media">
        ${imageHtml}
        <span class="badge-source">${car.source === 'riyasewana' ? 'Riyasewana' : 'Ikman.lk'}</span>
        ${dealBadgeHtml}
      </div>

      <div class="car-card-body">
        <div>
          <h3 class="car-title" title="${car.title}">${car.title}</h3>
          <div class="car-meta-line" style="margin-top: 0.35rem;">
            <span>${car.district || car.location || 'Sri Lanka'}</span>
            ${car.year ? `<span>· ${car.year}</span>` : ''}
            ${car.mileage_display ? `<span>· ${car.mileage_display}</span>` : ''}
          </div>
          ${car.liquidity_tag ? `
            <div style="margin-top: 0.35rem; display: flex; align-items: center; gap: 0.4rem;">
              <span class="badge-liquidity">${car.liquidity_tag}</span>
              <span style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-secondary);">${car.liquidity_tier || ''}</span>
            </div>
          ` : ''}
        </div>

        <div class="car-price-row">
          <div>
            <div class="car-price ${isUnpriced ? 'unpriced' : ''}">
              ${isUnpriced ? 'Price on request' : (car.price_display || 'Price on request')}
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-secondary); margin-top: 2px;">
              ${car.date_posted || 'Active ad'}
            </div>
          </div>
          ${car.market_avg_price > 0 ? `
            <div class="market-avg-info">
              Market Benchmark<br><strong>${formatLKR(car.market_avg_price)}</strong>
            </div>
          ` : ''}
        </div>

        ${profitStripHtml}

        <div class="car-card-actions">
          <button class="btn-card-calc" onclick="window.openCalcModal(${car.id})">
            Calculator
          </button>
          <button class="btn-card-track" onclick="window.openPipelineModal(${car.id})">
            ${trackBtnText}
          </button>
          <a href="${car.url}" target="_blank" rel="noopener" class="btn-card-link" title="Open source ad on ${car.source}">
            <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
          </a>
        </div>
      </div>
    </div>
  `;
}

// Window Bridge Functions for HTML Event Handlers
window.switchTab = switchTab;
window.loadCars = loadCars;
window.formatLiveNumberInput = formatLiveNumberInput;
window.parseFormattedNumber = parseFormattedNumber;

window.changePage = function(delta) {
  const newOffset = Math.max(0, currentOffset + (delta * pageLimit));
  loadCars(newOffset);
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

window.handleSearchKey = function(event) {
  if (event.key === 'Enter') {
    loadCars(0);
  }
};

window.resetFilters = function() {
  document.getElementById('filterQuery').value = '';
  document.getElementById('filterMake').value = '';
  document.getElementById('filterDistrict').value = '';
  document.getElementById('filterMinPrice').value = '';
  document.getElementById('filterMaxPrice').value = '';
  document.getElementById('filterSource').value = '';
  window.setDealFilter('', document.getElementById('pillAll'));
  document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
  loadCars(0);
};

window.setDealFilter = function(type, el) {
  currentDealFilter = type;
  document.querySelectorAll('.val-pill').forEach(p => p.classList.remove('active'));
  if (el) el.classList.add('active');
  loadCars(0);
};

window.applyPreset = function(preset, el) {
  document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
  if (el) el.classList.add('active');

  const queryEl = document.getElementById('filterQuery');
  const makeEl = document.getElementById('filterMake');
  const districtEl = document.getElementById('filterDistrict');
  const minPriceEl = document.getElementById('filterMinPrice');
  const maxPriceEl = document.getElementById('filterMaxPrice');

  queryEl.value = '';
  makeEl.value = '';
  districtEl.value = '';
  minPriceEl.value = '';
  maxPriceEl.value = '';
  currentDealFilter = '';

  if (preset === 'hot') {
    window.setDealFilter('hot', document.getElementById('pillHot'));
    return;
  } else if (preset === 'alto') {
    makeEl.value = 'Suzuki';
    queryEl.value = 'Alto';
  } else if (preset === 'wagonr') {
    makeEl.value = 'Suzuki';
    queryEl.value = 'Wagon R';
  } else if (preset === 'vitz_aqua') {
    makeEl.value = 'Toyota';
    queryEl.value = 'Vitz';
  } else if (preset === 'budget') {
    maxPriceEl.value = '3,500,000';
  } else if (preset === 'colombo') {
    districtEl.value = 'Colombo';
  }

  loadCars(0);
};

// Dynamic Calculator Bridges
window.openCalcModal = async function(carId) {
  const mod = await getCalculatorModule();
  mod.openCalcModal(carId, currentCars);
};

window.closeCalcModal = async function() {
  const mod = await getCalculatorModule();
  mod.closeCalcModal();
};

window.recomputeFlip = async function() {
  const mod = await getCalculatorModule();
  mod.recomputeFlip();
};

window.saveCalculatorToPipeline = async function() {
  const mod = await getCalculatorModule();
  mod.saveCalculatorToPipeline(() => {
    loadStats();
    if (document.getElementById('viewPipeline').style.display === 'block') {
      getPipelineModule().then(m => m.loadPipeline());
    }
  });
};

// Dynamic Pipeline Bridges
window.openPipelineModal = async function(carId) {
  const mod = await getPipelineModule();
  mod.openPipelineModal(carId, currentCars);
};

window.closePipelineModal = async function() {
  const mod = await getPipelineModule();
  mod.closePipelineModal();
};

window.submitPipelineUpdate = async function() {
  const mod = await getPipelineModule();
  mod.submitPipelineUpdate(() => {
    loadStats();
    loadCars(currentOffset);
    if (document.getElementById('viewPipeline').style.display === 'block') {
      mod.loadPipeline();
    }
  });
};

window.deleteLeadFromPipeline = async function() {
  const mod = await getPipelineModule();
  mod.deleteLeadFromPipeline(() => {
    loadStats();
    loadCars(currentOffset);
    if (document.getElementById('viewPipeline').style.display === 'block') {
      mod.loadPipeline();
    }
  });
};

// Dynamic Market Trends Bridges
window.changeMarketPage = async function(delta) {
  const mod = await getMarketTrendsModule();
  mod.changeMarketPage(delta);
};

window.searchSpecificModel = async function(make, model) {
  const mod = await getMarketTrendsModule();
  mod.searchSpecificModel(make, model);
};

// Dynamic Scraper Bridges
window.openScrapeModal = async function() {
  const mod = await getScraperModule();
  mod.openScrapeModal();
};

window.closeScrapeModal = async function() {
  const mod = await getScraperModule();
  mod.closeScrapeModal();
};

window.openEmptyScrapeModal = async function(msg) {
  const mod = await getScraperModule();
  mod.openEmptyScrapeModal(msg);
};

window.closeEmptyScrapeModal = async function() {
  const mod = await getScraperModule();
  mod.closeEmptyScrapeModal();
};

window.startScrapeJob = async function() {
  const mod = await getScraperModule();
  mod.startScrapeJob(() => {
    loadStats();
    loadCars(0);
    if (document.getElementById('viewMarket').style.display === 'block') {
      getMarketTrendsModule().then(m => m.loadMarketTrends(0));
    }
  });
};

window.exportData = function() {
  const params = getFilterParams(0);
  window.location.href = `/api/export?${params.toString()}`;
};

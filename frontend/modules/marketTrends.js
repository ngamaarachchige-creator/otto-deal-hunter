// Dynamic Module: Market Trends & Valuation Index
import { formatLKR, switchTab, loadCars } from '../app.js';

let currentMarketOffset = 0;
const marketLimit = 20;

export async function loadMarketTrends(offset = 0) {
  currentMarketOffset = offset;
  const tbody = document.getElementById('marketTableBody');
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="7" class="font-mono" style="text-align:center; padding: 2rem; color: var(--ink-secondary);">Analyzing market database benchmarks...</td></tr>`;
  }

  try {
    const res = await fetch(`/api/market-trends?limit=${marketLimit}&offset=${offset}`);
    const data = await res.json();
    const trends = data.items || (Array.isArray(data) ? data : []);
    const total = data.total || trends.length;

    const currentPage = Math.floor(offset / marketLimit) + 1;
    const totalPages = Math.ceil(total / marketLimit) || 1;
    
    const ind = document.getElementById('marketPageIndicator');
    if (ind) ind.innerText = `Page ${currentPage} of ${totalPages} (${total} models)`;
    const prevBtn = document.getElementById('prevMarketBtn');
    if (prevBtn) prevBtn.disabled = offset <= 0;
    const nextBtn = document.getElementById('nextMarketBtn');
    if (nextBtn) nextBtn.disabled = offset + marketLimit >= total;

    if (!tbody) return;

    if (trends.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--ink-secondary);">No sufficient pricing benchmarks yet. Fetch active listings to populate.</td></tr>`;
      return;
    }

    tbody.innerHTML = trends.map(t => `
      <tr>
        <td><strong>${t.make} ${t.model}</strong></td>
        <td class="font-mono">${t.avg_year || 'N/A'}</td>
        <td class="font-mono" style="font-weight: 700; color: var(--signal);">${formatLKR(t.avg_price)}</td>
        <td class="font-mono" style="color: var(--success);">${formatLKR(t.min_price)}</td>
        <td>
          <span class="badge-liquidity">${t.liquidity_tag || '⚡ 3–7d Turnover'}</span>
          <div class="font-mono" style="font-size:0.68rem; color:var(--ink-secondary); margin-top:2px;">${t.liquidity_tier || ''}</div>
        </td>
        <td class="font-mono">${t.total_ads} ads</td>
        <td>
          <button class="btn-secondary" style="padding:0.3rem 0.65rem; font-size:0.75rem;" onclick="window.searchSpecificModel('${t.make}', '${t.model}')">
            View Inventory
          </button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color: var(--danger);">Failed to load market benchmarks.</td></tr>`;
  }
}

export function changeMarketPage(delta) {
  const newOffset = Math.max(0, currentMarketOffset + (delta * marketLimit));
  loadMarketTrends(newOffset);
}

export function searchSpecificModel(make, model) {
  switchTab('deals');
  document.getElementById('filterMake').value = make;
  document.getElementById('filterQuery').value = model;
  loadCars(0);
}

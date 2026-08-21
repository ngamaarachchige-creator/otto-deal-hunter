// Dynamic Module: Flip Detailing & Repair Calculator
import { formatLKR, parseFormattedNumber } from '../app.js';
import { escapeHtml } from './sanitize.js';

let activeCalcCar = null;

export function openCalcModal(carId, currentCars) {
  const car = currentCars.find(c => c.id === carId);
  if (!car) return;
  activeCalcCar = car;

  const isUnpriced = car.is_negotiable || car.price <= 0;
  const suggestedBuy = car.price > 0 ? car.price : (car.market_avg_price ? Math.round(car.market_avg_price * 0.8) : '');
  const suggestedResale = car.market_avg_price > 0 ? Math.round(car.market_avg_price * 0.97) : (car.price > 0 ? Math.round(car.price * 1.15) : '');

  document.getElementById('calcCarSummary').innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <div>
        <strong style="font-size:0.95rem; color:var(--ink);">${escapeHtml(car.title)}</strong>
        <div class="font-mono" style="color:var(--ink-secondary); font-size:0.75rem; margin-top:2px;">
          ${escapeHtml(car.district || car.location)} · Year: ${car.year || 'N/A'} · Stated: ${isUnpriced ? 'Price on request' : escapeHtml(car.price_display)}
        </div>
      </div>
      <span class="badge-source" style="position:static;">${escapeHtml(car.source)}</span>
    </div>
  `;

  document.getElementById('calcBuyPrice').value = suggestedBuy ? Number(suggestedBuy).toLocaleString('en-US') : '';
  document.getElementById('calcResalePrice').value = suggestedResale ? Number(suggestedResale).toLocaleString('en-US') : '';
  document.getElementById('calcDetailingCost').value = Number(35000).toLocaleString('en-US');
  document.getElementById('calcRepairCost').value = Number(45000).toLocaleString('en-US');
  document.getElementById('calcFeeCost').value = Number(15000).toLocaleString('en-US');

  recomputeFlip();
  document.getElementById('calcModal').classList.add('active');
}

export function closeCalcModal() {
  document.getElementById('calcModal').classList.remove('active');
}

export function recomputeFlip() {
  const buy = parseFormattedNumber(document.getElementById('calcBuyPrice').value);
  const resale = parseFormattedNumber(document.getElementById('calcResalePrice').value);
  const detailing = parseFormattedNumber(document.getElementById('calcDetailingCost').value);
  const repair = parseFormattedNumber(document.getElementById('calcRepairCost').value);
  const fee = parseFormattedNumber(document.getElementById('calcFeeCost').value);

  const totalInvestment = buy + detailing + repair + fee;
  const netProfit = resale - totalInvestment;
  const roi = totalInvestment > 0 ? ((netProfit / totalInvestment) * 100) : 0;

  document.getElementById('calcTotalInvestment').value = formatLKR(totalInvestment);
  
  const profitEl = document.getElementById('calcNetProfit');
  profitEl.innerText = formatLKR(netProfit);
  if (netProfit >= 0) {
    profitEl.style.color = 'var(--success)';
  } else {
    profitEl.style.color = 'var(--danger)';
  }

  const roiBadge = document.getElementById('calcRoiBadge');
  roiBadge.innerText = `${roi.toFixed(1)}% ROI`;
  roiBadge.style.color = roi >= 10 ? 'var(--success)' : roi > 0 ? 'var(--signal)' : 'var(--danger)';
}

export async function saveCalculatorToPipeline(refreshCallback) {
  if (!activeCalcCar) return;
  const buy = parseFormattedNumber(document.getElementById('calcBuyPrice').value);
  const resale = parseFormattedNumber(document.getElementById('calcResalePrice').value);
  const repair = parseFormattedNumber(document.getElementById('calcDetailingCost').value) + parseFormattedNumber(document.getElementById('calcRepairCost').value);

  try {
    await fetch(`/api/pipeline/${activeCalcCar.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stage: 'saved',
        purchase_price: buy,
        estimated_repair_cost: repair,
        target_resale_price: resale,
        notes: `Prep & Flip Plan: Buy ${formatLKR(buy)}, Prep ${formatLKR(repair)}, Target Resale ${formatLKR(resale)}`
      })
    });
    closeCalcModal();
    if (refreshCallback) refreshCallback();
    alert(`Vehicle saved to your Flip Pipeline.`);
  } catch (e) {
    alert('Error saving record: ' + e.message);
  }
}

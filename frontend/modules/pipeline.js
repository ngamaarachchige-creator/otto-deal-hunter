// Dynamic Module: Acquisition Pipeline Kanban Board
import { formatLKR, parseFormattedNumber } from '../app.js';
import { escapeHtml } from './sanitize.js';

export async function loadPipeline() {
  const stages = ['saved', 'to_call', 'inspecting', 'offered', 'detailing', 'sold'];
  stages.forEach(s => {
    const col = document.getElementById(`stage_${s}`);
    if (col) col.innerHTML = `<div class="font-mono" style="font-size:0.75rem; color:var(--ink-secondary); text-align:center; padding: 1rem;">Loading...</div>`;
    const badge = document.getElementById(`count_${s}`);
    if (badge) badge.innerText = '0';
  });

  try {
    const res = await fetch('/api/pipeline?limit=100');
    const data = await res.json();
    const leads = data.items || (Array.isArray(data) ? data : []);

    const grouped = {};
    stages.forEach(s => grouped[s] = []);
    leads.forEach(l => {
      const stage = l.stage || 'saved';
      if (grouped[stage]) grouped[stage].push(l);
    });

    stages.forEach(s => {
      const items = grouped[s];
      const badge = document.getElementById(`count_${s}`);
      if (badge) badge.innerText = items.length;

      const col = document.getElementById(`stage_${s}`);
      if (!col) return;

      if (items.length === 0) {
        col.innerHTML = `
          <div style="font-family: var(--font-mono); font-size:0.75rem; color:var(--ink-tertiary); text-align:center; padding: 2rem 0.5rem; border: 1px dashed var(--border); border-radius: 8px;">
            No records
          </div>
        `;
      } else {
        col.innerHTML = items.map(l => `
          <div class="pipeline-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.4rem;">
              <strong style="font-size:0.85rem; line-height:1.3; color:var(--ink);">${escapeHtml(l.title)}</strong>
              <span class="badge-source" style="position:static; font-size:0.65rem; padding:0.15rem 0.35rem;">${escapeHtml(l.source)}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-family:var(--font-mono); font-size:0.78rem; color:var(--ink-secondary);">
              <span>${l.price > 0 ? formatLKR(l.price) : 'Price on request'}</span>
              <span>${escapeHtml(l.district || l.location || 'Sri Lanka')}</span>
            </div>
            ${l.seller_phone ? `<div class="font-mono" style="font-size:0.75rem; color:var(--signal); font-weight:600;">Tel: ${escapeHtml(l.seller_phone)} ${l.seller_name ? `(${escapeHtml(l.seller_name)})` : ''}</div>` : ''}
            ${l.pipeline_notes ? `<div style="font-size:0.75rem; color:var(--ink-secondary); background:var(--surface-subtle); padding:0.4rem; border-radius:4px; border:1px solid var(--border);">Note: ${escapeHtml(l.pipeline_notes)}</div>` : ''}
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.25rem; padding-top:0.35rem; border-top:1px solid var(--border);">
              <button class="btn-card-calc" style="padding:0.3rem 0.5rem; font-size:0.72rem;" onclick="window.openCalcModal(${l.id})">Calculator</button>
              <button class="btn-card-track" style="padding:0.3rem 0.5rem; font-size:0.72rem;" onclick="window.openPipelineModal(${l.id})">Edit</button>
              <a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" class="btn-card-link" style="padding:0.3rem 0.45rem; font-size:0.72rem;">↗</a>
            </div>
          </div>
        `).join('');
      }
    });
  } catch (e) {
    console.error('Error loading pipeline:', e);
  }
}

export function openPipelineModal(carId, currentCars) {
  const car = currentCars.find(c => c.id === carId);
  if (!car) return;

  document.getElementById('pipeCarId').value = car.id;
  document.getElementById('pipeStage').value = car.pipeline_stage || 'to_call';
  document.getElementById('pipePhone').value = car.seller_phone || '';
  document.getElementById('pipePurchasePrice').value = car.price > 0 ? Number(car.price).toLocaleString('en-US') : '';
  document.getElementById('pipeRepairCost').value = car.estimated_repair_cost ? Number(car.estimated_repair_cost).toLocaleString('en-US') : '50,000';
  document.getElementById('pipeNotes').value = car.pipeline_notes || '';

  document.getElementById('pipelineModal').classList.add('active');
}

export function closePipelineModal() {
  document.getElementById('pipelineModal').classList.remove('active');
}

export async function submitPipelineUpdate(refreshCallback) {
  const carId = document.getElementById('pipeCarId').value;
  const stage = document.getElementById('pipeStage').value;
  const phone = document.getElementById('pipePhone').value;
  const sellerName = document.getElementById('pipeSellerName').value;
  const purchasePrice = parseFormattedNumber(document.getElementById('pipePurchasePrice').value);
  const repairCost = parseFormattedNumber(document.getElementById('pipeRepairCost').value);
  const notes = document.getElementById('pipeNotes').value;

  try {
    await fetch(`/api/pipeline/${carId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stage: stage,
        seller_phone: phone,
        seller_name: sellerName,
        purchase_price: purchasePrice,
        estimated_repair_cost: repairCost,
        notes: notes
      })
    });
    closePipelineModal();
    if (refreshCallback) refreshCallback();
  } catch (e) {
    alert('Error updating record: ' + e.message);
  }
}

export async function deleteLeadFromPipeline(refreshCallback) {
  const carId = document.getElementById('pipeCarId').value;
  if (!confirm('Remove this vehicle from the acquisition pipeline?')) return;
  try {
    await fetch(`/api/pipeline/${carId}`, { method: 'DELETE' });
    closePipelineModal();
    if (refreshCallback) refreshCallback();
  } catch (e) {
    alert('Error deleting record: ' + e.message);
  }
}

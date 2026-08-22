// OTTO Copilot · Autonomous Vehicle Acquisition Agent & Slide-Over Panel
import { icon } from './icons.js';
import { escapeHtml } from './sanitize.js';
import { formatLKR } from '../app.js';

let isCopilotOpen = false;
let isProcessing = false;
let currentAbortController = null;
let chatHistory = [];

// Rotating "thinking" words while OTTO works — swaps to "Scraping" once a
// real scrape job is confirmed running (via the scrape-logs poll), rather
// than guessing intent from the user's message text.
const THINKING_WORDS = [
  'Scouting', 'Sniffing', 'Appraising', 'Benchmarking', 'Snooping', 'Prowling',
  'Sleuthing', 'Combing', 'Canvassing', 'Sizing up', 'Vetting', 'Cross-checking',
  'Triangulating', 'Squinting', 'Haggling', 'Valuing', 'Weighing', 'Digging',
  'Casing', 'Surveying', 'Scoping', 'Eyeballing', 'Sussing out', 'Verifying', 'Pricing',
];

function startThinkingRotation(labelEl) {
  if (!labelEl) return null;
  let i = 0;
  let timeoutId = null;
  const tick = () => {
    labelEl.textContent = THINKING_WORDS[i] + '…';
    i = (i + 1) % THINKING_WORDS.length;
    const delay = 2600 + Math.random() * 400; // 2.6–3s, randomized so it doesn't feel mechanical
    timeoutId = setTimeout(tick, delay);
  };
  tick();
  return { stop: () => clearTimeout(timeoutId) };
}

export function initCopilot() {
  const trigger = document.getElementById('ottoCopilotTrigger');
  const closeBtn = document.getElementById('ottoCopilotClose');
  const form = document.getElementById('ottoCopilotForm');
  const input = document.getElementById('ottoCopilotInput');

  if (trigger) {
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleCopilot();
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', closeCopilot);
  }



  if (form && input) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (isProcessing) {
        stopGeneration();
        return;
      }
      const msg = input.value.trim();
      if (!msg) return;
      input.value = '';
      sendCopilotMessage(msg);
    });
  }

  // Bind prompt chips
  document.querySelectorAll('.copilot-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt') || chip.innerText.trim();
      if (prompt && !isProcessing) {
        sendCopilotMessage(prompt);
      }
    });
  });

  // Initial check on load
  checkOllamaStatus();
}

export function toggleCopilot() {
  if (isCopilotOpen) {
    closeCopilot();
  } else {
    openCopilot();
  }
}

export async function checkOllamaStatus() {
  const dot = document.getElementById('ottoCopilotStatusDot');
  const triggerDot = document.getElementById('ottoCopilotTriggerDot');
  const subtitle = document.getElementById('ottoCopilotSubtitle');
  if (!dot || !subtitle) return;
  try {
    const res = await fetch('/api/copilot/status');
    const data = await res.json();
    if (data.active) {
      dot.style.backgroundColor = '#10b981';
      if (triggerDot) triggerDot.style.backgroundColor = '#10b981';
      subtitle.innerHTML = `<span class="status-dot" id="ottoCopilotStatusDot" style="background: #10b981;"></span> ${data.model} (LAN Active)`;
    } else {
      dot.style.backgroundColor = '#ef4444';
      if (triggerDot) triggerDot.style.backgroundColor = '#ef4444';
      subtitle.innerHTML = `<span class="status-dot" id="ottoCopilotStatusDot" style="background: #ef4444;"></span> ${data.model} (LAN Offline)`;
    }
  } catch (e) {
    dot.style.backgroundColor = '#ef4444';
    if (triggerDot) triggerDot.style.backgroundColor = '#ef4444';
    subtitle.innerHTML = `<span class="status-dot" id="ottoCopilotStatusDot" style="background: #ef4444;"></span> qwen3-vl:8b (LAN Offline)`;
  }
}

export function openCopilot() {
  const panel = document.getElementById('ottoCopilotPanel');
  const trigger = document.getElementById('ottoCopilotTrigger');
  if (!panel) return;
  panel.classList.add('active');
  trigger?.classList.add('hidden');
  isCopilotOpen = true;
  document.getElementById('ottoCopilotInput')?.focus();
  checkOllamaStatus();
}

export function closeCopilot() {
  const panel = document.getElementById('ottoCopilotPanel');
  const trigger = document.getElementById('ottoCopilotTrigger');
  if (!panel) return;
  panel.classList.remove('active');
  trigger?.classList.remove('hidden');
  isCopilotOpen = false;
}

export function stopGeneration() {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }
  setProcessingState(false);
}

function setProcessingState(processing) {
  isProcessing = processing;
  const submitBtn = document.getElementById('ottoCopilotSubmit');
  if (!submitBtn) return;

  if (processing) {
    submitBtn.classList.add('stop-mode');
    submitBtn.title = 'Stop Generating';
    submitBtn.innerHTML = `
      <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24">
        <rect x="5" y="5" width="14" height="14" rx="2" />
      </svg>
    `;
  } else {
    submitBtn.classList.remove('stop-mode');
    submitBtn.title = 'Send Message';
    submitBtn.innerHTML = `
      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"/>
      </svg>
    `;
  }
}

export function editPrompt(userText, msgElementId) {
  const input = document.getElementById('ottoCopilotInput');
  if (input) {
    input.value = userText;
    input.focus();
  }
  // Pop from chatHistory
  const idx = chatHistory.findIndex(h => h.role === 'user' && h.content === userText);
  if (idx !== -1) {
    chatHistory = chatHistory.slice(0, idx);
  }
  const userEl = document.getElementById(msgElementId);
  if (userEl) {
    const nextEl = userEl.nextElementSibling;
    if (nextEl && nextEl.classList.contains('agent-msg')) {
      nextEl.remove();
    }
    userEl.remove();
  }
}

export function copyResponseText(btn, textToCopy) {
  navigator.clipboard.writeText(textToCopy).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✓ Copied';
    setTimeout(() => { btn.innerHTML = orig; }, 1800);
  }).catch(() => {});
}

export async function sendCopilotMessage(userText) {
  const feed = document.getElementById('ottoCopilotFeed');
  if (!feed) return;

  setProcessingState(true);
  currentAbortController = new AbortController();

  const userMsgId = 'user_msg_' + Date.now();
  const agentMsgId = 'agent_msg_' + Date.now();

  // 1. Append User Message
  const userMsgEl = document.createElement('div');
  userMsgEl.className = 'copilot-msg user-msg';
  userMsgEl.id = userMsgId;
  userMsgEl.innerHTML = `
    <div class="user-msg-actions">
      <button class="msg-action-btn" title="Edit Prompt" onclick="window.editCopilotPrompt('${escapeHtml(userText.replace(/'/g, "\\'"))}', '${userMsgId}')">
        <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-5m-1.414-9.414a2 2 0 1 1 2.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
      </button>
    </div>
    <div class="msg-bubble">${escapeHtml(userText)}</div>
  `;
  feed.appendChild(userMsgEl);
  feed.scrollTop = feed.scrollHeight;

  // 2. Append Agent Response Container with Run Log
  const agentMsgEl = document.createElement('div');
  agentMsgEl.className = 'copilot-msg agent-msg';
  agentMsgEl.id = agentMsgId;
  agentMsgEl.innerHTML = `
    <div class="agent-avatar">
      <img src="/static/assets/bloub-cercle-attentif-encre-anime_circle.svg" alt="OTTO" width="28" height="28">
    </div>
    <div class="agent-body" id="${agentMsgId}_body">
      <div class="agent-run-log">
        <div class="run-step active"><span class="step-dot"></span> <span id="${agentMsgId}_thinking_label"></span></div>
      </div>
      <div class="copilot-live-terminal-wrap" id="${agentMsgId}_terminal_wrap" style="display: none;">
        <div class="copilot-terminal-header">
          <span>Live Scrape Progress Logs</span>
        </div>
        <div class="copilot-terminal-body font-mono" id="${agentMsgId}_terminal_body"></div>
      </div>
    </div>
  `;
  feed.appendChild(agentMsgEl);
  feed.scrollTop = feed.scrollHeight;

  const targetBody = document.getElementById(`${agentMsgId}_body`);
  const terminalWrap = document.getElementById(`${agentMsgId}_terminal_wrap`);
  const terminalBody = document.getElementById(`${agentMsgId}_terminal_body`);
  const thinkingLabel = document.getElementById(`${agentMsgId}_thinking_label`);
  let thinkingInterval = startThinkingRotation(thinkingLabel);

  let lastLogCount = 0;
  const pollInterval = setInterval(async () => {
    try {
      const pRes = await fetch('/api/copilot/scrape-logs');
      if (pRes.ok) {
        const pData = await pRes.json();
        const logs = pData.logs || [];
        if (logs.length > 0) {
          if (thinkingInterval) {
            thinkingInterval.stop();
            thinkingInterval = null;
            if (thinkingLabel) thinkingLabel.textContent = 'Scraping…';
          }
          if (terminalWrap && terminalWrap.style.display === 'none') {
            terminalWrap.style.display = 'block';
            feed.scrollTop = feed.scrollHeight;
          }
          if (terminalBody) {
            terminalBody.textContent = logs.map(line => `> ${line}`).join('\n');
            if (logs.length !== lastLogCount) {
              lastLogCount = logs.length;
              terminalBody.scrollTop = terminalBody.scrollHeight;
            }
          }
        }
      }
    } catch (e) {}
  }, 1000);

  try {
    const res = await fetch('/api/copilot/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        message: userText,
        history: chatHistory
      }),
      signal: currentAbortController.signal
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to communicate with OTTO agent');
    }

    clearInterval(pollInterval);
    if (thinkingInterval) thinkingInterval.stop();
    const data = await res.json();
    const thoughtSteps = data.thought_steps || [];
    const logEl = targetBody.querySelector('.agent-run-log');

    // Update conversation memory
    chatHistory.push({ role: 'user', content: userText });
    if (data.response_text) {
      chatHistory.push({ role: 'assistant', content: data.response_text });
    }

    // Fast-path animation for thought steps
    if (thoughtSteps.length > 0) {
      for (let i = 0; i < thoughtSteps.length; i++) {
        await new Promise(r => setTimeout(r, 200));
        if (logEl) {
          const stepEl = document.createElement('div');
          stepEl.className = 'run-step completed';
          stepEl.innerHTML = `<span class="step-dot completed"></span> ${escapeHtml(thoughtSteps[i])}`;
          logEl.appendChild(stepEl);
          feed.scrollTop = feed.scrollHeight;
        }
      }
      await new Promise(r => setTimeout(r, 150));
    }

    // Format Response Text (Markdown to HTML)
    let formattedText = data.response_text || '';
    const rawMarkdownText = formattedText;
    formattedText = formattedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formattedText = formattedText.replace(/\*(.*?)\*/g, '<em>$1</em>');
    formattedText = formattedText.replace(/^\*\s+(.*$)/gim, '<li style="margin-bottom:0.35rem;">$1</li>');
    if (formattedText.includes('<li')) {
      formattedText = formattedText.replace(/(<li.*<\/li>)/s, '<ul style="padding-left:1.1rem; margin:0.5rem 0;">$1</ul>');
    }
    formattedText = formattedText.split('\n\n').filter(p => p.trim() !== '').map(p => {
      if (p.includes('<ul')) return p;
      return `<p style="margin-bottom:0.6rem;">${p.trim()}</p>`;
    }).join('');

    // Generative Deal Cards HTML
    let cardsHtml = '';
    if (data.recommended_cars && data.recommended_cars.length > 0) {
      cardsHtml = `
        <div class="copilot-cards-grid">
          ${data.recommended_cars.map(c => `
            <div class="copilot-car-card">
              ${c.image_url ? `<img src="${escapeHtml(c.image_url)}" class="copilot-car-img" alt="${escapeHtml(c.title)}" onerror="this.style.display='none'">` : ''}
              <div class="copilot-car-info">
                <div class="copilot-car-title">${escapeHtml(c.title)}</div>
                <div class="copilot-car-meta">
                  <span>${c.year || ''}</span>
                  <span>•</span>
                  <span>${escapeHtml(c.transmission || 'Auto')}</span>
                  <span>•</span>
                  <span>${escapeHtml(c.location || 'SL')}</span>
                </div>
                <div class="copilot-car-pricing">
                  <div class="copilot-price">${formatLKR(c.price)}</div>
                  ${c.discount_pct > 0 ? `<div class="copilot-discount">-${c.discount_pct}% below avg</div>` : ''}
                </div>
                <div class="copilot-card-actions">
                  <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener" class="copilot-btn-link">${icon('sparkles')} View</a>
                  <button class="copilot-btn-pipeline" id="pipe_btn_${c.id}" onclick="window.saveCopilotCarToPipeline(${c.id})">+ Pipeline</button>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }

    const logHtml = thoughtSteps.length > 0 ? `
      <details class="agent-log-accordion">
        <summary><span class="log-toggle-icon">✓</span> Scout Logic & Run Log (${thoughtSteps.length} steps)</summary>
        <div class="agent-run-log">${logEl ? logEl.innerHTML : ''}</div>
      </details>
    ` : '';

    targetBody.innerHTML = `
      ${logHtml}
      <div class="agent-response-text">${formattedText}</div>
      ${cardsHtml}
      <div class="agent-msg-footer">
        <button class="msg-footer-btn" onclick="window.copyCopilotResponse(this, \`${escapeHtml(rawMarkdownText.replace(/`/g, '\\`'))}\`)">
          <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1M8 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M8 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m0 0h2a2 2 0 0 1 2 2v3m2 4H10m0 0 3-3m-3 3 3 3"/></svg> Copy
        </button>
      </div>
    `;

  } catch (err) {
    clearInterval(pollInterval);
    if (thinkingInterval) thinkingInterval.stop();
    if (err.name === 'AbortError') {
      targetBody.innerHTML = `
        <div style="color: var(--ink-secondary); font-size: 0.82rem; font-style: italic;">
          ⏹ Generation stopped.
        </div>
      `;
    } else {
      const isConnectionError = err.message.toLowerCase().includes('192.168.1.23') || 
                               err.message.toLowerCase().includes('11434') || 
                               err.message.toLowerCase().includes('failed to communicate');
      const errorMsg = isConnectionError 
        ? "Lankan GPU rig offline! 🔴 Ensure your TUFGAMING-0001 PC (192.168.1.23) is powered on and Ollama is running."
        : err.message;
      targetBody.innerHTML = `
        <div style="color: var(--danger); font-size: 0.85rem; font-weight: 500; line-height: 1.4;">
          ${icon('alertTriangle')} Error: ${escapeHtml(errorMsg)}
        </div>
      `;
      // Update LAN status indicator immediately to Offline
      const dot = document.getElementById('ottoCopilotStatusDot');
      const triggerDot = document.getElementById('ottoCopilotTriggerDot');
      const subtitle = document.getElementById('ottoCopilotSubtitle');
      if (dot && subtitle) {
        dot.style.backgroundColor = '#ef4444';
        if (triggerDot) triggerDot.style.backgroundColor = '#ef4444';
        subtitle.innerHTML = `<span class="status-dot" id="ottoCopilotStatusDot" style="background: #ef4444;"></span> qwen3-vl:8b (LAN Offline)`;
      }
    }
  } finally {
    setProcessingState(false);
    currentAbortController = null;
    feed.scrollTop = feed.scrollHeight;
  }
}

export async function saveCopilotCarToPipeline(carId) {
  const btn = document.getElementById(`pipe_btn_${carId}`);
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Saving...';
  }

  try {
    const res = await fetch(`/api/pipeline/${carId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage: 'saved' })
    });
    if (res.ok) {
      if (btn) {
        btn.innerText = '✓ Saved';
        btn.style.background = 'var(--success-bg)';
        btn.style.color = 'var(--success)';
        btn.style.borderColor = 'var(--success-border)';
      }
    } else {
      if (btn) {
        btn.disabled = false;
        btn.innerText = 'Retry';
      }
    }
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Retry';
    }
  }
}

window.toggleCopilot = toggleCopilot;
window.openCopilot = openCopilot;
window.closeCopilot = closeCopilot;
window.stopCopilotGeneration = stopGeneration;
window.editCopilotPrompt = editPrompt;
window.copyCopilotResponse = copyResponseText;
window.saveCopilotCarToPipeline = saveCopilotCarToPipeline;
window.checkOllamaStatus = checkOllamaStatus;

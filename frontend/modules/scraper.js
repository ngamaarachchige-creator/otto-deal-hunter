// Dynamic Module: Real-time Web Scraping & Polling Interface
import { escapeHtml } from './sanitize.js';

let pollTimer = null;

export function openScrapeModal() {
  const modal = document.getElementById('scrapeModal');
  if (modal) modal.classList.add('active');
}

export function closeScrapeModal() {
  const modal = document.getElementById('scrapeModal');
  if (modal) modal.classList.remove('active');
}

export function openEmptyScrapeModal(message) {
  const msgEl = document.getElementById('emptyScrapeMessage');
  if (msgEl) msgEl.innerText = message;
  const modal = document.getElementById('emptyScrapeModal');
  if (modal) modal.classList.add('active');
}

export function closeEmptyScrapeModal() {
  const modal = document.getElementById('emptyScrapeModal');
  if (modal) modal.classList.remove('active');
}

export async function startScrapingJob() {
  const sources = [];
  if (document.getElementById('scrapeRiyasewana')?.checked) sources.push('riyasewana');
  if (document.getElementById('scrapeIkman')?.checked) sources.push('ikman');

  if (sources.length === 0) {
    alert('Select at least one marketplace portal to scrape.');
    return;
  }

  const pages = parseInt(document.getElementById('scrapePagesSlider')?.value) || 3;
  const keyword = document.getElementById('scrapeKeyword')?.value.trim() || '';

  const startBtn = document.getElementById('startScrapeBtn');
  if (startBtn) {
    startBtn.disabled = true;
    startBtn.innerText = 'Fetching...';
  }

  const logSection = document.getElementById('scrapeLogSection');
  if (logSection) logSection.style.display = 'flex';
  
  const terminalLog = document.getElementById('scrapeTerminalLog');
  if (terminalLog) terminalLog.innerHTML = '<div>› Initializing scrape worker...</div>';
  
  const progressBar = document.getElementById('scrapeProgressBar');
  if (progressBar) progressBar.style.width = '15%';

  try {
    const res = await fetch('/api/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sources: sources,
        pages_per_source: pages,
        query: keyword
      })
    });

    if (!res.ok) {
      throw new Error(`Scrape trigger failed: ${res.statusText}`);
    }

    const data = await res.json();
    pollScrapeStatus(data.job_id);
  } catch (e) {
    alert('Error starting fetch: ' + e.message);
    if (startBtn) {
      startBtn.disabled = false;
      startBtn.innerText = 'Start Scraping';
    }
  }
}

function pollScrapeStatus(jobId) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/scrape-status/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();

      const stepEl = document.getElementById('scrapeCurrentStep');
      if (stepEl) stepEl.innerText = job.current_step || 'Scraping feeds...';

      const terminalLog = document.getElementById('scrapeTerminalLog');
      if (terminalLog && job.logs) {
        terminalLog.innerHTML = job.logs.map(l => `<div>› ${escapeHtml(l)}</div>`).join('');
        terminalLog.scrollTop = terminalLog.scrollHeight;
      }

      const progressBar = document.getElementById('scrapeProgressBar');
      const percentEl = document.getElementById('scrapePercent');

      if (job.status === 'running') {
        if (progressBar) progressBar.style.width = '65%';
        if (percentEl) percentEl.innerText = '65%';
      } else if (job.status === 'completed') {
        clearInterval(pollTimer);
        if (progressBar) progressBar.style.width = '100%';
        if (percentEl) percentEl.innerText = '100%';
        
        const startBtn = document.getElementById('startScrapeBtn');
        if (startBtn) {
          startBtn.disabled = false;
          startBtn.innerText = 'Fetch Again';
        }

        // Refresh global feed and stats
        if (window.loadCars) window.loadCars(0);
        if (window.loadStats) window.loadStats();

        if (job.total_scraped === 0) {
          closeScrapeModal();
          const queryMsg = job.query_used ? `for '${job.query_used}'` : '';
          const sourcesMsg = (job.sources || []).join(' and ');
          openEmptyScrapeModal(`No matching listings were found on ${sourcesMsg} ${queryMsg}. Check your spelling or try searching for a broader term like 'Suzuki' or 'Toyota'.`);
        }
      } else if (job.status === 'error') {
        clearInterval(pollTimer);
        if (stepEl) {
          stepEl.innerText = 'Scraping Error: ' + (job.error || 'Failed');
          stepEl.style.color = 'var(--danger)';
        }
        const startBtn = document.getElementById('startScrapeBtn');
        if (startBtn) {
          startBtn.disabled = false;
          startBtn.innerText = 'Retry';
        }
      }
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 1000);
}

// Bind to window
window.openScrapeModal = openScrapeModal;
window.closeScrapeModal = closeScrapeModal;
window.startScrapingJob = startScrapingJob;
window.openEmptyScrapeModal = openEmptyScrapeModal;
window.closeEmptyScrapeModal = closeEmptyScrapeModal;

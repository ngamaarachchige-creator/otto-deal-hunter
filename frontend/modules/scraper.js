// Dynamic Module: Real-time Web Scraping & Polling Interface

let pollTimer = null;

export function openScrapeModal() {
  document.getElementById('scrapeModal').classList.add('active');
}

export function closeScrapeModal() {
  document.getElementById('scrapeModal').classList.remove('active');
}

export function openEmptyScrapeModal(message) {
  document.getElementById('emptyScrapeMessage').innerText = message;
  document.getElementById('emptyScrapeModal').classList.add('active');
}

export function closeEmptyScrapeModal() {
  document.getElementById('emptyScrapeModal').classList.remove('active');
}

export async function startScrapeJob(refreshCallback) {
  const sources = [];
  if (document.getElementById('scrapeRiyasewana').checked) sources.push('riyasewana');
  if (document.getElementById('scrapeIkman').checked) sources.push('ikman');

  if (sources.length === 0) {
    alert('Select at least one portal to scrape.');
    return;
  }

  const pages = parseInt(document.getElementById('scrapePagesSlider').value) || 3;
  const keyword = document.getElementById('scrapeKeyword').value.trim();

  const startBtn = document.getElementById('startScrapeBtn');
  startBtn.disabled = true;
  startBtn.innerText = 'Fetching...';

  const logSection = document.getElementById('scrapeLogSection');
  logSection.style.display = 'flex';
  document.getElementById('scrapeLogs').innerHTML = '';
  document.getElementById('scrapeProgressBar').style.width = '10%';
  document.getElementById('scrapeStatusText').innerText = 'RUNNING';

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
    const data = await res.json();
    pollScrapeStatus(data.job_id, refreshCallback);
  } catch (e) {
    alert('Error starting fetch: ' + e.message);
    startBtn.disabled = false;
    startBtn.innerText = 'Start Fetch';
  }
}

function pollScrapeStatus(jobId, refreshCallback) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/scrape-status/${jobId}`);
      const job = await res.json();

      document.getElementById('scrapeCurrentStep').innerText = job.current_step || 'Processing request';
      document.getElementById('scrapeStatusText').innerText = job.status.toUpperCase();

      const logBox = document.getElementById('scrapeLogs');
      logBox.innerHTML = (job.logs || []).map(l => `<div>› ${l}</div>`).join('');
      logBox.scrollTop = logBox.scrollHeight;

      if (job.status === 'running') {
        document.getElementById('scrapeProgressBar').style.width = '65%';
      } else if (job.status === 'completed') {
        clearInterval(pollTimer);
        document.getElementById('scrapeProgressBar').style.width = '100%';
        document.getElementById('scrapeStatusText').innerText = 'COMPLETED';
        document.getElementById('startScrapeBtn').disabled = false;
        document.getElementById('startScrapeBtn').innerText = 'Fetch Again';

        if (refreshCallback) refreshCallback();

        if (job.total_scraped === 0) {
          closeScrapeModal();
          const queryMsg = job.query_used ? `for '${job.query_used}'` : '';
          const sourcesMsg = (job.sources || []).join(' and ');
          openEmptyScrapeModal(`No matching listings were found on ${sourcesMsg} ${queryMsg}. Check your spelling or try searching for a broader term like 'Suzuki' or 'Toyota'.`);
        }
      } else if (job.status === 'error') {
        clearInterval(pollTimer);
        document.getElementById('scrapeStatusText').innerText = 'ERROR';
        document.getElementById('scrapeStatusText').style.color = 'var(--danger)';
        document.getElementById('startScrapeBtn').disabled = false;
        document.getElementById('startScrapeBtn').innerText = 'Retry';
      }
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 1000);
}

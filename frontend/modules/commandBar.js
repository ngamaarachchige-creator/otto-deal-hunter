import { formatLKR } from '../app.js';
import { sendCopilotMessage, openCopilot } from './copilot.js';

let isCommandBarOpen = false;
let activeIndex = 0;

export function initCommandBar() {
  const backdrop = document.getElementById('ottoCommandBarBackdrop');
  const input = document.getElementById('ottoCommandBarInput');

  if (!backdrop || !input) return;

  // Bind keydown on window for Cmd+K / Ctrl+K & Esc
  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      toggleCommandBar();
    }
    if (e.key === 'Escape' && isCommandBarOpen) {
      e.preventDefault();
      closeCommandBar();
    }
  });

  // Input listeners
  input.addEventListener('input', updateSuggestions);
  input.addEventListener('keydown', handleInputKeys);

  // Initial render of suggestions
  updateSuggestions();
}

export function toggleCommandBar() {
  if (isCommandBarOpen) {
    closeCommandBar();
  } else {
    openCommandBar();
  }
}

export function openCommandBar() {
  const backdrop = document.getElementById('ottoCommandBarBackdrop');
  const input = document.getElementById('ottoCommandBarInput');
  if (!backdrop) return;

  // Close other drawers/panels if open
  window.closeCopilot?.();

  backdrop.classList.add('active');
  isCommandBarOpen = true;
  activeIndex = 0;
  
  if (input) {
    input.value = '';
    input.focus();
  }
  updateSuggestions();
}

export function closeCommandBar() {
  const backdrop = document.getElementById('ottoCommandBarBackdrop');
  if (!backdrop) return;

  backdrop.classList.remove('active');
  isCommandBarOpen = false;
}

function getSuggestions(val) {
  const cleanVal = val.trim();
  
  if (!cleanVal) {
    return [
      {
        icon: '🔍',
        text: 'Search <strong>Toyota Vitz</strong> deals in active feed',
        shortcut: '↵ Enter',
        action: 'search_feed',
        query: 'Toyota Vitz'
      },
      {
        icon: '⚡',
        text: 'Trigger live scrape for <strong>Wagon R</strong>',
        shortcut: '↵ Enter',
        action: 'scrape_cars',
        query: 'Wagon R'
      },
      {
        icon: '📊',
        text: 'Open CRM flip pipeline stages summary',
        shortcut: '↵ Enter',
        action: 'open_tab',
        tabId: 'pipeline'
      },
      {
        icon: '💬',
        text: 'Ask OTTO: <em>\"find me an Alto under 30 lakhs no cap\"</em>',
        shortcut: '↵ Enter',
        action: 'ask_otto',
        query: 'find me an Alto under 30 lakhs no cap'
      }
    ];
  }

  // Parse potential budgets in lakhs or millions
  let budgetPrompt = '';
  let parsedMax = null;
  const lakhsMatch = cleanVal.match(/(\d+(?:\.\d+)?)\s*lakhs?/i);
  const mMatch = cleanVal.match(/(\d+(?:\.\d+)?)\s*(?:m|million)/i);
  
  if (lakhsMatch) {
    parsedMax = parseFloat(lakhsMatch[1]) * 100000;
    budgetPrompt = ` under ${formatLKR(parsedMax)}`;
  } else if (mMatch) {
    parsedMax = parseFloat(mMatch[1]) * 1000000;
    budgetPrompt = ` under ${formatLKR(parsedMax)}`;
  }

  const queryWithoutBudget = cleanVal
    .replace(/\bunder\b/i, '')
    .replace(/\bbelow\b/i, '')
    .replace(/\bmax\b/i, '')
    .replace(/\b\d+(?:\.\d+)?\s*(?:lakhs?|m|million)\b/gi, '')
    .trim();

  const searchTitle = queryWithoutBudget || 'cars';

  return [
    {
      icon: '🤖',
      text: `Ask OTTO Agent: <strong>"${cleanVal}"</strong>`,
      shortcut: '↵ Enter',
      action: 'ask_otto',
      query: cleanVal
    },
    {
      icon: '🔍',
      text: `Filter Main Feed: <strong>${searchTitle}</strong>${budgetPrompt}`,
      shortcut: '↵ Enter',
      action: 'search_feed_custom',
      query: searchTitle,
      maxPrice: parsedMax
    },
    {
      icon: '⚡',
      text: `Trigger live scrape for: <strong>${searchTitle}</strong>`,
      shortcut: '↵ Enter',
      action: 'scrape_cars',
      query: searchTitle
    }
  ];
}

function updateSuggestions() {
  const input = document.getElementById('ottoCommandBarInput');
  const resultsContainer = document.getElementById('ottoCommandBarResults');
  if (!input || !resultsContainer) return;

  const suggestions = getSuggestions(input.value);
  
  let html = `<div class="command-section-title">${input.value ? 'MATCHING COMMANDS' : 'SUGGESTED COMMANDS'}</div>`;
  
  suggestions.forEach((item, idx) => {
    const isActive = idx === activeIndex;
    html += `
      <div class="command-item ${isActive ? 'active' : ''}" data-index="${idx}">
        <span class="command-icon">${item.icon}</span>
        <span class="command-text">${item.text}</span>
        <span class="command-shortcut">${item.shortcut}</span>
      </div>
    `;
  });

  resultsContainer.innerHTML = html;

  // Bind click on items
  resultsContainer.querySelectorAll('.command-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.getAttribute('data-index'));
      executeCommand(suggestions[idx]);
    });
  });
}

function handleInputKeys(e) {
  const input = document.getElementById('ottoCommandBarInput');
  const suggestions = getSuggestions(input ? input.value : '');
  
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    activeIndex = (activeIndex + 1) % suggestions.length;
    updateSuggestions();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    activeIndex = (activeIndex - 1 + suggestions.length) % suggestions.length;
    updateSuggestions();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (suggestions[activeIndex]) {
      executeCommand(suggestions[activeIndex]);
    }
  }
}

function executeCommand(item) {
  closeCommandBar();
  
  if (item.action === 'search_feed') {
    const searchInput = document.getElementById('filterQuery');
    if (searchInput) {
      searchInput.value = item.query;
      window.executeNLUSearch?.();
    }
  } else if (item.action === 'search_feed_custom') {
    const searchInput = document.getElementById('filterQuery');
    if (searchInput) {
      searchInput.value = item.query;
    }
    const maxPriceInput = document.getElementById('filterMaxPrice');
    if (maxPriceInput && item.maxPrice) {
      maxPriceInput.value = item.maxPrice;
    }
    window.executeNLUSearch?.();
  } else if (item.action === 'scrape_cars') {
    window.openScrapeModal?.();
    const scrapeInput = document.getElementById('scrapeQuery');
    if (scrapeInput) {
      scrapeInput.value = item.query;
    }
  } else if (item.action === 'open_tab') {
    window.switchTab?.(item.tabId);
  } else if (item.action === 'ask_otto') {
    openCopilot();
    sendCopilotMessage(item.query);
  }
}

// Expose functions globally for layout onclick bindings
window.toggleCommandBar = toggleCommandBar;
window.closeCommandBar = closeCommandBar;
window.openCommandBar = openCommandBar;

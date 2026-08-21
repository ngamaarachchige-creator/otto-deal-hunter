// Dynamic Module: Natural Language Understanding (NLU) Search Parser for Sri Lankan Vehicle Classifieds

const POPULAR_MAKES = [
  'toyota', 'suzuki', 'honda', 'nissan', 'daihatsu', 'mitsubishi', 
  'mazda', 'hyundai', 'kia', 'mercedes-benz', 'bmw', 'audi', 'land rover',
  'micro', 'perodua', 'peugeot', 'dfsk', 'chery', 'mg', 'subaru', 'volkswagen', 'ford'
];

const POPULAR_MODELS = [
  'aqua', 'celerio', 'swift', 'vitz', 'wagon r', 'wagonr', 'alto', 'axio', 'premio',
  'fit', 'vezel', 'prius', 'mira', 'sunny', 'belta', 'civic', 'grace', 'ist', 'cr-v', 'crv',
  'tucson', 'sportage', 'picanto', 'spacia', 'hustler', 'dayz', 'march', 'passo', 'yaris',
  'raize', 'x-trail', 'xtrail', 'outlander', 'pajero', 'hilux', 'ranger', 'd-max', 'dmax',
  'prado', 'harrier', 'ch-r', 'chr', 'elantra', 'corolla', 'fb15', '110', '121', 'viva elite', 'axia'
];

const DISTRICTS = [
  'colombo', 'gampaha', 'kalutara', 'kandy', 'matale', 'nuwara eliya',
  'galle', 'matara', 'hambantota', 'jaffna', 'kilinochchi', 'mannar',
  'vavuniya', 'mullaitivu', 'batticaloa', 'ampara', 'trincomalee',
  'kurunegala', 'puttalam', 'anuradhapura', 'polonnaruwa', 'badulla',
  'monaragala', 'ratnapura', 'kegalle'
];

export function parseNaturalLanguageQuery(text) {
  if (!text || typeof text !== 'string') return {};
  
  let raw = text.trim();
  let lower = raw.toLowerCase();
  const parsed = {
    make: '',
    model: '',
    year: null,
    min_year: null,
    max_year: null,
    min_price: null,
    max_price: null,
    district: '',
    deal_filter: '',
    cleaned_query: ''
  };

  // 1. Parse Years (e.g. 2019, 2010 to 2015, after 2014, 2010+)
  const rangeYearMatch = lower.match(/(\b20\d{2}\b)\s*(?:to|-)\s*(\b20\d{2}\b)/);
  if (rangeYearMatch) {
    parsed.min_year = parseInt(rangeYearMatch[1]);
    parsed.max_year = parseInt(rangeYearMatch[2]);
    lower = lower.replace(rangeYearMatch[0], ' ');
  } else {
    const afterYearMatch = lower.match(/(?:after|above|newer than|\>)\s*(\b20\d{2}\b)/);
    if (afterYearMatch) {
      parsed.min_year = parseInt(afterYearMatch[1]);
      lower = lower.replace(afterYearMatch[0], ' ');
    } else {
      const yearPlusMatch = lower.match(/(\b20\d{2}\b)\s*\+/);
      if (yearPlusMatch) {
        parsed.min_year = parseInt(yearPlusMatch[1]);
        lower = lower.replace(yearPlusMatch[0], ' ');
      } else {
        const singleYearMatch = lower.match(/\b(19\d{2}|20\d{2})\b/);
        if (singleYearMatch) {
          parsed.year = parseInt(singleYearMatch[1]);
          parsed.min_year = parsed.year;
          parsed.max_year = parsed.year;
          lower = lower.replace(singleYearMatch[0], ' ');
        }
      }
    }
  }

  // 2. Parse Price constraints (e.g. under 5.5m, below 6 million, 5m - 6m, under 60 lakhs, less than 5.5 mil, < 6m)
  const priceRangeMatch = lower.match(/(\d+(?:\.\d+)?)\s*(?:m|mil|million|lakhs?|lkr)?\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(m|mil|million|lakhs?|lkr)?/);
  if (priceRangeMatch && (priceRangeMatch[0].includes('m') || priceRangeMatch[0].includes('lakh') || priceRangeMatch[0].includes('to'))) {
    let p1 = parseFloat(priceRangeMatch[1]);
    let p2 = parseFloat(priceRangeMatch[2]);
    if (p1 < 100) p1 *= 1000000;
    if (p2 < 100) p2 *= 1000000;
    parsed.min_price = p1;
    parsed.max_price = p2;
    lower = lower.replace(priceRangeMatch[0], ' ');
  } else {
    // Under / below / max / less than
    const maxPriceMatch = lower.match(/(?:under|below|less than|max|up to|\<)\s*(\d+(?:\.\d+)?)\s*(m|mil|million|lakhs?|lkr)?/);
    if (maxPriceMatch) {
      let val = parseFloat(maxPriceMatch[1]);
      const unit = maxPriceMatch[2] || '';
      if (unit.startsWith('lakh')) {
        val = val * 100000;
      } else if (val < 100 || unit.startsWith('m')) {
        val = val * 1000000;
      }
      parsed.max_price = val;
      lower = lower.replace(maxPriceMatch[0], ' ');
    }
    
    // Above / min / more than
    const minPriceMatch = lower.match(/(?:above|more than|min|from|\>)\s*(\d+(?:\.\d+)?)\s*(m|mil|million|lakhs?|lkr)?/);
    if (minPriceMatch) {
      let val = parseFloat(minPriceMatch[1]);
      const unit = minPriceMatch[2] || '';
      if (unit.startsWith('lakh')) {
        val = val * 100000;
      } else if (val < 100 || unit.startsWith('m')) {
        val = val * 1000000;
      }
      parsed.min_price = val;
      lower = lower.replace(minPriceMatch[0], ' ');
    }
  }

  // 3. Parse Districts / Locations (e.g. in colombo, gampaha, kandy)
  for (const d of DISTRICTS) {
    const reg = new RegExp(`\\b(?:in|at|near)?\\s*${d}\\b`, 'i');
    if (reg.test(lower)) {
      parsed.district = d.charAt(0).toUpperCase() + d.slice(1);
      lower = lower.replace(reg, ' ');
      break;
    }
  }

  // 4. Parse Makes
  for (const m of POPULAR_MAKES) {
    const reg = new RegExp(`\\b${m}\\b`, 'i');
    if (reg.test(lower)) {
      parsed.make = m.charAt(0).toUpperCase() + m.slice(1);
      lower = lower.replace(reg, ' ');
      break;
    }
  }

  // 5. Parse Models
  for (const mod of POPULAR_MODELS) {
    const reg = new RegExp(`\\b${mod}\\b`, 'i');
    if (reg.test(lower)) {
      parsed.model = mod.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
      lower = lower.replace(reg, ' ');
      break;
    }
  }

  // 6. Parse Deal Type Keywords
  if (lower.includes('hot') || lower.includes('underpriced') || lower.includes('flip') || lower.includes('bargain')) {
    parsed.deal_filter = 'hot';
    lower = lower.replace(/\b(hot|underpriced|flips?|bargain|deals?)\b/g, ' ');
  } else if (lower.includes('good')) {
    parsed.deal_filter = 'good';
    lower = lower.replace(/\b(good|deals?)\b/g, ' ');
  } else if (lower.includes('negotiable') || lower.includes('price on request') || lower.includes('unpriced')) {
    parsed.deal_filter = 'negotiable';
    lower = lower.replace(/\b(negotiable|price on request|unpriced)\b/g, ' ');
  }

  // Clean remaining residual query keywords
  const cleaned = lower.replace(/\b(for sale|sale|car|cars|in|at|with|and|the|a|looking for|find me|show me)\b/g, ' ')
                       .replace(/\s+/g, ' ').trim();
  parsed.cleaned_query = cleaned;

  return parsed;
}

export function renderParsedChips(parsed, onRemoveCallback) {
  const chips = [];

  if (parsed.make) {
    chips.push({ key: 'make', label: `Make: ${parsed.make}` });
  }
  if (parsed.model) {
    chips.push({ key: 'model', label: `Model: ${parsed.model}` });
  }
  if (parsed.year) {
    chips.push({ key: 'year', label: `Year: ${parsed.year}` });
  } else if (parsed.min_year && parsed.max_year) {
    chips.push({ key: 'year_range', label: `Years: ${parsed.min_year}–${parsed.max_year}` });
  } else if (parsed.min_year) {
    chips.push({ key: 'min_year', label: `Year: ${parsed.min_year}+` });
  }
  if (parsed.min_price && parsed.max_price) {
    chips.push({ key: 'price_range', label: `Price: Rs. ${(parsed.min_price/1000000).toFixed(1)}M – ${(parsed.max_price/1000000).toFixed(1)}M` });
  } else if (parsed.max_price) {
    chips.push({ key: 'max_price', label: `Max Price: Rs. ${(parsed.max_price/1000000).toFixed(1)}M` });
  } else if (parsed.min_price) {
    chips.push({ key: 'min_price', label: `Min Price: Rs. ${(parsed.min_price/1000000).toFixed(1)}M` });
  }
  if (parsed.district) {
    chips.push({ key: 'district', label: `District: ${parsed.district}` });
  }
  if (parsed.deal_filter) {
    chips.push({ key: 'deal_filter', label: `Deals: ${parsed.deal_filter.toUpperCase()}` });
  }

  return chips.map(c => `
    <span class="nlu-chip" data-key="${c.key}">
      ${c.label}
      <button type="button" class="nlu-chip-remove" onclick="window.removeNLUFilter('${c.key}')">×</button>
    </span>
  `).join('');
}

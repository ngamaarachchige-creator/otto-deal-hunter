// Escapes text pulled from scraped listings (seller-controlled) before it's
// interpolated into an innerHTML template string, so a crafted title or
// image_url can't break out of an attribute/tag and inject a handler.
export function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

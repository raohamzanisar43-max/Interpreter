export const fmtDate = (d) => (d ? new Date(d).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—')
export const fmtDay = (d) => (d ? new Date(d).toLocaleDateString('en-GB', { dateStyle: 'medium' }) : '—')
export const pct = (v) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(1)}%`)
export const ordinal = (n) => { const s = ['th', 'st', 'nd', 'rd']; const v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]) }
export const toLocalInput = (d) => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 16) }
export const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export function countdown(deadline) {
  const ms = new Date(deadline) - Date.now()
  if (ms <= 0) return 'deadline passed'
  const d = Math.floor(ms / 864e5); const h = Math.floor((ms % 864e5) / 36e5)
  return d > 0 ? `${d}d ${h}h left` : `${h}h ${Math.floor((ms % 36e5) / 6e4)}m left`
}

/** Tiny markdown renderer (headings, bold, lists) — enough for terms / privacy text. */
export function mdToHtml(src = '') {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>')
  const out = []; let list = null
  for (const line of src.split('\n')) {
    const h = line.match(/^(#{1,3})\s+(.*)/); const li = line.match(/^(?:\d+\.|[-*])\s+(.*)/)
    if (li) { const tag = /^\d/.test(line) ? 'ol' : 'ul'; if (list !== tag) { if (list) out.push(`</${list}>`); out.push(`<${tag}>`); list = tag } out.push(`<li>${inline(li[1])}</li>`); continue }
    if (list) { out.push(`</${list}>`); list = null }
    if (h) out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`)
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`)
  }
  if (list) out.push(`</${list}>`)
  return out.join('')
}

import { useEffect, useRef } from 'react'

export const VALUE_LABEL = { full: 'Fully', partial: 'Partly', lost: 'Lost' }
const KEYMAP = { 1: 'full', 2: 'partial', 3: 'lost' }

/**
 * Key-point checklist with Fully / Partly / Lost buttons and an optional comment per point.
 * Keyboard: 1/2/3 score the highlighted point (and move on), ↑/↓ move the highlight.
 * `scores` = {[keyPointId]: {value, comment}}. Disabled shows read-only values.
 */
export default function ScoringPanel({ keyPoints, scores, onChange, disabled, current, setCurrent, showComments = true, reference }) {
  const refs = useRef({})

  useEffect(() => {
    if (disabled) return undefined
    const onKey = (e) => {
      const tag = e.target.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT' || e.ctrlKey || e.metaKey || e.altKey) return
      const kp = keyPoints[current]
      if (KEYMAP[e.key] && kp) {
        e.preventDefault()
        onChange(kp.id, { value: KEYMAP[e.key] })
        if (current < keyPoints.length - 1) setCurrent(current + 1)
      } else if (e.key === 'ArrowDown') { e.preventDefault(); setCurrent(Math.min(current + 1, keyPoints.length - 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setCurrent(Math.max(current - 1, 0)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [disabled, keyPoints, current, onChange, setCurrent])

  useEffect(() => { refs.current[current]?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }) }, [current])

  return (
    <div className="stack" role="list">
      {keyPoints.map((k, i) => {
        const s = scores[k.id] || {}
        return (
          <div key={k.id} role="listitem" ref={(el) => { refs.current[i] = el }} className={`kp ${current === i ? 'current' : ''}`} onClick={() => setCurrent?.(i)}>
            <div className="row between">
              <div><span className="muted small">{i + 1}. {k.category}</span><div>{k.text}</div></div>
              <div className="seg" role="group" aria-label={`Score for key point ${i + 1}`}>
                {Object.entries(VALUE_LABEL).map(([v, l]) => (
                  <button key={v} type="button" className={v} aria-pressed={s.value === v} disabled={disabled}
                    onClick={() => onChange(k.id, { value: v })}>{l}</button>
                ))}
              </div>
            </div>
            {reference && s.value && (
              <div className={`alert ${reference[k.id]?.match ? 'ok' : 'warn'}`}>
                Reference: <strong>{VALUE_LABEL[reference[k.id]?.reference]}</strong> {reference[k.id]?.explanation && `— ${reference[k.id].explanation}`}
              </div>
            )}
            {showComments && (
              <input placeholder="Comment (optional)" aria-label={`Comment for key point ${i + 1}`} value={s.comment || ''} disabled={disabled}
                onChange={(e) => onChange(k.id, { comment: e.target.value })} onFocus={() => setCurrent?.(i)} />
            )}
          </div>
        )
      })}
    </div>
  )
}

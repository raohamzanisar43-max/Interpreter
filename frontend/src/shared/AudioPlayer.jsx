import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { mmss } from './util'

/**
 * Shared audio player: play/pause, 10 s back, speed 0.75x–1.25x, scrubber.
 * `refresh` (async () => newUrl) is called when the signed URL has expired mid-session.
 * `singlePlay` allows one listen only (the controls lock after the audio ends).
 */
const AudioPlayer = forwardRef(function AudioPlayer({ url, label, refresh, singlePlay, active, onPlay, compact }, ref) {
  const a = useRef()
  const [src, setSrc] = useState(url)
  const [playing, setPlaying] = useState(false)
  const [t, setT] = useState(0)
  const [dur, setDur] = useState(0)
  const [rate, setRate] = useState(1)
  const [used, setUsed] = useState(false)
  const [err, setErr] = useState(null)
  const resume = useRef(null)

  useEffect(() => { setSrc(url); setErr(null) }, [url])
  useEffect(() => { if (a.current) a.current.playbackRate = rate }, [rate, src])

  const toggle = useCallback(() => {
    const el = a.current
    if (!el || (singlePlay && used)) return
    if (el.paused) el.play().catch(() => {}); else el.pause()
  }, [singlePlay, used])
  useImperativeHandle(ref, () => ({ toggle, pause: () => a.current?.pause() }), [toggle])

  const onError = async () => {
    if (!refresh || resume.current !== null) { setErr('Audio could not be loaded.'); return }
    resume.current = a.current?.currentTime || 0       // expired signed URL: fetch a fresh one and continue
    try { setSrc(await refresh()) } catch { setErr('Audio could not be loaded.') }
  }
  const onLoaded = () => {
    setDur(a.current.duration || 0)
    if (resume.current !== null) { a.current.currentTime = resume.current; a.current.play().catch(() => {}); resume.current = null }
  }

  const locked = singlePlay && used
  return (
    <div className={`player ${active ? 'active' : ''}`}>
      {label && <div className="label">{label}</div>}
      <audio ref={a} src={src} preload="metadata"
        onPlay={() => { setPlaying(true); onPlay?.() }} onPause={() => setPlaying(false)}
        onEnded={() => { setPlaying(false); if (singlePlay) setUsed(true) }}
        onTimeUpdate={() => setT(a.current.currentTime)} onLoadedMetadata={onLoaded} onError={onError} />
      {err ? <div className="err small" role="alert" style={{ color: 'var(--bad)' }}>{err}</div> : (
        <div className="controls">
          <button type="button" className="btn sm" onClick={toggle} disabled={locked} aria-label={playing ? 'Pause' : 'Play'}>{playing ? '⏸ Pause' : '▶ Play'}</button>
          {!compact && !singlePlay && <button type="button" className="btn sm" onClick={() => { a.current.currentTime = Math.max(0, a.current.currentTime - 10) }} aria-label="Back 10 seconds">⟲ 10s</button>}
          <input type="range" min="0" max={dur || 0} step="0.1" value={t} disabled={locked || singlePlay} aria-label={`${label || 'Audio'} position`}
            onChange={(e) => { a.current.currentTime = Number(e.target.value) }} />
          <span className="small muted" style={{ minWidth: 70, textAlign: 'right' }}>{mmss(t)} / {mmss(dur)}</span>
          {!compact && !singlePlay && (
            <select value={rate} onChange={(e) => setRate(Number(e.target.value))} aria-label="Playback speed">
              {[0.75, 1, 1.25].map((r) => <option key={r} value={r}>{r}x</option>)}
            </select>
          )}
        </div>
      )}
      {locked && <div className="muted small">Single play only — already listened.</div>}
    </div>
  )
})
export default AudioPlayer

import { useCallback, useEffect, useRef, useState } from 'react'

/** iOS Safari records audio/mp4, Android Chrome audio/webm;codecs=opus — pick whatever the browser supports. */
export function pickMime() {
  const c = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return (typeof MediaRecorder !== 'undefined' && c.find((t) => MediaRecorder.isTypeSupported?.(t))) || ''
}

export const extFor = (mime = '') => (mime.includes('mp4') ? '.m4a' : mime.includes('ogg') ? '.ogg' : mime.includes('mpeg') ? '.mp3' : mime.includes('wav') ? '.wav' : '.webm')

export function useRecorder() {
  const [state, setState] = useState('idle')      // idle | recording | stopped
  const [level, setLevel] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const [result, setResult] = useState(null)      // {blob, mime, seconds}
  const [error, setError] = useState('')
  const r = useRef({})

  const cleanup = useCallback(() => {
    const s = r.current
    cancelAnimationFrame(s.raf); clearInterval(s.timer)
    s.stream?.getTracks().forEach((t) => t.stop())
    s.ctx?.close?.().catch(() => {})
    s.wake?.release?.().catch(() => {})
    setLevel(0)
  }, [])
  useEffect(() => cleanup, [cleanup])

  const start = useCallback(async () => {
    setError(''); setResult(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Recording is not supported in this browser. Use "Upload audio file" instead.'); return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const mime = pickMime()
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      const chunks = []
      const s = r.current
      s.stream = stream; s.mr = mr; s.t0 = Date.now()
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      mr.onstop = () => {
        const type = mr.mimeType || mime || 'audio/webm'
        const secs = (Date.now() - s.t0) / 1000
        cleanup()
        setResult({ blob: new Blob(chunks, { type }), mime: type, seconds: Math.round(secs * 10) / 10 })
        setState('stopped')
      }
      // live level meter
      const Ctx = window.AudioContext || window.webkitAudioContext
      if (Ctx) {
        const ctx = new Ctx(); const src = ctx.createMediaStreamSource(stream); const an = ctx.createAnalyser(); an.fftSize = 512; src.connect(an)
        const buf = new Uint8Array(an.fftSize); s.ctx = ctx
        const tick = () => { an.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) sum += ((v - 128) / 128) ** 2; setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 3)); s.raf = requestAnimationFrame(tick) }
        tick()
      }
      try { s.wake = await navigator.wakeLock?.request('screen') } catch { /* optional */ }
      mr.start(1000)
      setSeconds(0); setState('recording')
      s.timer = setInterval(() => setSeconds(Math.floor((Date.now() - s.t0) / 1000)), 250)
    } catch (e) {
      cleanup()
      setError(e.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow it in your browser settings, or use "Upload audio file".' : e.name === 'NotFoundError' ? 'No microphone found.' : `Could not start recording (${e.message}).`)
    }
  }, [cleanup])

  const stop = useCallback(() => { const mr = r.current.mr; if (mr && mr.state !== 'inactive') mr.stop() }, [])
  const reset = useCallback(() => { setResult(null); setState('idle'); setSeconds(0) }, [])
  return { state, level, seconds, result, error, start, stop, reset, setResult: (x) => { setResult(x); setState('stopped') } }
}

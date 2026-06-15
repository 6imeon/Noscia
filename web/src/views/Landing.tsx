// Landing page. Noscia's "Research Console" style (Oat palette, system sans + SF Mono,
// caramel accent). Hero is a field of free-floating gradient particles that the cursor
// repels like a fluid (outward force added to each particle's own velocity, no tether,
// with a viscous drag back to a baseline drift, grounded in Stam's stable-fluids
// force/advect/diffuse split). Content sections explain the product, with scroll-reveal
// and light parallax. Mounted at /landing (see main.tsx); CTAs enter the app at '/'.
import { useEffect, useRef } from 'react'
import { Logo } from '../app/Logo'

export function Landing() {
  const auraRef = useRef<HTMLDivElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const blob1 = useRef<HTMLDivElement>(null)
  const blob2 = useRef<HTMLDivElement>(null)

  // Fluid particle aura.
  useEffect(() => {
    const aura = auraRef.current
    if (!aura) return
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    let W = innerWidth, H = innerHeight
    const onResize = () => { W = innerWidth; H = innerHeight }
    addEventListener('resize', onResize)

    const PAL = [[95, 110, 77], [191, 138, 85], [138, 154, 102], [176, 124, 69], [110, 132, 84]]
    const N = 10
    const parts: { el: HTMLDivElement; x: number; y: number; vx: number; vy: number }[] = []
    aura.innerHTML = ''
    for (let i = 0; i < N; i++) {
      const c = PAL[i % PAL.length]
      const a = (0.5 + Math.random() * 0.22).toFixed(2)
      const sz = 15 + Math.random() * 16 // vw
      const el = document.createElement('div')
      el.style.cssText =
        `position:absolute;left:0;top:0;width:${sz}vw;height:${sz}vw;border-radius:50%;` +
        `filter:blur(44px);opacity:.55;will-change:transform;` +
        `background:radial-gradient(circle, rgba(${c[0]},${c[1]},${c[2]},${a}), transparent 70%)`
      aura.appendChild(el)
      const sp = 0.22 + Math.random() * 0.22
      const ang = Math.random() * 6.283
      parts.push({ el, x: Math.random() * W, y: Math.random() * H, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp })
    }

    let mx = -1e4, my = -1e4
    const onMove = (e: PointerEvent) => { mx = e.clientX; my = e.clientY }
    const onLeave = () => { mx = -1e4; my = -1e4 }
    addEventListener('pointermove', onMove, { passive: true })
    addEventListener('pointerleave', onLeave)

    const R = 260, EPS = 26, FORCE = 2.0, MAXV = 7, DRAG = 0.985, BASE = 0.34
    let raf = 0
    const loop = () => {
      for (const b of parts) {
        const w = b.el.offsetWidth, h = b.el.offsetHeight
        const dx = b.x - mx, dy = b.y - my, r = Math.hypot(dx, dy)
        if (r < R) { const m = (FORCE * (1 - r / R)) / (r + EPS); b.vx += dx * m; b.vy += dy * m } // shove outward
        if (!reduce) {
          b.vx *= DRAG; b.vy *= DRAG
          let sp = Math.hypot(b.vx, b.vy)
          if (sp > MAXV) { b.vx *= MAXV / sp; b.vy *= MAXV / sp }
          else if (sp < BASE && sp > 1e-4) { b.vx *= BASE / sp; b.vy *= BASE / sp } // never fully stop
          b.x += b.vx; b.y += b.vy
          if (b.x < 0) { b.x = 0; b.vx = Math.abs(b.vx) } else if (b.x > W) { b.x = W; b.vx = -Math.abs(b.vx) }
          if (b.y < 0) { b.y = 0; b.vy = Math.abs(b.vy) } else if (b.y > H) { b.y = H; b.vy = -Math.abs(b.vy) }
        }
        b.el.style.transform = `translate(${(b.x - w / 2).toFixed(1)}px,${(b.y - h / 2).toFixed(1)}px)`
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(raf)
      removeEventListener('resize', onResize)
      removeEventListener('pointermove', onMove)
      removeEventListener('pointerleave', onLeave)
      aura.innerHTML = ''
    }
  }, [])

  // Scroll-reveal for content blocks.
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target) } }),
      { threshold: 0.18 },
    )
    root.querySelectorAll('.reveal').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  // Light parallax on the decorative blobs.
  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        const y = scrollY
        if (blob1.current) blob1.current.style.transform = `translateY(${y * 0.12}px)`
        if (blob2.current) blob2.current.style.transform = `translateY(${y * -0.08}px)`
        raf = 0
      })
    }
    addEventListener('scroll', onScroll, { passive: true })
    return () => { removeEventListener('scroll', onScroll); if (raf) cancelAnimationFrame(raf) }
  }, [])

  const enterApp = () => { window.location.href = '/' }

  return (
    <div ref={rootRef} className="w-full bg-bg font-sans text-ink">
      {/* ===================== HERO ===================== */}
      <header
        className="relative min-h-screen w-full overflow-hidden"
        style={{ background: 'radial-gradient(120% 100% at 50% 0%, #f6efe2, var(--color-bg) 60%)' }}
      >
        <div ref={auraRef} className="absolute inset-0 z-0 overflow-hidden" />
        <div
          className="pointer-events-none absolute inset-0 z-[1]"
          style={{ background: 'radial-gradient(120% 80% at 50% 42%, transparent 48%, rgba(239,232,220,0.6))' }}
        />

        <nav className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-8 py-6">
          <a href="/landing" className="flex items-center gap-2.5 font-mono text-sm font-semibold tracking-[0.2em] text-ink">
            <Logo size={18} />
            NOSCIA
          </a>
          <button
            type="button"
            onClick={enterApp}
            className="rounded-full border border-line/80 bg-panel/60 px-5 py-2 font-mono text-xs tracking-wide text-muted backdrop-blur-sm transition-colors hover:border-accent hover:text-accent"
          >
            Launch console →
          </button>
        </nav>

        <section className="relative z-10 mx-auto flex min-h-[calc(100vh-84px)] w-full max-w-3xl flex-col items-center justify-center px-6 text-center">
          <p className="animate-fade-rise mb-6 font-mono text-xs uppercase tracking-[0.28em] text-accent-2">
            Vertical neural search
          </p>
          <h1
            className="animate-fade-rise max-w-3xl text-5xl font-medium tracking-[-0.035em] text-ink sm:text-6xl md:text-7xl"
            style={{ lineHeight: 1.02 }}
          >
            Neural search for the <span className="text-accent">fields</span> that matter.
          </h1>
          <p className="animate-fade-rise-delay mt-7 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            Cited passages from a curated, authoritative corpus, one vertical at a time. No open-web
            crawl, no invented sources.
          </p>
          <div className="animate-fade-rise-delay-2 mt-10 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={enterApp}
              className="rounded-lg bg-accent px-7 py-3 text-sm font-semibold text-on-accent transition-transform duration-200 hover:scale-[1.03]"
            >
              Enter Noscia
            </button>
            <button
              type="button"
              onClick={enterApp}
              className="rounded-lg border border-line bg-panel/50 px-7 py-3 text-sm font-medium text-ink backdrop-blur-sm transition-colors hover:border-accent/70 hover:text-accent"
            >
              See it search
            </button>
          </div>
        </section>
      </header>

      {/* ===================== WHAT IT DOES ===================== */}
      <section className="relative overflow-hidden px-6 py-28 sm:py-36">
        <div
          ref={blob1}
          className="pointer-events-none absolute -left-32 top-10 -z-0 h-80 w-80 rounded-full opacity-60 blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(95,110,77,0.22), transparent 70%)' }}
        />
        <div
          ref={blob2}
          className="pointer-events-none absolute -right-24 bottom-0 -z-0 h-72 w-72 rounded-full opacity-60 blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(191,138,85,0.18), transparent 70%)' }}
        />
        <div className="relative mx-auto max-w-6xl">
          <div className="reveal max-w-2xl">
            <p className="mb-4 font-mono text-xs uppercase tracking-[0.24em] text-accent-2">What it does</p>
            <h2 className="text-3xl font-medium tracking-[-0.02em] text-ink sm:text-[42px]" style={{ lineHeight: 1.1 }}>
              Search that shows its sources.
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted">
              Every answer is grounded in passages from a corpus you control, ranked with hybrid
              neural and lexical retrieval, reranked for precision, and returned with the exact text
              it stood on. Never a paraphrase of the open web.
            </p>
          </div>
          <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {CARDS.map((c, i) => (
              <div
                key={c.title}
                data-delay={i + 1}
                className="reveal group relative overflow-hidden rounded-2xl border border-line bg-field/80 p-7 backdrop-blur-sm transition-all duration-300 hover:-translate-y-1.5 hover:border-accent/50 hover:shadow-[0_24px_60px_rgba(51,47,40,0.10)]"
              >
                <div
                  className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100"
                  style={{ background: c.glow }}
                />
                <div
                  className="relative mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-panel font-mono text-lg"
                  style={{ color: c.iconColor }}
                >
                  {c.icon}
                </div>
                <h3 className="relative mb-2.5 text-lg font-semibold tracking-[-0.01em] text-ink">{c.title}</h3>
                <p className="relative text-[15px] leading-relaxed text-muted">{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===================== SHOWCASE ===================== */}
      <section
        className="relative overflow-hidden px-6 py-28 sm:py-36"
        style={{ background: 'linear-gradient(180deg, rgba(95,110,77,0.06), rgba(239,232,220,0) 60%)' }}
      >
        <div className="mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-2">
          <div className="reveal">
            <p className="mb-4 font-mono text-xs uppercase tracking-[0.24em] text-accent-2">Ask in plain language</p>
            <h2 className="text-3xl font-medium tracking-[-0.02em] text-ink sm:text-[42px]" style={{ lineHeight: 1.1 }}>
              Intent in. Cited passages out.
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted">
              A question about climate-related financial disclosure routes to the regulators and
              frameworks that actually answer it, and hands back the sentences, ranked and linked.
              When the corpus can&apos;t answer, Noscia says so instead of inventing a source.
            </p>
            <div className="mt-7 flex flex-wrap gap-2.5">
              {['hybrid RRF', 'cross-encoder rerank', 'evidence-or-null', 'no egress'].map((p) => (
                <span key={p} className="rounded-full border border-line bg-field px-3.5 py-1.5 font-mono text-xs text-muted">
                  {p}
                </span>
              ))}
            </div>
          </div>
          <div className="reveal" data-delay="1">
            <div
              className="overflow-hidden rounded-2xl border p-6 shadow-[0_30px_70px_rgba(20,24,14,0.28)]"
              style={{ background: 'linear-gradient(160deg, #1c2614, #11160c)', borderColor: '#2c3522' }}
            >
              <div className="font-mono text-[13px] leading-[1.9] text-[#d7cfb8]">
                <div className="flex gap-2.5">
                  <span className="text-accent">›</span>
                  <span>how do central banks set rates to curb inflation?</span>
                </div>
                <div className="my-3 h-px bg-[#2c3522]" />
                <div className="text-[#7d8669]">retrieving · economics · hybrid</div>
                <div className="mt-1">
                  <span className="text-[#a8bd84]">01</span>{' '}
                  <span className="text-[#d7cfb8]">federalreserve.gov · </span>
                  <span className="rounded bg-[rgba(191,138,85,0.2)] px-1 text-[#f1e6d2]">
                    the policy rate is the FOMC&apos;s primary tool
                  </span>
                  …
                </div>
                <div>
                  <span className="text-[#a8bd84]">02</span>{' '}
                  <span className="text-[#d7cfb8]">ecb.europa.eu · </span>
                  <span className="rounded bg-[rgba(191,138,85,0.2)] px-1 text-[#f1e6d2]">
                    key rates steer financing conditions
                  </span>
                  …
                </div>
                <div>
                  <span className="text-[#a8bd84]">03</span>{' '}
                  <span className="text-[#d7cfb8]">bis.org · transmission to </span>
                  <span className="rounded bg-[rgba(191,138,85,0.2)] px-1 text-[#f1e6d2]">aggregate demand</span>…
                </div>
                <div className="my-3 h-px bg-[#2c3522]" />
                <div className="text-[#7d8669]">3 sources · 0 external calls · 41ms rerank</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===================== CLOSING CTA ===================== */}
      <section className="relative overflow-hidden px-6 py-32 text-center" style={{ background: 'linear-gradient(160deg, #243019, #141d0f)' }}>
        <div
          className="pointer-events-none absolute left-1/2 top-0 h-72 w-[36rem] -translate-x-1/2 rounded-full opacity-50 blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(191,138,85,0.28), transparent 70%)' }}
        />
        <div className="reveal relative mx-auto max-w-2xl">
          <p className="mb-5 font-mono text-xs uppercase tracking-[0.24em] text-accent">Get started</p>
          <h2 className="text-4xl font-medium tracking-[-0.02em] text-[#f6ecd8] sm:text-5xl" style={{ lineHeight: 1.08 }}>
            Bring neural search to your field.
          </h2>
          <p className="mx-auto mt-5 max-w-md text-lg leading-relaxed text-[#cabfa6]">
            Grounded in a corpus you trust. Request early access for your team.
          </p>
          <button
            type="button"
            onClick={enterApp}
            className="mt-9 rounded-lg bg-accent px-8 py-3.5 text-sm font-semibold text-on-accent transition-transform duration-200 hover:scale-[1.03]"
          >
            Enter Noscia
          </button>
        </div>
      </section>

      <footer className="border-t border-line bg-bg px-8 py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 font-mono text-xs text-dim">
          <span className="font-semibold tracking-[0.18em] text-muted">NOSCIA</span>
          <span className="ml-auto">© 2026</span>
        </div>
      </footer>
    </div>
  )
}

const CARDS = [
  {
    icon: '◳',
    iconColor: 'var(--color-accent)',
    glow: 'radial-gradient(circle, rgba(191,138,85,0.16), transparent 70%)',
    title: 'Cited, not guessed',
    body: 'Hybrid dense and BM25 retrieval over your index, reranked with a cross-encoder. Each result carries the source passage and a link. Evidence or nothing.',
  },
  {
    icon: '◧',
    iconColor: 'var(--color-ok)',
    glow: 'radial-gradient(circle, rgba(107,122,82,0.18), transparent 70%)',
    title: 'Ten verticals, one click',
    body: 'ESG, economics, healthcare, energy and more, each its own authoritative corpus, embedded on demand. Switch instantly; nothing bleeds across fields.',
  },
  {
    icon: '⌂',
    iconColor: 'var(--color-accent-2)',
    glow: 'radial-gradient(circle, rgba(176,124,69,0.16), transparent 70%)',
    title: 'Yours to host',
    body: 'Runs in Docker behind your SSO. Index-only by design: queries and data never leave your network. Bring your own key only for optional reasoning.',
  },
]

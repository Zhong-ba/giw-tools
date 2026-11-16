// Hovering the logo spins it up; at top speed each tool icon turns into a spinning Painmelo in turn,
// and once they are all at top speed the main area erupts. Leaving undoes it all in reverse order.
const MAX_SPEED = 2880
const TOP_SPEED = MAX_SPEED * 0.97
const BOOST_SECONDS = 0.65
// Logistic growth: starts gently, accelerates, then eases into top speed.
const accelerate = (speed: number, dt: number) => Math.min(MAX_SPEED, speed + 2.2 * (speed + 60) * (1 - speed / MAX_SPEED) * dt)
const SPIN_UP = (() => {
  let speed = 0
  let time = 0
  while (speed < TOP_SPEED) { speed = accelerate(speed, 1 / 120); time += 1 / 120 }
  return time
})()
// From the logo reaching top speed until the last tool does, regardless of how many tools there are
// (the time four tools took when each waited for the previous one to reach top speed).
const TOOL_PHASE = 4 * SPIN_UP
const rand = (min: number, max: number) => min + Math.random() * (max - min)
const pick = <T>(items: readonly T[]) => items[Math.floor(Math.random() * items.length)]

class Spinner {
  img: HTMLImageElement
  angle = 0
  speed = 0
  mode: 'up' | 'hold' | 'down' = 'up'
  from = 0
  release = 0
  duration = 1
  elapsed = 0
  constructor(img: HTMLImageElement) { this.img = img }
  get top() { return this.speed >= TOP_SPEED }
  boost() {
    this.mode = 'up'
    for (let time = 0; time < BOOST_SECONDS; time += 1 / 120) {
      this.speed = accelerate(this.speed, Math.min(1 / 120, BOOST_SECONDS - time))
    }
  }
  hold() { if (this.mode === 'up') this.mode = 'hold' }
  down() {
    if (this.mode === 'down') return
    this.mode = 'down'
    const target = Math.ceil((this.angle + Math.max(this.speed * 0.6, 30)) / 360) * 360
    this.from = this.angle
    this.release = Math.max(this.speed, 60)
    this.duration = 3 * (target - this.angle) / this.release
    this.elapsed = 0
  }
  /** Advances the spin and returns true once it has come to rest upright. */
  step(dt: number) {
    if (this.mode === 'down') {
      // Speed falls as (1 - s)^2, so velocity and deceleration both reach zero upright.
      this.elapsed += dt
      const s = Math.min(1, this.elapsed / this.duration)
      this.speed = this.release * (1 - s) ** 2
      this.angle = this.from + this.release * this.duration * (1 - (1 - s) ** 3) / 3
      if (s === 1) {
        this.img.style.rotate = ''
        return true
      }
    } else {
      if (this.mode === 'up') this.speed = accelerate(this.speed, dt)
      this.angle += this.speed * dt
    }
    this.img.style.rotate = `${this.angle % 360}deg`
    return false
  }
}

const meloImage = new Image()
meloImage.src = '/painmelo.png'
const sprites: HTMLCanvasElement[] = []
const getSprites = () => {
  if (sprites.length || !meloImage.complete || !meloImage.naturalWidth) return sprites
  for (let hue = 0; hue < 360; hue += 40) {
    const sprite = document.createElement('canvas')
    sprite.width = 148
    sprite.height = 160
    const context = sprite.getContext('2d')
    if (!context) continue
    context.filter = `hue-rotate(${hue}deg)`
    context.drawImage(meloImage, 0, 0, sprite.width, sprite.height)
    sprites.push(sprite)
  }
  return sprites
}

type Kind = 'bounce' | 'orbit' | 'wave' | 'comet' | 'pulse' | 'flip' | 'spiral' | 'drunk' | 'conga' | 'row' | 'rain' | 'write'
type Point = [number, number]
const arc = (cx: number, cy: number, r: number, from: number, to: number): Point[] =>
  Array.from({ length: 33 }, (_, i) => { const a = from + (to - from) * i / 32; return [cx + r * Math.cos(a), cy + r * Math.sin(a)] })
// "PAIN" in print-handwriting stroke order, in units of the letter height (y points down).
// Each letter is its width, the gap after it and its strokes, drawn in order with the pen lifted between them.
// P-A is kerned tighter since A's leg slants away from P's bowl.
const PAIN: [number, number, Point[][]][] = [
  [0.55, 0.1, [[[0, 0], [0, 1]], [[0, 0], ...arc(0.3, 0.25, 0.25, -Math.PI / 2, Math.PI / 2), [0, 0.5]]]],
  [0.7, 0.3, [[[0.35, 0], [0, 1]], [[0.35, 0], [0.7, 1]], [[0.133, 0.62], [0.567, 0.62]]]],
  [0, 0.3, [[[0, 0], [0, 1]]]],
  [0.6, 0, [[[0, 0], [0, 1]], [[0, 0], [0.6, 1]], [[0.6, 1], [0.6, 0]]]],
]
/** Evenly spaced points along a polyline, `step` apart (both ends included). */
const resample = (line: Point[], step: number): Point[] => {
  const lengths = line.slice(1).map((point, i) => Math.hypot(point[0] - line[i][0], point[1] - line[i][1]))
  const total = lengths.reduce((sum, length) => sum + length, 0)
  const count = Math.max(1, Math.round(total / step))
  const points: Point[] = []
  for (let n = 0, segment = 0, start = 0; n <= count; n++) {
    const distance = total * n / count
    while (segment < lengths.length - 1 && start + lengths[segment] < distance) start += lengths[segment++]
    const s = lengths[segment] ? Math.min(1, (distance - start) / lengths[segment]) : 0
    const [a, b] = [line[segment], line[segment + 1]]
    points.push([a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s])
  }
  return points
}
type Melo = {
  kind: Kind, x: number, y: number, vx: number, vy: number, size: number, angle: number, spin: number, hue: number,
  t: number, life: number, a: number, b: number, c: number, squash: number, trail: number[],
}
type Bit = { x: number, y: number, vx: number, vy: number, rot: number, vr: number, w: number, h: number, color: string, round: boolean, sway: number }
const POPULATION: [Kind, number][] = [['bounce', 14], ['orbit', 6], ['wave', 5], ['comet', 3], ['pulse', 2], ['flip', 5], ['spiral', 4], ['drunk', 4]]
const COLORS = ['#ff4d6d', '#ffd23f', '#3bceac', '#4cc9f0', '#7b61ff', '#ff8c42', '#f15bb5', '#9ef01a', '#ffffff']

class Party {
  canvas = document.createElement('canvas')
  context = this.canvas.getContext('2d')
  main = document.querySelector<HTMLElement>('main')
  melos: Melo[] = []
  bits: Bit[] = []
  level = 0
  time = 0
  width = 0
  height = 0
  left = 0
  top = 0
  spawnTimer = 0
  cannonTimer = 0.4
  rowTimer = 0.8
  writeTimer = rand(1.5, 3)
  rainTimer = 0
  jolt = 0
  flash = 0

  constructor(origins: DOMRect[]) {
    this.canvas.className = 'party-layer'
    this.canvas.setAttribute('aria-hidden', 'true')
    document.body.append(this.canvas)
    document.body.classList.add('party-time')
    this.resize()
    // Kick off with every tool icon launching a bouncing Painmelo and a burst of confetti.
    for (const rect of origins) {
      const x = rect.left + rect.width / 2 - this.left, y = rect.top + rect.height / 2 - this.top
      for (let i = 0; i < 4; i++) this.melos.push({ ...this.spawn('bounce'), x, y, vx: rand(-700, 700), vy: rand(-1300, -600) })
      this.burst(x, y, 50, 900)
    }
  }

  resize() {
    const shell = document.querySelector('.main-shell')?.getBoundingClientRect()
    const left = Math.max(0, shell?.left ?? 0), top = Math.max(0, shell?.top ?? 0)
    const width = Math.max(1, window.innerWidth - left), height = Math.max(1, window.innerHeight - top)
    if (width === this.width && height === this.height && left === this.left && top === this.top) return
    Object.assign(this, { width, height, left, top })
    const ratio = window.devicePixelRatio || 1
    this.canvas.style.left = `${left}px`
    this.canvas.style.top = `${top}px`
    this.canvas.style.width = `${width}px`
    this.canvas.style.height = `${height}px`
    this.canvas.width = Math.round(width * ratio)
    this.canvas.height = Math.round(height * ratio)
    this.context?.setTransform(ratio, 0, 0, ratio, 0, 0)
  }

  spawn(kind: Kind): Melo {
    const { width: w, height: h } = this
    const melo: Melo = {
      kind, x: rand(0, w), y: rand(0, h), vx: 0, vy: 0, size: rand(34, 64), angle: rand(0, 360), spin: rand(-900, 900),
      hue: Math.floor(rand(0, 9)), t: rand(0, 10), life: rand(6, 14), a: 0, b: 0, c: 0, squash: 1, trail: [],
    }
    if (kind === 'bounce') Object.assign(melo, { y: rand(-80, h * 0.3), vx: rand(-500, 500), vy: rand(-900, -200) })
    else if (kind === 'orbit') Object.assign(melo, { a: rand(w * 0.2, w * 0.8), b: rand(h * 0.2, h * 0.8), c: rand(60, 190), spin: pick([-1, 1]) * rand(2, 5) })
    else if (kind === 'wave') {
      const direction = pick([-1, 1])
      Object.assign(melo, { x: direction > 0 ? -70 : w + 70, vx: direction * rand(260, 650), a: rand(60, h - 60), b: rand(40, 170), c: rand(2, 7), life: Infinity })
    } else if (kind === 'comet') {
      const edge = Math.floor(rand(0, 4))
      melo.x = edge === 0 ? -60 : edge === 1 ? w + 60 : rand(0, w)
      melo.y = edge === 2 ? -60 : edge === 3 ? h + 60 : rand(0, h)
      const angle = Math.atan2(rand(h * 0.2, h * 0.8) - melo.y, rand(w * 0.2, w * 0.8) - melo.x), speed = rand(1200, 2100)
      Object.assign(melo, { vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, size: rand(44, 74), spin: rand(1500, 3000), life: Infinity })
    } else if (kind === 'pulse') Object.assign(melo, { x: rand(w * 0.15, w * 0.85), y: rand(h * 0.15, h * 0.85), size: rand(90, 160), life: rand(5, 9) })
    else if (kind === 'flip') Object.assign(melo, { vx: pick([-1, 1]) * rand(150, 380), vy: pick([-1, 1]) * rand(150, 380), size: rand(44, 74), spin: 0 })
    else if (kind === 'spiral') Object.assign(melo, { a: w / 2, b: h / 2, c: rand(3, 7) * pick([-1, 1]), t: 0, size: rand(26, 48), life: Infinity })
    else if (kind === 'drunk') Object.assign(melo, { vx: rand(-200, 200), vy: rand(-200, 200) })
    else if (kind === 'rain') Object.assign(melo, { y: -60, vx: rand(-60, 60), vy: rand(250, 650), size: rand(26, 54), spin: rand(-500, 500), c: rand(0, 6), life: Infinity })
    return melo
  }

  /** Lines up Painmelos that appear one after another across the screen, hold, then pop in the same order. */
  row() {
    const { width: w, height: h } = this
    const size = rand(36, 54), spacing = size * 1.15, count = Math.max(1, Math.floor((w - 20) / spacing))
    const direction = pick([-1, 1]), y = rand(size, h - size), hue = Math.floor(rand(0, 9)), drawTime = rand(0.04, 0.08)
    for (let i = 0; i < count; i++) {
      const offset = (w - count * spacing) / 2 + spacing * (i + 0.5)
      this.melos.push({
        ...this.spawn('row'), x: direction > 0 ? offset : w - offset, b: y, y, size, spin: 0, angle: 0,
        hue: (hue + i) % 9, t: -i * drawTime, c: i, life: count * drawTime + rand(0.8, 1.6) + i * 0.05,
      })
    }
  }

  /** Writes "PAIN" in Painmelos, one at a time in stroke order, holds it, then pops them in a loose stroke order. */
  write() {
    const { width: w, height: h } = this
    const span = PAIN.reduce((sum, [width, gap]) => sum + width + gap, 0)
    // Same Painmelo size and spacing as the row effect; the letters are 5-8 Painmelos tall, as space allows.
    const size = rand(36, 54), spacing = size * 1.15
    const height = Math.min(spacing * rand(5, 8), (w - size * 2) / span, h - size * 2)
    const step = spacing / height
    const left = rand(size, Math.max(size, w - span * height - size)), top = rand(size, Math.max(size, h - height - size))
    const hue = Math.floor(rand(0, 9)), drawTime = rand(0.05, 0.08)
    const points: { x: number, y: number, start: number }[] = []
    let x = 0, clock = 0
    for (const [width, gap, strokes] of PAIN) {
      for (const stroke of strokes) {
        for (const [px, py] of resample(stroke, step)) {
          const point = { x: left + (x + px) * height, y: top + py * height, start: clock }
          // Strokes that begin where another ended (A's apex, N's corners) don't stack a second Painmelo.
          if (points.some(other => Math.hypot(other.x - point.x, other.y - point.y) < size * 0.5)) continue
          points.push(point)
          clock += drawTime
        }
        clock += 0.15
      }
      x += width + gap
      clock += 0.15
    }
    points.forEach((point, i) => this.melos.push({
      ...this.spawn('write'), x: point.x, y: point.y, b: point.y, size, spin: 0, angle: 0,
      // The row effect's wave, travelling along the word from left to right, and its loosely ordered pops.
      hue: (hue + i) % 9, t: -point.start, c: (point.x - left) / spacing, life: clock + rand(0.8, 1.6) + point.start * 0.1,
    }))
  }

  burst(x: number, y: number, count: number, force: number, direction?: number) {
    for (let i = 0; i < count && this.bits.length < 1400; i++) {
      const angle = direction === undefined ? rand(0, Math.PI * 2) : direction + rand(-0.45, 0.45), speed = rand(force * 0.3, force)
      this.bits.push({
        x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, rot: rand(0, Math.PI * 2), vr: rand(-14, 14),
        w: rand(5, 11), h: rand(3, 7), color: pick(COLORS), round: Math.random() < 0.3, sway: rand(1, 4),
      })
    }
  }

  /** Moves a Painmelo and returns false once it should leave the party. */
  move(melo: Melo, dt: number) {
    const { width: w, height: h } = this
    const half = melo.size / 2
    melo.t += dt
    melo.life -= dt
    melo.squash += (1 - melo.squash) * Math.min(1, dt * 10)
    switch (melo.kind) {
      case 'bounce':
        melo.vy += 1500 * dt
        melo.x += melo.vx * dt
        melo.y += melo.vy * dt
        melo.angle += melo.spin * dt
        if (melo.x < half || melo.x > w - half) { melo.vx *= -0.95; melo.x = Math.min(w - half, Math.max(half, melo.x)); melo.spin *= -1 }
        if (melo.y > h - half) {
          melo.y = h - half
          melo.vy = Math.random() < 0.25 ? -rand(1100, 1600) : -Math.abs(melo.vy) * 0.85
          melo.squash = 0.55
          if (Math.abs(melo.vy) > 500) this.burst(melo.x, h - 4, 8, 380, -Math.PI / 2)
        }
        break
      case 'orbit':
        melo.a += Math.sin(this.time * 0.7 + melo.c) * 80 * dt
        melo.x = melo.a + Math.cos(melo.t * melo.spin) * melo.c * (1 + 0.3 * Math.sin(melo.t * 3))
        melo.y = melo.b + Math.sin(melo.t * melo.spin) * melo.c * 0.75
        melo.angle = melo.t * melo.spin * 57.3 + 90
        break
      case 'wave':
        melo.x += melo.vx * dt
        melo.y = melo.a + Math.sin(melo.t * melo.c) * melo.b
        melo.angle = Math.sin(melo.t * melo.c) * 35
        return melo.x > -100 && melo.x < w + 100
      case 'comet':
        melo.x += melo.vx * dt
        melo.y += melo.vy * dt
        melo.angle += melo.spin * dt
        melo.trail.unshift(melo.x, melo.y, melo.angle)
        melo.trail.length = Math.min(melo.trail.length, 36)
        return melo.x > -200 && melo.x < w + 200 && melo.y > -200 && melo.y < h + 200
      case 'pulse':
        melo.angle = Math.sin(melo.t * 6) * 25
        melo.hue = Math.floor(melo.t * 12) % 9
        break
      case 'flip':
        melo.x += melo.vx * dt
        melo.y += melo.vy * dt
        if (melo.x < half || melo.x > w - half) { melo.vx *= -1; melo.x = Math.min(w - half, Math.max(half, melo.x)); melo.hue = (melo.hue + 1) % 9 }
        if (melo.y < half || melo.y > h - half) { melo.vy *= -1; melo.y = Math.min(h - half, Math.max(half, melo.y)); melo.hue = (melo.hue + 1) % 9 }
        break
      case 'spiral': {
        const radius = melo.t * 140
        melo.x = melo.a + Math.cos(melo.t * melo.c) * radius
        melo.y = melo.b + Math.sin(melo.t * melo.c) * radius
        melo.angle = melo.t * melo.c * 57.3
        melo.size += 12 * dt
        return radius < Math.hypot(w, h)
      }
      case 'drunk':
        melo.vx += rand(-1800, 1800) * dt
        melo.vy += rand(-1800, 1800) * dt
        melo.vx *= 0.97
        melo.vy *= 0.97
        melo.x = Math.min(w - half, Math.max(half, melo.x + melo.vx * dt))
        melo.y = Math.min(h - half, Math.max(half, melo.y + melo.vy * dt))
        melo.angle += Math.sin(melo.t * 9) * 400 * dt
        if (Math.random() < dt * 0.6) {
          this.burst(melo.x, melo.y, 16, 300)
          melo.x = rand(half, w - half)
          melo.y = rand(half, h - half)
          this.burst(melo.x, melo.y, 16, 300)
        }
        break
      case 'conga': {
        const t = this.time * 1.1 - melo.c
        melo.x = w / 2 + Math.sin(t) * w * 0.38
        melo.y = h / 2 + Math.sin(t * 2) * h * 0.3
        melo.angle = Math.sin(this.time * 8 + melo.c * 4) * 30
        return true
      }
      case 'row':
      case 'write':
        melo.y = melo.b + Math.sin(this.time * 7 + melo.c * 0.6) * 7
        melo.angle = Math.sin(this.time * 7 + melo.c * 0.6) * 12
        break
      case 'rain':
        melo.vy += 400 * dt
        melo.x += (melo.vx + Math.sin(melo.t * 2 + melo.c) * 50) * dt
        melo.y += melo.vy * dt
        melo.angle += melo.spin * dt
        if (melo.y < h - half) return true
        this.burst(melo.x, h - 4, 12, 420, -Math.PI / 2)
        return false
    }
    if (melo.life > 0) return true
    if (melo.kind === 'row' || melo.kind === 'write') { this.burst(melo.x, melo.y, 18, 420); return false }
    this.burst(melo.x, melo.y, 40, 650)
    this.jolt = Math.max(this.jolt, 4)
    return false
  }

  draw(melo: Melo, sprite: HTMLCanvasElement, x: number, y: number, angle: number, alpha: number) {
    const context = this.context
    if (!context) return
    let scaleX = 1, scaleY = 1
    if (melo.kind === 'pulse') scaleX = scaleY = 1 + 0.45 * Math.sin(melo.t * 9)
    if (melo.kind === 'flip') scaleX = Math.cos(melo.t * 9)
    if (melo.kind === 'wave') scaleX = Math.sign(melo.vx)
    if (melo.kind === 'bounce') { scaleY = melo.squash; scaleX = 2 - melo.squash }
    if (melo.kind === 'row' || melo.kind === 'write') {
      if (melo.t < 0) return
      // Overshooting pop-in, so each Painmelo in the row lands with a little boing.
      const s = Math.min(1, melo.t / 0.25) - 1
      scaleX = scaleY = 1 + 2.70158 * s ** 3 + 1.70158 * s ** 2
    }
    const height = melo.size * 1.08
    context.save()
    context.globalAlpha = alpha
    context.translate(x, y)
    context.rotate(angle * Math.PI / 180)
    context.scale(scaleX, scaleY)
    context.drawImage(sprite, -melo.size / 2, -height / 2, melo.size, height)
    context.restore()
  }

  /** Advances the party and returns true once it has fully faded out. */
  step(dt: number, on: boolean) {
    this.level = on ? Math.min(1, this.level + dt * 2.5) : Math.max(0, this.level - dt * 2)
    this.canvas.style.opacity = String(this.level)
    if (!on && this.level === 0) {
      this.canvas.remove()
      document.body.classList.remove('party-time')
      if (this.main) { this.main.style.translate = ''; this.main.style.rotate = '' }
      return true
    }
    this.resize()
    this.time += dt
    const { width: w, height: h, context } = this
    if (on) {
      this.spawnTimer -= dt
      if (this.spawnTimer <= 0) {
        this.spawnTimer = 0.12
        const missing = POPULATION.filter(([kind, count]) => this.melos.filter(melo => melo.kind === kind).length < count)
        if (missing.length) this.melos.push(this.spawn(pick(missing)[0]))
        if (!this.melos.some(melo => melo.kind === 'conga'))
          for (let i = 0; i < 9; i++) this.melos.push({ ...this.spawn('conga'), c: i * 0.32, size: 58 - i * 3.5, hue: i % 9 })
      }
      this.rowTimer -= dt
      if (this.rowTimer <= 0) { this.rowTimer = rand(1.2, 2.6); this.row() }
      // Only one PAIN at a time; the next is written a little after the last one has popped.
      if (!this.melos.some(melo => melo.kind === 'write')) {
        this.writeTimer -= dt
        if (this.writeTimer <= 0) { this.writeTimer = rand(1.5, 3.5); this.write() }
      }
      this.rainTimer -= dt
      if (this.rainTimer <= 0) { this.rainTimer = rand(0.04, 0.12); this.melos.push(this.spawn('rain')) }
      for (let i = Math.floor(dt * 220 + Math.random()); i > 0; i--) this.burst(rand(0, w), -10, 1, 160, Math.PI / 2)
      this.cannonTimer -= dt
      if (this.cannonTimer <= 0) {
        this.cannonTimer = rand(0.5, 1.2)
        const fromLeft = Math.random() < 0.5
        this.burst(fromLeft ? 0 : w, h, 90, 1500, fromLeft ? -Math.PI / 3 : -Math.PI * 2 / 3)
        if (Math.random() < 0.4) this.burst(fromLeft ? w : 0, h, 90, 1500, fromLeft ? -Math.PI * 2 / 3 : -Math.PI / 3)
        this.jolt = 10
        this.flash = 0.18
      }
    }
    this.melos = this.melos.filter(melo => this.move(melo, dt))
    this.bits = this.bits.filter(bit => {
      bit.vy += 620 * dt
      bit.vx *= 1 - 1.6 * dt
      bit.vy *= 1 - 1.2 * dt
      bit.x += (bit.vx + Math.sin(this.time * bit.sway * 2 + bit.rot) * 60) * dt
      bit.y += bit.vy * dt
      bit.rot += bit.vr * dt
      return bit.y < h + 20 && bit.x > -40 && bit.x < w + 40
    })
    this.jolt = Math.max(0, this.jolt - dt * 25)
    this.flash = Math.max(0, this.flash - dt * 0.6)
    if (this.main) {
      const shake = this.level * (1.5 + this.jolt)
      this.main.style.translate = `${rand(-shake, shake)}px ${rand(-shake, shake)}px`
      this.main.style.rotate = `${rand(-0.08, 0.08) * this.jolt}deg`
    }
    if (!context) return false
    context.clearRect(0, 0, w, h)
    // Disco beams sweeping from the top.
    context.save()
    context.globalCompositeOperation = 'lighter'
    const reach = Math.hypot(w, h) * 1.5
    for (let i = 0; i < 7; i++) {
      const angle = Math.PI / 2 + Math.sin(this.time * 0.9 + i * 1.7) * 1.1
      context.fillStyle = `hsla(${(this.time * 120 + i * 51) % 360}, 95%, 60%, 0.08)`
      context.beginPath()
      context.moveTo(w * (i + 0.5) / 7, -20)
      context.lineTo(w * (i + 0.5) / 7 + Math.cos(angle - 0.08) * reach, Math.sin(angle - 0.08) * reach)
      context.lineTo(w * (i + 0.5) / 7 + Math.cos(angle + 0.08) * reach, Math.sin(angle + 0.08) * reach)
      context.fill()
    }
    if (this.flash) { context.fillStyle = `rgba(255, 255, 255, ${this.flash})`; context.fillRect(0, 0, w, h) }
    context.restore()
    const images = getSprites()
    if (images.length) for (const melo of this.melos) {
      const sprite = images[melo.hue % images.length]
      for (let i = melo.trail.length - 3; i > 0; i -= 6) this.draw(melo, images[(melo.hue + i / 3) % images.length], melo.trail[i], melo.trail[i + 1], melo.trail[i + 2], 0.5 * (1 - i / melo.trail.length))
      this.draw(melo, sprite, melo.x, melo.y, melo.angle, 1)
    }
    for (const bit of this.bits) {
      context.save()
      context.translate(bit.x, bit.y)
      context.rotate(bit.rot)
      context.scale(1, Math.cos(bit.rot * 1.7))
      context.fillStyle = bit.color
      if (bit.round) { context.beginPath(); context.arc(0, 0, bit.h / 1.6, 0, Math.PI * 2); context.fill() }
      else context.fillRect(-bit.w / 2, -bit.h / 2, bit.w, bit.h)
      context.restore()
    }
    return false
  }
}

// The favicon mirrors the logo's rotation; redraws are throttled since each one re-encodes a PNG.
const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
const faviconHref = favicon?.getAttribute('href') ?? ''
const faviconCanvas = document.createElement('canvas')
faviconCanvas.width = faviconCanvas.height = 64
let faviconDrawn = 0
const drawFavicon = (angle: number | null, now: number) => {
  if (!favicon) return
  if (angle === null) { favicon.href = faviconHref; return }
  const context = faviconCanvas.getContext('2d')
  if (now - faviconDrawn < 40 || !context || !meloImage.complete || !meloImage.naturalWidth) return
  faviconDrawn = now
  context.clearRect(0, 0, 64, 64)
  context.save()
  context.translate(32, 32)
  context.rotate(angle * Math.PI / 180)
  // Shrink a little so the corners stay inside the square while rotating.
  context.drawImage(meloImage, -27, -29, 54, 58)
  context.restore()
  favicon.href = faviconCanvas.toDataURL('image/png')
}

let logo: Spinner | null = null
const tools: Spinner[] = []
let party: Party | null = null
let hovered = false
let partyAllowed = false
let last = 0
// Seconds since the logo reached top speed during the current hover.
let toolClock: number | null = null

const activate = (img: HTMLImageElement) => {
  // Drop the hover animation so only the scripted rotation applies, and so it restarts upright later.
  img.style.animation = 'none'
  img.parentElement?.classList.add('partying')
  return new Spinner(img)
}
const deactivate = (img: HTMLImageElement) => {
  img.parentElement?.classList.remove('partying')
  setTimeout(() => { if (!tools.some(tool => tool.img === img)) img.style.animation = '' }, 350)
}

const frame = (now: number) => {
  const dt = Math.min((now - last) / 1000, 0.05)
  last = now
  if (!logo) return
  const spinners = [logo, ...tools]
  if (hovered) {
    for (const spinner of spinners) spinner.mode = 'up'
    if (logo.top && !party && partyAllowed) {
      // Tool starts are spread so the last one reaches top speed TOOL_PHASE after the logo did.
      const images = Array.from(document.querySelectorAll<HTMLImageElement>('.tool-melo'))
      const interval = images.length > 1 ? Math.max(0, TOOL_PHASE - SPIN_UP) / (images.length - 1) : 0
      // Resuming mid-ramp-down: the next tool follows one interval after the ones still spinning.
      toolClock = toolClock === null ? Math.max(0, tools.length - 1) * interval : toolClock + dt
      while (tools.length < images.length && toolClock >= tools.length * interval) {
        const next = images.find(img => !tools.some(tool => tool.img === img))
        if (!next) break
        tools.push(activate(next))
      }
      if (tools.length >= images.length && tools.every(tool => tool.top)) {
        party = new Party(tools.map(tool => tool.img.getBoundingClientRect()))
      }
    }
  } else if (party) {
    toolClock = null
    for (const spinner of spinners) spinner.hold()
  } else {
    toolClock = null
    for (const spinner of spinners) spinner.hold()
    spinners[spinners.length - 1].down()
  }
  if (party?.step(dt, hovered)) party = null
  if (logo.step(dt)) { logo = null; drawFavicon(null, now); return }
  drawFavicon(logo.angle, now)
  for (const tool of [...tools]) if (tool.step(dt)) {
    tools.splice(tools.indexOf(tool), 1)
    deactivate(tool.img)
  }
  requestAnimationFrame(frame)
}

/** Spins the logo; the tool icons and the party only follow when `allowParty` (the Tools page is open). */
export const startParty = (img: HTMLImageElement | null, allowParty: boolean) => {
  if (!img || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  hovered = true
  partyAllowed = allowParty
  if (logo) return
  logo = new Spinner(img)
  last = performance.now()
  requestAnimationFrame(frame)
}
export const stopParty = () => { hovered = false }

const clickConfetti = (img: HTMLImageElement) => {
  const bounds = img.getBoundingClientRect()
  const burst = document.createElement('div')
  burst.className = 'boost-confetti'
  burst.setAttribute('aria-hidden', 'true')
  burst.style.left = `${bounds.left + bounds.width / 2}px`
  burst.style.top = `${bounds.top + bounds.height / 2}px`
  document.body.append(burst)
  for (let i = 0; i < 18; i++) {
    const bit = document.createElement('span')
    bit.style.backgroundColor = pick(COLORS)
    burst.append(bit)
    const angle = rand(-Math.PI, 0), distance = rand(45, 110), rotation = rand(-240, 240)
    const x = Math.cos(angle) * distance, y = Math.sin(angle) * distance
    bit.animate([
      { transform: 'translate(0, 0) rotate(0deg)', opacity: 1 },
      { transform: `translate(${x * 0.6}px, ${y}px) rotate(${rotation * 0.5}deg)`, opacity: 1, offset: 0.5 },
      { transform: `translate(${x}px, ${y + 60}px) rotate(${rotation}deg)`, opacity: 0 },
    ], { duration: rand(550, 800), easing: 'ease-out', fill: 'forwards' })
  }
  setTimeout(() => burst.remove(), 850)
}

/** Advances the current ramp without jumping the icons' rotation angles. */
export const boostParty = (img: HTMLImageElement | null, allowParty: boolean) => {
  if (!img) return
  img.closest('.brand')?.animate([
    { backgroundColor: 'transparent' },
    { backgroundColor: '#7aaaff26', offset: 0.2 },
    { backgroundColor: 'transparent' },
  ], { duration: 350, easing: 'ease-out' })
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  clickConfetti(img)
  img.animate([
    { scale: '1' }, { scale: '1.22', offset: 0.3 }, { scale: '0.96', offset: 0.7 }, { scale: '1' },
  ], { duration: 300, easing: 'ease-out' })
  startParty(img, allowParty)
  if (party) return
  for (const spinner of [logo, ...tools]) spinner?.boost()
  if (toolClock !== null) toolClock += BOOST_SECONDS
}

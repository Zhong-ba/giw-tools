import { createLucideIcon } from 'lucide-react'

// Custom glyphs drawn on Lucide's 24px grid so they inherit its stroke styling.

export const CrescentBird = createLucideIcon('CrescentBird', [
  ['path', { d: 'M6.85 11.25C7.05 9.25 8.26 8 9.88 8C10.69 4.75 12.91 3 15.53 3C19.37 3 22 7.25 22 12.75C22 14.75 21.39 15.75 21.39 16.75C22.2 18 22 19.75 20.99 21', key: 'body' }],
  ['path', { d: 'M6.85 13.25C7.25 14.5 8.06 15.26 8.87 15.5', key: 'chin' }],
  ['path', { d: 'M6.85 11.25C5.23 9 3.41 8.5 2 9.75', key: 'beak-top' }],
  ['path', { d: 'M6.85 13.25C5.03 14.75 3.21 14.5 2 13.25', key: 'beak-bottom' }],
  ['circle', { cx: '8.87', cy: '11.87', r: '0.74', key: 'eye' }],
  ['path', { d: 'M8.87 15.5C10.48 14.75 11.49 12.75 11.49 10.5C13.31 12.75 14.32 16.51 14.52 21H8.26Z', key: 'drape' }],
  ['path', { d: 'M2.81 21h18.18', key: 'wall' }],
  ['path', { d: 'M17.55 15.26a1.62 2.01 0 1 1 1.62 -2.01', key: 'swirl' }],
])

export const BearFace = createLucideIcon('BearFace', [
  ['path', { d: 'M3.36 21.73C2.5 18.49 2.06 14.82 2.71 12.01C3.14 10.5 3.58 9.63 4.44 8.98C2.71 7.47 2.5 4.45 4.44 2.94C6.38 1.64 8.76 2.5 9.41 4.88C11.14 4.23 12.86 4.23 14.59 4.88C15.24 2.5 17.62 1.64 19.56 2.94C21.5 4.45 21.29 7.47 19.56 8.98C20.42 9.63 20.86 10.5 21.29 12.01C21.94 14.82 21.5 18.49 20.64 21.73', key: 'head' }],
  ['path', { d: 'M7.9 8.12h.01', key: 'eye-left' }],
  ['path', { d: 'M16.1 7.9h.01', key: 'eye-right' }],
  ['path', { d: 'M8.8 14.64C6.6 15.9 4.87 15.03 4.87 13.09C4.87 11.14 6.6 10.28 8.54 10.71C10 11.04 10.92 11.58 12 11.58C13.08 11.58 14 11.04 15.46 10.71C17.4 10.28 19.13 11.14 19.13 13.09C19.13 15.03 17.4 15.9 15.2 14.64', key: 'mask' }],
  ['rect', { x: '8.11', y: '13.95', width: '7.78', height: '4.75', rx: '2.38', key: 'muzzle' }],
])

export const HornedMask = createLucideIcon('HornedMask', [
  ['path', { d: 'M12 22.83C6.85 22.83 3.99 18.82 3.99 14.24C3.99 11.95 4.68 10.12 5.82 8.75C3.53 7.37 2.39 4.63 3.18 1.88C4.44 1.65 5.36 2.22 5.82 3.48C6.28 5.08 6.96 6.23 7.88 6.69C9.14 6.01 10.52 5.66 12 5.66C13.48 5.66 14.86 6.01 16.12 6.69C17.04 6.23 17.72 5.08 18.18 3.48C18.64 2.22 19.56 1.65 20.82 1.88C21.61 4.63 20.47 7.37 18.18 8.75C19.32 10.12 20.01 11.95 20.01 14.24C20.01 18.82 17.15 22.83 12 22.83Z', key: 'mask' }],
  ['path', { d: 'M12 9.21L13.6 11.73L12 14.24L10.4 11.73Z', key: 'diamond' }],
  ['path', { d: 'M8.8 9.44C7.19 11.5 8.11 13.79 10.4 15.39C11.31 16.08 11.54 16.99 11.43 17.91', key: 'wing-left' }],
  ['path', { d: 'M15.2 9.44C16.81 11.5 15.89 13.79 13.6 15.39C12.69 16.08 12.46 16.99 12.57 17.91', key: 'wing-right' }],
  ['path', { d: 'M9.02 17.91L12 20.42L14.98 17.91', key: 'chevron' }],
])

// The Spiral Abyss: an eye at the bottom of two widening staircase arms.
export const AbyssSpiral = createLucideIcon('AbyssSpiral', [
  ['circle', { cx: '12', cy: '12', r: '2.4', key: 'eye' }],
  ['path', { d: 'M12 6.8A5.85 5.85 0 0 1 18.5 12A7.15 7.15 0 0 1 12 19.8A8.45 8.45 0 0 1 2.9 12A9.75 9.75 0 0 1 12 1.6', key: 'arm-1' }],
  ['path', { d: 'M12 17.2A5.85 5.85 0 0 1 5.5 12A7.15 7.15 0 0 1 12 4.2A8.45 8.45 0 0 1 21.1 12A9.75 9.75 0 0 1 12 22.4', key: 'arm-2' }],
])

// Stygian Onslaught: a cupped, spiky lotus bloom over flared petals.
export const StygianLotus = createLucideIcon('StygianLotus', [
  ['path', { d: 'M7.6 13.2C6.7 10 7 6.6 8.4 3.8L10.3 6.4L12 3.2L13.7 6.4L15.6 3.8C17 6.6 17.3 10 16.4 13.2C14.4 15 9.6 15 7.6 13.2Z', key: 'bloom' }],
  ['path', { d: 'M10.3 6.4C10 9.2 10.6 11.8 12 14.2C13.4 11.8 14 9.2 13.7 6.4', key: 'seam' }],
  ['path', { d: 'M12 18.6C7.4 19.4 3.6 17.6 2 14.2C4 13.4 6.2 13.4 8.2 14.4', key: 'petal-left' }],
  ['path', { d: 'M12 18.6C16.6 19.4 20.4 17.6 22 14.2C20 13.4 17.8 13.4 15.8 14.4', key: 'petal-right' }],
])

// Imaginarium Theater: an open script before a diamond frame.
export const TheaterBook = createLucideIcon('TheaterBook', [
  ['path', { d: 'M7.2 5.6L12 1.2L16.8 5.6', key: 'tip-top' }],
  ['path', { d: 'M2.8 10.2L1.2 12L2.8 13.8', key: 'tip-left' }],
  ['path', { d: 'M21.2 10.2L22.8 12L21.2 13.8', key: 'tip-right' }],
  ['path', { d: 'M10.2 21.4L12 22.8L13.8 21.4', key: 'tip-bottom' }],
  ['path', { d: 'M12 8C10.3 6.6 7.6 6.1 5.6 6.6V16C7.6 15.6 10.3 16.1 12 17.5C13.7 16.1 16.4 15.6 18.4 16V6.6C16.4 6.1 13.7 6.6 12 8Z', key: 'pages' }],
  ['path', { d: 'M3.2 9.2V18.6H10.6L12 19.8L13.4 18.6H20.8V9.2', key: 'cover' }],
  ['path', { d: 'M8.8 9.6Q9 11.6 10.8 11.8Q9 12 8.8 14Q8.6 12 6.8 11.8Q8.6 11.6 8.8 9.6Z', key: 'sparkle' }],
  ['path', { d: 'M14.6 9.8L16 9.6M14.6 12.6L16 12.4', key: 'lines' }],
])

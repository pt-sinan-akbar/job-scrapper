const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

export function scrollMotion(): ScrollBehavior {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches ? 'auto' : 'smooth'
}

import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { expect, test } from 'vitest'

const readSource = (path) => readFileSync(resolve(process.cwd(), path), 'utf8')

function collectAuthoredStyles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = join(directory, entry.name)
    if (entry.isDirectory()) return collectAuthoredStyles(target)
    if (/\.(?:css|vue)$/.test(entry.name)) return [readFileSync(target, 'utf8')]
    return []
  })
}

const indexHtml = readSource('index.html')
const appSource = readSource('src/App.vue')
const baseCss = readSource('src/styles/base.css')
const tokensCss = readSource('src/styles/tokens.css')
const sidebarSource = readSource('src/components/AppSidebar.vue')
const pathFieldSource = readSource('src/components/PathField.vue')
const spotifyClientIdHelpSource = readSource('src/components/SpotifyClientIdHelp.vue')
const duplicateGroupSource = readSource('src/components/DuplicateGroupCard.vue')
const manualRelinkSource = readSource('src/components/ManualRelinkModal.vue')
const rematchSource = readSource('src/components/ReMatchModal.vue')
const settingsSource = readSource('src/screens/SettingsScreen.vue')
const allAuthoredStyles = collectAuthoredStyles(resolve(process.cwd(), 'src')).join('\n')

test('the document declares its dark-only scheme before the application entrypoint', () => {
  const declaration = indexHtml.indexOf('<meta name="color-scheme" content="dark" />')
  const entrypoint = indexHtml.indexOf('<script type="module" src="/src/main.ts"></script>')

  expect(declaration).toBeGreaterThan(-1)
  expect(entrypoint).toBeGreaterThan(-1)
  expect(declaration).toBeLessThan(entrypoint)
})

test('the inherited scrollbar enhancement uses tokens and a transparent track', () => {
  expect(baseCss).toMatch(/:root\s*\{[^}]*color-scheme:\s*dark\s*;/s)
  expect(baseCss).toMatch(
    /@supports\s*\(scrollbar-color:\s*auto\)\s*\{\s*:root\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+transparent\s*;/s,
  )
  expect(tokensCss).toMatch(/--scrollbar-thumb:\s*var\(--text-muted\)\s*;/)

  expect(allAuthoredStyles).not.toMatch(/\bscrollbar-width\s*:/)
  expect(allAuthoredStyles).not.toMatch(/::-webkit-scrollbar/)
})

test('the shell derives all top-chrome geometry from shared tokens', () => {
  expect(tokensCss).toMatch(/--top-chrome-height:\s*52px\s*;/)
  expect(tokensCss).toMatch(/--traffic-light-clearance:\s*80px\s*;/)
  expect(appSource).toContain('left: var(--traffic-light-clearance);')
  expect(appSource).toContain('height: var(--top-chrome-height);')
  expect(appSource).toContain('padding-top: var(--top-chrome-height);')
  expect(sidebarSource).toContain('padding: var(--top-chrome-height) 12px 14px;')
})

test('the drag layer stays above shell content and cannot select text', () => {
  const dragRule = appSource.match(/\.window-drag-region\s*\{([^}]*)\}/s)?.[1] ?? ''

  expect(dragRule).toMatch(/z-index:\s*1\s*;/)
  expect(dragRule).toMatch(/-webkit-user-select:\s*none\s*;/)
  expect(dragRule).toMatch(/user-select:\s*none\s*;/)
})

test('desktop chrome and action controls cannot start accidental text selection', () => {
  const controlRule =
    baseCss.match(
      /\.sidebar,\s*button,\s*a,\s*label,\s*select,\s*\[role='button'\],\s*\[role='tab'\],\s*\[role='menuitem'\],\s*\[role='option'\]\s*\{([^}]*)\}/s,
    )?.[1] ?? ''

  expect(controlRule).toMatch(/-webkit-user-select:\s*none\s*;/)
  expect(controlRule).toMatch(/user-select:\s*none\s*;/)
  expect(baseCss).not.toMatch(/(?:html|body|#app)\s*\{[^}]*user-select:\s*none\s*;/s)
})

test('useful technical values remain explicitly selectable', () => {
  expect(baseCss).toMatch(
    /input\[type='text'\],[^{]*textarea\s*\{[^}]*-webkit-user-select:\s*text\s*;[^}]*user-select:\s*text\s*;/s,
  )
  expect(pathFieldSource).toMatch(/\.full-path\s*\{[^}]*user-select:\s*text\s*;/s)
  expect(settingsSource).toMatch(/\.derived-path\s*\{[^}]*user-select:\s*text\s*;/s)
  expect(spotifyClientIdHelpSource).toMatch(/\.redirect\s*\{[^}]*user-select:\s*all\s*;/s)
  expect(duplicateGroupSource).toMatch(/\.member-title,[^{]*\{[^}]*user-select:\s*text\s*;/s)
  expect(manualRelinkSource).toMatch(/\.cand-text,[^{]*\{[^}]*user-select:\s*text\s*;/s)
  expect(rematchSource).toMatch(/\.cand-text,[^{]*\{[^}]*user-select:\s*text\s*;/s)
})

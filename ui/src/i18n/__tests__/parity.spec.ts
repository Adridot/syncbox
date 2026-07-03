import { expect, test } from 'vitest'

import { en } from '../en'
import { fr } from '../fr'

function flatKeys(node: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(node).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? flatKeys(value as Record<string, unknown>, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  )
}

test('en/fr key sets are identical (M4-PLAN §4 parity rule)', () => {
  expect(flatKeys(fr as never).sort()).toEqual(flatKeys(en).sort())
})

test('no empty translation values', () => {
  const check = (node: Record<string, unknown>, locale: string) => {
    for (const key of flatKeys(node)) {
      const value = key.split('.').reduce<unknown>(
        (acc, part) => (acc as Record<string, unknown>)[part],
        node,
      )
      expect(value, `${locale}:${key}`).toBeTruthy()
    }
  }
  check(en, 'en')
  check(fr as never, 'fr')
})

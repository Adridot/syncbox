import { expect, test } from 'vitest'

import { dots, invisibleOnlyChange, markInvisible } from '../whitespace'

test('B4: trailing / doubled / non-breaking spaces are marked; normal spaces are not', () => {
  // trailing space
  expect(markInvisible('Carole Fredericks ')).toEqual([
    { text: 'Carole Fredericks', mark: false },
    { text: ' ', mark: true },
  ])
  // doubled inner space
  expect(markInvisible('A  B')).toEqual([
    { text: 'A', mark: false },
    { text: '  ', mark: true },
    { text: 'B', mark: false },
  ])
  // NBSP
  expect(markInvisible('A B')).toEqual([
    { text: 'A', mark: false },
    { text: ' ', mark: true },
    { text: 'B', mark: false },
  ])
  // leading whitespace
  expect(markInvisible(' A')[0]).toEqual({ text: ' ', mark: true })
  // a normal single inter-word space stays unmarked
  expect(markInvisible('Daft Punk')).toEqual([{ text: 'Daft Punk', mark: false }])
})

test('B4: identical-looking rows are detected as invisible-only changes', () => {
  expect(invisibleOnlyChange('Carole Fredericks ', 'Carole Fredericks')).toBe(true)
  expect(invisibleOnlyChange('A B', 'A B')).toBe(true)
  expect(invisibleOnlyChange('A  B', 'A B')).toBe(true)
  expect(invisibleOnlyChange('DAFT PUNK', 'Daft Punk')).toBe(false)
  expect(invisibleOnlyChange('same', 'same')).toBe(false)
})

test('dots renders one visible dot per hidden character', () => {
  expect(dots('  ')).toBe('··')
  expect(dots(' ')).toBe('·')
})

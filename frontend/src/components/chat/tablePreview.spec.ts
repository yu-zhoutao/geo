import { describe, expect, it } from 'vitest'

import { parseDelimitedTablePreview } from './tablePreview'

describe('parseDelimitedTablePreview', () => {
  it('parses quoted CSV cells and limits rendered rows', () => {
    const preview = parseDelimitedTablePreview(
      'name,value\n"alpha, one",1\nbeta,2\ngamma,3\n',
      ',',
      2,
    )

    expect(preview.headers).toEqual(['name', 'value'])
    expect(preview.rows).toEqual([
      ['alpha, one', '1'],
      ['beta', '2'],
    ])
    expect(preview.truncated).toBe(true)
  })

  it('parses TSV content', () => {
    const preview = parseDelimitedTablePreview('name\tvalue\nalpha\t1\n', '\t', 10)

    expect(preview.headers).toEqual(['name', 'value'])
    expect(preview.rows).toEqual([['alpha', '1']])
    expect(preview.truncated).toBe(false)
  })
})

import type { Artifact } from '../../types'
import { artifactFormat } from './artifactPreview'

export const INLINE_TABLE_PREVIEW_MAX_ROWS = 20
export const MODAL_TABLE_PREVIEW_MAX_ROWS = 100

export type TableDelimiter = ',' | '\t'

export interface DelimitedTablePreview {
  headers: string[]
  rows: string[][]
  truncated: boolean
}

export function tableDelimiterForArtifact(artifact: Artifact): TableDelimiter {
  return artifactFormat(artifact) === 'tsv' ? '\t' : ','
}

export function parseDelimitedTablePreview(
  value: string,
  delimiter: TableDelimiter,
  maxRows: number,
): DelimitedTablePreview {
  const parsedRows = parseRows(value, delimiter, maxRows + 2)
  const [rawHeaders = [], ...rawRows] = parsedRows
  const rows = rawRows.slice(0, maxRows)
  const columnCount = Math.max(rawHeaders.length, ...rows.map((row) => row.length), 0)
  const headers = Array.from({ length: columnCount }, (_, index) => rawHeaders[index]?.trim() || `列 ${index + 1}`)

  return {
    headers,
    rows: rows.map((row) => Array.from({ length: columnCount }, (_, index) => row[index] ?? '')),
    truncated: rawRows.length > maxRows,
  }
}

function parseRows(value: string, delimiter: TableDelimiter, rowLimit: number): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let inQuotes = false

  const pushCell = (): void => {
    row.push(cell)
    cell = ''
  }

  const pushRow = (): void => {
    pushCell()
    if (row.some((item) => item.length > 0)) {
      rows.push(row)
    }
    row = []
  }

  for (let index = 0; index < value.length; index += 1) {
    const char = value[index]

    if (char === '"') {
      if (inQuotes && value[index + 1] === '"') {
        cell += '"'
        index += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }

    if (!inQuotes && char === delimiter) {
      pushCell()
      continue
    }

    if (!inQuotes && (char === '\n' || char === '\r')) {
      if (char === '\r' && value[index + 1] === '\n') {
        index += 1
      }
      pushRow()
      if (rows.length >= rowLimit) {
        return rows
      }
      continue
    }

    cell += char
  }

  if (cell.length > 0 || row.length > 0) {
    pushRow()
  }

  return rows
}

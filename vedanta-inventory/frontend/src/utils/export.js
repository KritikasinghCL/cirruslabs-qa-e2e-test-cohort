/**
 * Export utilities: CSV, Excel (via SheetJS/xlsx), PDF (via jsPDF + autoTable)
 * Used by DataTable component.
 */
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import * as XLSX from 'xlsx'

// ─── CSV ─────────────────────────────────────────────────────────────────────
export function exportCSV(data, columns, filename) {
  const headers = columns.map(c => c.label).join(',')
  const rows = data.map(row =>
    columns.map(c => {
      const v = row[c.key]
      if (v === null || v === undefined) return 'Data not available'
      if (typeof v === 'string' && (v.includes(',') || v.includes('"')))
        return `"${v.replace(/"/g, '""')}"`
      return v
    }).join(',')
  )
  const csv = [headers, ...rows].join('\n')
  downloadBlob(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' }), `${filename}.csv`)
}

// ─── Excel (real .xlsx via SheetJS) ──────────────────────────────────────────
export function exportExcel(data, columns, filename) {
  const wsData = [
    columns.map(c => c.label),
    ...data.map(row =>
      columns.map(c => {
        const v = row[c.key]
        return v === null || v === undefined ? 'Data not available' : v
      })
    ),
  ]
  const ws = XLSX.utils.aoa_to_sheet(wsData)

  // Column widths
  ws['!cols'] = columns.map(c => ({ wch: Math.max(c.label.length + 4, 14) }))

  // Header style (SheetJS community doesn't support cell styles without Pro,
  // but we can set the freeze pane)
  ws['!freeze'] = { xSplit: 0, ySplit: 1 }

  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Vedanta Inventory')

  // Metadata sheet
  const meta = XLSX.utils.aoa_to_sheet([
    ['Vedanta Inventory Forecasting Dashboard'],
    ['Scope', 'ZSPR and ZSPN materials only'],
    ['Exported', new Date().toLocaleString('en-IN')],
    ['Page', filename],
    ['Note', 'Data not available = metric blocked by open gap (see Data & Methodology page)'],
  ])
  XLSX.utils.book_append_sheet(wb, meta, 'Metadata')

  XLSX.writeFile(wb, `${filename}.xlsx`)
}

// ─── PDF ─────────────────────────────────────────────────────────────────────
export function exportPDF(data, columns, filename, pageLabel = '') {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' })

  // Header bar
  doc.setFillColor(22, 33, 62)
  doc.rect(0, 0, doc.internal.pageSize.width, 52, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFontSize(15)
  doc.setFont('helvetica', 'bold')
  doc.text('Vedanta Inventory Forecasting Dashboard', 40, 28)
  doc.setFontSize(9)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(180, 180, 180)
  doc.text(
    `${pageLabel} · Scope: ZSPR & ZSPN · Generated: ${new Date().toLocaleString('en-IN')}`,
    40, 44
  )

  autoTable(doc, {
    startY: 62,
    head: [columns.map(c => c.label)],
    body: data.map(row =>
      columns.map(c => {
        const v = row[c.key]
        return v === null || v === undefined ? 'Data not available' : String(v)
      })
    ),
    styles: { fontSize: 7, cellPadding: 4, textColor: [30, 30, 30] },
    headStyles: { fillColor: [15, 52, 96], textColor: [255, 255, 255], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [240, 244, 255] },
    margin: { left: 40, right: 40 },
  })

  // Footer on every page
  const pageCount = doc.internal.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFontSize(7)
    doc.setTextColor(150)
    doc.text(
      `Page ${i} of ${pageCount} · Vedanta Inventory Intelligence · CONFIDENTIAL · Data not available = metric blocked by open gap`,
      40, doc.internal.pageSize.height - 18
    )
  }

  doc.save(`${filename}.pdf`)
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

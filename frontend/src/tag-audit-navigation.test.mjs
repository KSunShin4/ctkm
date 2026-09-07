import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = async name => readFile(new URL(name, import.meta.url), 'utf8')

test('main navigation exposes public shelf check beside store modules', async () => {
  const source = await read('./main.jsx')
  assert.match(source, /data-ctkm-shelf-link/)
  assert.match(source, /Kiểm tra kệ/)
  assert.match(source, /\/scan-tem\?mode=shelf/)
  assert.match(source, /expirationButton\.after\(shelfButton\)/)
})

test('standalone shelf and camera routes expose an explicit way back to main features', async () => {
  const shelf = await read('./tag-audit-shelf-main.jsx')
  const camera = await read('./tag-audit-main.jsx')
  for (const source of [shelf, camera]) {
    assert.match(source, /href="\/"/)
    assert.match(source, /Thoát · Chức năng khác/)
  }
})

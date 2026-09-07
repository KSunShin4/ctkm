import test from "node:test"
import assert from "node:assert/strict"
import { nextShelfKey, smartShelfList } from "./tag-audit-shelf-list.js"

const shelves = [
  {shelf_key:"A", shelf_label:"POG-A · L1"},
  {shelf_key:"B", shelf_label:"POG-B · L2"},
  {shelf_key:"C", shelf_label:"POG-C · L3"},
  {shelf_key:"D", shelf_label:"POG-D · L4"},
]
const items = [
  {shelf_key:"A", item_id:"P25860", item_name:"HOTCHLAND SLEEP NOW", pog_code:"POG-A", location_id:"L1"},
  {shelf_key:"B", item_id:"P25175", item_name:"FELIX GINKGO BILOBA", pog_code:"POG-B", location_id:"L2"},
  {shelf_key:"C", item_id:"P30001", item_name:"OTHER", pog_code:"POG-C", location_id:"L3"},
  {shelf_key:"D", item_id:"P30002", item_name:"DONE", pog_code:"POG-D", location_id:"L4"},
]
const stats = {
  A:{total:10,checked:4,remaining:6,pass:4,fail:0,review:0},
  B:{total:8,checked:2,remaining:6,pass:1,fail:1,review:0},
  C:{total:9,checked:0,remaining:9,pass:0,fail:0,review:0},
  D:{total:5,checked:5,remaining:0,pass:5,fail:0,review:0},
}
const getStats = key => stats[key]

test("search finds shelf by item id and product name", () => {
  assert.deepEqual(smartShelfList(shelves,items,getStats,{query:"P25860",filter:"all"}).rows.map(x=>x.shelf.shelf_key), ["A"])
  assert.deepEqual(smartShelfList(shelves,items,getStats,{query:"felix",filter:"all"}).rows.map(x=>x.shelf.shelf_key), ["B"])
})

test("default todo hides completed shelves and prioritizes issues then in-progress", () => {
  const result = smartShelfList(shelves,items,getStats,{filter:"todo",limit:12})
  assert.deepEqual(result.rows.map(x=>x.shelf.shelf_key), ["B","A","C"])
  assert.equal(result.totalMatches, 3)
})

test("compact list limits only non-search browsing", () => {
  const limited = smartShelfList(shelves,items,getStats,{filter:"all",limit:2})
  assert.equal(limited.rows.length, 2)
  assert.equal(limited.totalMatches, 4)
  const searched = smartShelfList(shelves,items,getStats,{query:"POG",filter:"all",limit:2})
  assert.equal(searched.rows.length, 4)
})

test("next shelf chooses issue before in-progress and untouched", () => {
  assert.equal(nextShelfKey(shelves,getStats), "B")
})

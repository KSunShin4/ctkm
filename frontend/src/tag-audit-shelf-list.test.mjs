import test from "node:test"
import assert from "node:assert/strict"
import { nextShelfKey, smartShelfList, smartShelfSuggestions } from "./tag-audit-shelf-list.js"

const shelves = [
  {shelf_key:"A", shelf_label:"POG-A", locations:["KỆ-01"]},
  {shelf_key:"B", shelf_label:"POG-B", locations:["KỆ-02"]},
  {shelf_key:"C", shelf_label:"POG-C", locations:["KỆ-03"]},
  {shelf_key:"D", shelf_label:"POG-D", locations:["KỆ-04"]},
  {shelf_key:"E", shelf_label:"POG-E", locations:["KỆ-05"]},
]
const items = [
  {shelf_key:"A", check_key:"A1", item_id:"P25860", item_name:"HOTCHLAND SLEEP NOW", pog_code:"POG-A", location_id:"KỆ-01",expected_action:"gan_tem"},
  {shelf_key:"B", check_key:"B1", item_id:"P25175", item_name:"FELIX GINKGO BILOBA", pog_code:"POG-B", location_id:"KỆ-02",expected_action:"gan_tem"},
  {shelf_key:"C", check_key:"C1", item_id:"P30001", item_name:"OTHER", pog_code:"POG-C", location_id:"KỆ-03",expected_action:"gan_tem"},
  {shelf_key:"D", check_key:"D1", item_id:"P30002", item_name:"DONE", pog_code:"POG-D", location_id:"KỆ-04",expected_action:"gan_tem"},
  {shelf_key:"E", check_key:"E1", removal_key:"ER1", item_id:"P30003", item_name:"EXPIRED", pog_code:"POG-E", location_id:"KỆ-05",expected_action:"thao_tem"},
]
const stats = {
  A:{total:10,checked:4,remaining:6,pass:4,fail:0,review:0,attachTotal:10,removeTotal:0,removed:0,removePending:0},
  B:{total:8,checked:2,remaining:6,pass:1,fail:1,review:0,attachTotal:8,removeTotal:0,removed:0,removePending:0},
  C:{total:9,checked:0,remaining:9,pass:0,fail:0,review:0,attachTotal:9,removeTotal:0,removed:0,removePending:0},
  D:{total:5,checked:5,remaining:0,pass:5,fail:0,review:0,attachTotal:5,removeTotal:0,removed:0,removePending:0},
  E:{total:7,checked:6,remaining:1,pass:5,fail:1,review:0,attachTotal:0,removeTotal:7,removed:5,removePending:2},
}
const getStats = key => stats[key]

test("search finds shelf by item id and returns a useful match hint", () => {
  const result = smartShelfList(shelves,items,getStats,{query:"P25860",filter:"all"})
  assert.deepEqual(result.rows.map(x=>x.shelf.shelf_key), ["A"])
  assert.match(result.rows[0].matchHint, /P25860/)
})

test("search is accent-insensitive, compact-form friendly and typo tolerant", () => {
  assert.deepEqual(smartShelfList(shelves,items,getStats,{query:"ke 01",filter:"all"}).rows.map(x=>x.shelf.shelf_key), ["A"])
  assert.deepEqual(smartShelfList(shelves,items,getStats,{query:"ke02",filter:"all"}).rows.map(x=>x.shelf.shelf_key), ["B"])
  assert.deepEqual(smartShelfList(shelves,items,getStats,{query:"ginko",filter:"all"}).rows.map(x=>x.shelf.shelf_key), ["B"])
})

test("typing searches all statuses even when browsing filter is still todo", () => {
  const result = smartShelfList(shelves,items,getStats,{query:"P30002",filter:"todo"})
  assert.deepEqual(result.rows.map(x=>x.shelf.shelf_key), ["D"])
  assert.equal(result.rows[0].status, "done")
})

test("default todo prioritizes due removal before ordinary issues and work", () => {
  const result = smartShelfList(shelves,items,getStats,{filter:"todo",limit:12})
  assert.deepEqual(result.rows.map(x=>x.shelf.shelf_key), ["E","B","A","C"])
  assert.equal(result.totalMatches, 4)
})

test("remove filter only shows shelves with unfinished removal work", () => {
  const result = smartShelfList(shelves,items,getStats,{filter:"remove",limit:12})
  assert.deepEqual(result.rows.map(x=>x.shelf.shelf_key), ["E"])
})

test("browsing and search stay compact", () => {
  const limited = smartShelfList(shelves,items,getStats,{filter:"all",limit:2})
  assert.equal(limited.rows.length, 2)
  assert.equal(limited.totalMatches, 5)
  const searched = smartShelfList(shelves,items,getStats,{query:"POG",filter:"all",searchLimit:3})
  assert.equal(searched.rows.length, 3)
  assert.equal(searched.totalMatches, 5)
})

test("clicking search exposes a full progress-aware shelf directory", () => {
  const progress = {
    A1:{state:"pass",checkedAt:"2026-09-08T01:00:00.000Z",resolved:false},
    B1:{state:"fail",reason:"Sai giá",checkedAt:"2026-09-08T01:10:00.000Z",resolved:false},
  }
  const removal = {
    ER1:{state:"still_present",checkedAt:"2026-09-08T01:20:00.000Z"},
  }
  const directory = smartShelfSuggestions(shelves,items,getStats,progress,removal,{limit:7})
  assert.deepEqual(directory.map(row => row.shelf.shelf_key), ["E","B","A","C","D"])
  assert.deepEqual(directory.map(row => row.kind), ["remove","resume","resume","todo","done"])
  assert.equal(directory.length, shelves.length)
  assert.match(directory[0].reason, /KỆ-05/)
})

test("suggestions put due removal first before recent in-progress work", () => {
  const progress = {
    A1:{state:"pass",checkedAt:"2026-09-08T01:00:00.000Z",resolved:false},
    B1:{state:"fail",reason:"Sai giá",checkedAt:"2026-09-08T01:10:00.000Z",resolved:false},
  }
  const removal = {
    ER1:{state:"still_present",checkedAt:"2026-09-08T01:20:00.000Z"},
  }
  const suggestions = smartShelfSuggestions(shelves,items,getStats,progress,removal,{limit:7})
  assert.equal(suggestions[0].shelf.shelf_key, "E")
  assert.equal(suggestions[0].kind, "remove")
  assert.ok(suggestions.some(row => row.shelf.shelf_key === "B" && row.kind === "resume"))
})

test("unresolved fail or review is suggested for return when not already used", () => {
  const localStats = {...stats, B:{...stats.B,checked:8,remaining:0,removePending:0}}
  const localGetStats = key => localStats[key]
  const progress = {
    B1:{state:"fail",reason:"Sai giá",checkedAt:"2026-09-08T01:10:00.000Z",resolved:false},
  }
  const suggestions = smartShelfSuggestions(shelves,items,localGetStats,progress,{}, {limit:7})
  assert.ok(suggestions.some(row => row.shelf.shelf_key === "B" && row.kind === "issue" && row.unresolvedIssues === 1))
})

test("focus directory remains bounded for very large stores", () => {
  const manyShelves = Array.from({length:100}, (_, index) => ({shelf_key:`S${index}`, shelf_label:`POG-${index}`}))
  const manyStats = () => ({total:1,checked:0,remaining:1,pass:0,fail:0,review:0,attachTotal:1,removeTotal:0,removed:0,removePending:0})
  const directory = smartShelfSuggestions(manyShelves,[],manyStats,{}, {}, {limit:7,browseLimit:60})
  assert.equal(directory.length, 60)
})

test("next shelf chooses due removal and can exclude the current shelf", () => {
  assert.equal(nextShelfKey(shelves,getStats), "E")
  assert.equal(nextShelfKey(shelves,getStats,{excludeKey:"E"}), "B")
})

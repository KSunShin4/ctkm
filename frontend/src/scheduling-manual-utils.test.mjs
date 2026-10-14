import test from "node:test"
import assert from "node:assert/strict"
import { applySmartSuggestion, buildLockedOptimizationConfig, buildSmartSuggestions, clearDraft, DRAFT_STORAGE_KEY, getExportDockState, loadDraft, rebalanceManualMorningTimes, restoreTouchedReceiving, saveDraft, summarizeCurrentSchedule, validateConfigPreflight } from "./scheduling-manual-utils.js"

function baseConfig(){
  return {
    employees:[
      {id:"phuong",role:"STORE_MANAGER",active:true},
      {id:"mi",role:"EMPLOYEE",active:true},
      {id:"ly",role:"EMPLOYEE",active:true},
    ],
    morning_time_overrides:[],
  }
}

test("manual edit with two morning staff normalizes both to 06:00",()=>{
  const config=baseConfig()
  const rows=[
    {employee_id:"phuong",date:"2026-09-23",shift:"MORNING",start_time:"07:00"},
    {employee_id:"mi",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
    {employee_id:"ly",date:"2026-09-23",shift:"AFTERNOON",start_time:"14:00"},
  ]
  const out=rebalanceManualMorningTimes(config,rows,"2026-09-23")
  const morning=out.filter(r=>r.shift==="MORNING")
  assert.deepEqual(morning.map(r=>r.start_time).sort(),["06:00","06:00"])
})

test("manual edit with three morning staff gives exactly one 07:00 and prefers CHT",()=>{
  const config=baseConfig()
  const rows=[
    {employee_id:"phuong",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
    {employee_id:"mi",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
    {employee_id:"ly",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
  ]
  const out=rebalanceManualMorningTimes(config,rows,"2026-09-23")
  const morning=out.filter(r=>r.shift==="MORNING")
  assert.equal(morning.filter(r=>r.start_time==="07:00").length,1)
  assert.equal(morning.find(r=>r.employee_id==="phuong").start_time,"07:00")
})

test("explicit 06:00 lock on CHT is preserved and another staff gets 07:00",()=>{
  const config=baseConfig()
  config.morning_time_overrides=[{employee_id:"phuong",date:"2026-09-23",start:"06:00"}]
  const rows=[
    {employee_id:"phuong",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
    {employee_id:"mi",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
    {employee_id:"ly",date:"2026-09-23",shift:"MORNING",start_time:"06:00"},
  ]
  const out=rebalanceManualMorningTimes(config,rows,"2026-09-23")
  assert.equal(out.find(r=>r.employee_id==="phuong").start_time,"06:00")
  assert.equal(out.filter(r=>r.start_time==="07:00").length,1)
})

function smartConfig(){
  return {
    week_start:"2026-09-21",
    employees:[
      {id:"phuong",name:"Phương",role:"STORE_MANAGER",active:true},
      {id:"mi",name:"Mi",role:"EMPLOYEE",active:true},
      {id:"ly",name:"Ly",role:"EMPLOYEE",active:true},
      {id:"vu",name:"Vũ",role:"EMPLOYEE",active:true},
    ],
    staffing:[
      {date:"2026-09-21",morning:2,afternoon:2},
      {date:"2026-09-22",morning:2,afternoon:2},
    ],
    requests:[],
    fixed_weekday_rules:[],
    employee_rules:[
      {employee_id:"phuong",target_morning:1,target_afternoon:1,receiving_target:0},
      {employee_id:"mi",target_morning:1,target_afternoon:1,receiving_target:0},
      {employee_id:"ly",target_morning:1,target_afternoon:1,receiving_target:0},
      {employee_id:"vu",target_morning:1,target_afternoon:1,receiving_target:0},
    ],
    receiving_days:[],
    manager_trend:{enabled:true,scores:[
      {weekday:0,morning:10,afternoon:20},
      {weekday:1,morning:20,afternoon:10},
    ]},
    morning_time_overrides:[],
  }
}

test("smart assistant suggests moving one person when a day is overstaffed morning and understaffed afternoon",()=>{
  const config=smartConfig()
  const rows=[
    {employee_id:"phuong",date:"2026-09-21",shift:"MORNING",start_time:"07:00",receiving:false},
    {employee_id:"mi",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"ly",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"vu",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:false},
  ]
  const suggestions=buildSmartSuggestions(config,rows,{status:"VALID_WITH_WARNINGS",errors:[],warnings:[]})
  const move=suggestions.find(s=>s.type==="MOVE_SHIFT")
  assert.ok(move)
  assert.equal(move.from_shift,"MORNING")
  assert.equal(move.to_shift,"AFTERNOON")
  assert.match(move.reason,/3S\/1C/)
})

test("smart assistant never proposes breaking a hard shift rule",()=>{
  const config=smartConfig()
  config.fixed_weekday_rules=[{employee_id:"mi",weekday:0,shift:"MORNING",level:"HARD",source:"USER"}]
  const rows=[
    {employee_id:"phuong",date:"2026-09-21",shift:"MORNING",start_time:"07:00",receiving:false},
    {employee_id:"mi",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"ly",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"vu",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:false},
  ]
  const suggestions=buildSmartSuggestions(config,rows,{status:"VALID_WITH_WARNINGS",errors:[],warnings:[]})
  const move=suggestions.find(s=>s.type==="MOVE_SHIFT")
  assert.ok(move)
  assert.notEqual(move.employee_id,"mi")
})

test("applying a move suggestion changes only after explicit apply and rebalances morning times",()=>{
  const config=smartConfig()
  const rows=[
    {employee_id:"phuong",date:"2026-09-21",shift:"MORNING",start_time:"07:00",receiving:false},
    {employee_id:"mi",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"ly",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
    {employee_id:"vu",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:false},
  ]
  const suggestion=buildSmartSuggestions(config,rows,{status:"VALID_WITH_WARNINGS",errors:[],warnings:[]}).find(s=>s.type==="MOVE_SHIFT")
  assert.ok(suggestion)
  assert.equal(rows.filter(r=>r.shift==="MORNING").length,3)
  const next=applySmartSuggestion(config,rows,suggestion)
  assert.equal(rows.filter(r=>r.shift==="MORNING").length,3)
  assert.equal(next.filter(r=>r.shift==="MORNING").length,2)
  assert.deepEqual(next.filter(r=>r.shift==="MORNING").map(r=>r.start_time).sort(),["06:00","06:00"])
})

test("schedule summary separates hard errors from optimization suggestions",()=>{
  const config=smartConfig()
  const critical=summarizeCurrentSchedule(config,{errors:["x"],warnings:[]},[])
  assert.equal(critical.tone,"error")
  const ok=summarizeCurrentSchedule(config,{errors:[],warnings:[]},[{severity:"optimization"}])
  assert.equal(ok.tone,"ok")
  assert.match(ok.headline,/1 điểm/)
})

test("optimize remaining converts manually touched cells into temporary hard locks",()=>{
  const config=smartConfig()
  const rows=[
    {employee_id:"phuong",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:false},
    {employee_id:"mi",date:"2026-09-21",shift:"MORNING",start_time:"06:00",receiving:false},
  ]
  const touched=new Set(["phuong|2026-09-21"])
  const locked=buildLockedOptimizationConfig(config,rows,touched)
  assert.ok(locked.requests.some(r=>r.employee_id==="phuong"&&r.date==="2026-09-21"&&r.type==="MUST_AFTERNOON"))
  assert.equal(config.requests.length,0)
})

test("restore touched receiving preserves user choice after optimizer rerun",()=>{
  const current=[{employee_id:"mi",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:true}]
  const generated=[{employee_id:"mi",date:"2026-09-21",shift:"AFTERNOON",start_time:"14:00",receiving:false}]
  const out=restoreTouchedReceiving(generated,current,new Set(["mi|2026-09-21"]))
  assert.equal(out[0].receiving,true)
})

test("export dock communicates ready warning invalid and exported states",()=>{
  const pending=getExportDockState({validation:null,dirty:true})
  assert.equal(pending.tone,"pending")
  assert.match(pending.buttonLabel,/Kiểm tra/)

  const invalid=getExportDockState({validation:{status:"INVALID",errors:["a","b"],warnings:[]},dirty:true})
  assert.equal(invalid.tone,"invalid")
  assert.match(invalid.detail,/2 lỗi/)
  assert.equal(invalid.buttonLabel,"Vẫn xuất Excel")
  assert.match(invalid.detail,/vẫn có thể xuất/)

  const warning=getExportDockState({validation:{status:"VALID_WITH_WARNINGS",errors:[],warnings:["w"]},dirty:true})
  assert.equal(warning.tone,"warning")
  assert.match(warning.detail,/1 cảnh báo/)

  const ready=getExportDockState({validation:{status:"VALID",errors:[],warnings:[]},dirty:true})
  assert.equal(ready.tone,"ready")
  assert.match(ready.label,/sẵn sàng/)

  const exported=getExportDockState({validation:{status:"VALID",errors:[],warnings:[]},dirty:false})
  assert.equal(exported.tone,"ready")
  assert.match(exported.label,/Đã xuất Excel/)
  assert.equal(exported.buttonLabel,"Xuất lại Excel")
})

test("export dock surfaces the last export error next to the action button",()=>{
  const state=getExportDockState({
    validation:{status:"VALID",errors:[],warnings:[]},
    dirty:true,
    message:"Lỗi xuất Excel: workbook invalid",
  })
  assert.equal(state.tone,"invalid")
  assert.equal(state.label,"Xuất Excel chưa thành công")
  assert.match(state.detail,/workbook invalid/)
})

test("validateConfigPreflight passes on valid configuration",()=>{
  const config = smartConfig()
  const result = validateConfigPreflight(config)
  assert.equal(result.valid, true)
  assert.equal(result.errors.length, 0)
})

test("validateConfigPreflight catches receiving count exceeding afternoon staffing",()=>{
  const config = smartConfig()
  config.receiving_days = [{date: "2026-09-21", count: 3}]
  // Afternoon staffing on 2026-09-21 is 2
  const result = validateConfigPreflight(config)
  assert.equal(result.valid, false)
  assert.ok(result.errors.some(e => e.includes("Số người nhận hàng") && e.includes("vượt quá quân số ca Chiều")))
})

test("validateConfigPreflight catches hard conflict between QLKV rule and requests",()=>{
  const config = smartConfig()
  config.fixed_weekday_rules = [
    {employee_id: "phuong", weekday: 0, shift: "MORNING", level: "HARD", source: "REGIONAL"}
  ]
  config.requests = [
    {employee_id: "phuong", date: "2026-09-21", type: "OFF"}
  ]
  const result = validateConfigPreflight(config)
  assert.equal(result.valid, false)
  assert.ok(result.errors.some(e => e.includes("Xung đột ca bắt buộc") && e.includes("QLKV") && e.includes("Nguyện vọng")))
})

test("validateConfigPreflight catches missing or multiple store managers",()=>{
  const config = smartConfig()
  config.employees[0].role = "EMPLOYEE"
  const noManager = validateConfigPreflight(config)
  assert.equal(noManager.valid, false)
  assert.ok(noManager.errors.some(e => e.includes("Chưa có Cửa hàng trưởng")))

  config.employees[0].role = "STORE_MANAGER"
  config.employees[1].role = "STORE_MANAGER"
  const multiManager = validateConfigPreflight(config)
  assert.equal(multiManager.valid, false)
  assert.ok(multiManager.errors.some(e => e.includes("Có 2 CHT đang hoạt động")))
})

test("validateConfigPreflight catches morning staffing exceeding 3",()=>{
  const config = smartConfig()
  config.staffing[0].morning = 4
  const result = validateConfigPreflight(config)
  assert.equal(result.valid, false)
  assert.ok(result.errors.some(e => e.includes("tối đa 3 người")))
})

function createMockStorage() {
  const store = new Map()
  return {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
  }
}

test("saveDraft and loadDraft roundtrips configuration, assignments and manualTouched", () => {
  const storage = createMockStorage()
  const config = smartConfig()
  const assignments = [{ employee_id: "phuong", date: "2026-09-21", shift: "MORNING", start_time: "07:00" }]
  const manualTouched = new Set(["phuong|2026-09-21"])

  const saved = saveDraft({ config, assignments, manualTouched, variant: "preferences" }, storage)
  assert.equal(saved, true)

  const loaded = loadDraft(storage)
  assert.ok(loaded)
  assert.equal(loaded.config.week_start, "2026-09-21")
  assert.equal(loaded.assignments.length, 1)
  assert.equal(loaded.assignments[0].employee_id, "phuong")
  assert.ok(loaded.manualTouched instanceof Set)
  assert.ok(loaded.manualTouched.has("phuong|2026-09-21"))
  assert.equal(loaded.variant, "preferences")
  assert.ok(typeof loaded.savedAt === "number")
})

test("clearDraft removes the stored draft", () => {
  const storage = createMockStorage()
  saveDraft({ config: smartConfig() }, storage)
  assert.ok(loadDraft(storage))

  clearDraft(storage)
  assert.equal(loadDraft(storage), null)
})

test("loadDraft safely handles invalid JSON or missing fields", () => {
  const storage = createMockStorage()
  storage.setItem(DRAFT_STORAGE_KEY, "invalid json {")
  assert.equal(loadDraft(storage), null)

  storage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ wrong: true }))
  assert.equal(loadDraft(storage), null)
})


import test from "node:test"
import assert from "node:assert/strict"
import { applySmartSuggestion, buildLockedOptimizationConfig, buildSmartSuggestions, rebalanceManualMorningTimes, restoreTouchedReceiving, summarizeCurrentSchedule } from "./scheduling-manual-utils.js"

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


import test from "node:test"
import assert from "node:assert/strict"
import { rebalanceManualMorningTimes } from "./scheduling-manual-utils.js"

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

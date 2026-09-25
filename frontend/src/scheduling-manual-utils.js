function key(employeeId,date){return `${employeeId}|${date}`}
function countSwitches(rows){
  const sorted=[...rows].sort((a,b)=>a.date.localeCompare(b.date))
  let previous=null,switches=0
  for(const row of sorted){
    if(row.shift==="OFF"){previous=null;continue}
    if(previous&&previous!==row.shift)switches++
    previous=row.shift
  }
  return switches
}
function effectiveTargets(config,date){
  const nominal=(config.staffing||[]).find(r=>r.date===date)||{morning:0,afternoon:0}
  const active=(config.employees||[]).filter(e=>e.active)
  const weekday=Math.round((new Date(date+"T00:00:00")-new Date(config.week_start+"T00:00:00"))/86400000)
  const hardOff=new Set()
  for(const r of config.requests||[])if(r.date===date&&r.type==="OFF")hardOff.add(r.employee_id)
  for(const r of config.fixed_weekday_rules||[])if(Number(r.weekday)===weekday&&r.level==="HARD"&&r.shift==="OFF")hardOff.add(r.employee_id)
  const available=Math.max(0,active.length-hardOff.size)
  const total=Math.min(available,Number(nominal.morning||0)+Number(nominal.afternoon||0))
  const candidates=[]
  for(let morning=0;morning<=Math.min(Number(nominal.morning||0),total);morning++){
    const afternoon=total-morning
    if(afternoon<0||afternoon>Number(nominal.afternoon||0))continue
    const ratio=Math.abs(morning*(Number(nominal.morning||0)+Number(nominal.afternoon||0))-Number(nominal.morning||0)*total)
    candidates.push([ratio,Math.abs(morning-afternoon),morning,afternoon])
  }
  candidates.sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2])
  return {morning:candidates[0]?.[2]||0,afternoon:candidates[0]?.[3]||0}
}
function hardWanted(config,employeeId,date){
  const req=(config.requests||[]).find(r=>r.employee_id===employeeId&&r.date===date&&["OFF","MUST_MORNING","MUST_AFTERNOON"].includes(r.type))
  if(req)return req.type==="OFF"?"OFF":req.type==="MUST_MORNING"?"MORNING":"AFTERNOON"
  const weekday=Math.round((new Date(date+"T00:00:00")-new Date(config.week_start+"T00:00:00"))/86400000)
  const fixed=(config.fixed_weekday_rules||[]).find(r=>r.employee_id===employeeId&&Number(r.weekday)===weekday&&r.level==="HARD")
  return fixed?.shift||null
}
function softWanted(config,employeeId,date){
  const req=(config.requests||[]).find(r=>r.employee_id===employeeId&&r.date===date&&["PREFER_MORNING","PREFER_AFTERNOON"].includes(r.type))
  return req?.type==="PREFER_MORNING"?"MORNING":req?.type==="PREFER_AFTERNOON"?"AFTERNOON":null
}
function employeeRule(config,employeeId){
  return (config.employee_rules||[]).find(r=>r.employee_id===employeeId)||{}
}
function employeeCounts(assignments,employeeId){
  const rows=assignments.filter(r=>r.employee_id===employeeId)
  return {
    morning:rows.filter(r=>r.shift==="MORNING").length,
    afternoon:rows.filter(r=>r.shift==="AFTERNOON").length,
    receiving:rows.filter(r=>r.receiving).length,
    switches:countSwitches(rows),
  }
}
function targetPenalty(config,assignments,employeeId){
  const rule=employeeRule(config,employeeId), counts=employeeCounts(assignments,employeeId)
  let p=0
  if(rule.target_morning!=null)p+=Math.abs(counts.morning-Number(rule.target_morning))
  if(rule.target_afternoon!=null)p+=Math.abs(counts.afternoon-Number(rule.target_afternoon))
  return p
}
function changeOne(assignments,employeeId,date,toShift){
  return assignments.map(row=>{
    if(row.employee_id!==employeeId||row.date!==date)return {...row}
    if(toShift==="MORNING")return {...row,shift:"MORNING",start_time:"06:00",receiving:false}
    if(toShift==="AFTERNOON")return {...row,shift:"AFTERNOON",start_time:"14:00",receiving:false}
    return {...row,shift:"OFF",start_time:null,receiving:false}
  })
}
function candidateScore(config,assignments,employeeId,date,toShift,manualTouched){
  if(hardWanted(config,employeeId,date)&&hardWanted(config,employeeId,date)!==toShift)return null
  const current=assignments.find(r=>r.employee_id===employeeId&&r.date===date)
  if(!current||current.shift===toShift)return null
  const beforeTarget=targetPenalty(config,assignments,employeeId)
  const afterAssignments=changeOne(assignments,employeeId,date,toShift)
  const afterTarget=targetPenalty(config,afterAssignments,employeeId)
  const beforeSwitch=employeeCounts(assignments,employeeId).switches
  const afterSwitch=employeeCounts(afterAssignments,employeeId).switches
  let score=(afterTarget-beforeTarget)*12+(afterSwitch-beforeSwitch)*7
  if(current.receiving)score+=30
  if(softWanted(config,employeeId,date)&&softWanted(config,employeeId,date)!==toShift)score+=8
  if(manualTouched?.has?.(key(employeeId,date)))score+=18
  const employee=(config.employees||[]).find(e=>e.id===employeeId)
  if(employee?.role==="STORE_MANAGER"&&config.manager_trend?.enabled!==false){
    const weekday=Math.round((new Date(date+"T00:00:00")-new Date(config.week_start+"T00:00:00"))/86400000)
    const trend=(config.manager_trend?.scores||[]).find(r=>Number(r.weekday)===weekday)
    if(trend){
      const currentScore=current.shift==="MORNING"?Number(trend.morning||0):current.shift==="AFTERNOON"?Number(trend.afternoon||0):0
      const nextScore=toShift==="MORNING"?Number(trend.morning||0):toShift==="AFTERNOON"?Number(trend.afternoon||0):0
      score+=(currentScore-nextScore)/3
    }
  }
  return {score,beforeTarget,afterTarget,beforeSwitch,afterSwitch,current}
}
function employeeName(config,id){return (config.employees||[]).find(e=>e.id===id)?.name||id}
function dayLabel(config,date){
  const idx=Math.round((new Date(date+"T00:00:00")-new Date(config.week_start+"T00:00:00"))/86400000)
  return ["T2","T3","T4","T5","T6","T7","CN"][idx]||date
}
function severityRank(x){return x==="critical"?0:x==="important"?1:2}

export function buildSmartSuggestions(config,assignments,validation,{manualTouched=new Set(),dismissed=new Set()}={}){
  if(!assignments?.length)return []
  const out=[]
  const dates=[...new Set(assignments.map(r=>r.date))].sort()
  for(const date of dates){
    const rows=assignments.filter(r=>r.date===date)
    const target=effectiveTargets(config,date)
    const morning=rows.filter(r=>r.shift==="MORNING")
    const afternoon=rows.filter(r=>r.shift==="AFTERNOON")
    let from=null,to=null,need=0
    if(morning.length>target.morning&&afternoon.length<target.afternoon){from="MORNING";to="AFTERNOON";need=Math.min(morning.length-target.morning,target.afternoon-afternoon.length)}
    else if(afternoon.length>target.afternoon&&morning.length<target.morning){from="AFTERNOON";to="MORNING";need=Math.min(afternoon.length-target.afternoon,target.morning-morning.length)}
    if(from&&to&&need>0){
      const candidates=rows.filter(r=>r.shift===from).map(r=>({id:r.employee_id,...candidateScore(config,assignments,r.employee_id,date,to,manualTouched)})).filter(x=>x.score!=null).sort((a,b)=>a.score-b.score)
      const pick=candidates[0]
      if(pick){
        const id=`balance:${date}:${pick.id}:${from}:${to}`
        if(!dismissed.has(id)){
          const touched=manualTouched.has(key(pick.id,date))
          const reasons=[`${dayLabel(config,date)} đang ${morning.length}S/${afternoon.length}C, mục tiêu hiện tại ${target.morning}S/${target.afternoon}C`]
          if(pick.afterTarget<pick.beforeTarget)reasons.push("đưa nhân viên gần target S/C hơn")
          if(pick.afterSwitch<pick.beforeSwitch)reasons.push("giảm số lần đổi ca")
          if(touched)reasons.push("ô này đã được chỉnh tay nên chỉ thay khi bạn đồng ý")
          out.push({id,type:"MOVE_SHIFT",severity:"important",title:`Chuyển ${employeeName(config,pick.id)} ${from==="MORNING"?"Sáng":"Chiều"} → ${to==="MORNING"?"Sáng":"Chiều"}`,reason:reasons.join("; "),employee_id:pick.id,date,from_shift:from,to_shift:to,score:pick.score})
        }
      }
    }

    const receiving=(config.receiving_days||[]).find(r=>r.date===date)
    if(receiving){
      const wanted=Math.min(Number(receiving.count||0),target.afternoon)
      const assigned=afternoon.filter(r=>r.receiving)
      if(assigned.length<wanted){
        const candidates=afternoon.filter(r=>!r.receiving).filter(r=>!manualTouched.has(key(r.employee_id,date))||afternoon.length===1).map(r=>{
          const rule=employeeRule(config,r.employee_id), counts=employeeCounts(assignments,r.employee_id)
          let score=0
          if(rule.receiving_target!=null)score+=(counts.receiving-Number(rule.receiving_target))*8
          if(rule.receiving_max!=null&&counts.receiving>=Number(rule.receiving_max))score+=100
          if(rule.off_receiving_compensation)score-=4
          return {id:r.employee_id,score}
        }).sort((a,b)=>a.score-b.score)
        const pick=candidates[0]
        if(pick&&pick.score<100){
          const id=`receiving:${date}:${pick.id}`
          if(!dismissed.has(id))out.push({id,type:"SET_RECEIVING",severity:"important",title:`Cho ${employeeName(config,pick.id)} nhận hàng ${dayLabel(config,date)}`,reason:`Ngày nhận hàng đang có ${assigned.length}/${wanted} người; ${employeeName(config,pick.id)} đang ở ca Chiều và phù hợp hơn các lựa chọn còn lại.`,employee_id:pick.id,date,value:true,score:pick.score})
        }
      }
    }
  }

  // Same-day swaps: preserve staffing while improving target/switches or CHT trend.
  for(const date of dates){
    const rows=assignments.filter(r=>r.date===date)
    const morning=rows.filter(r=>r.shift==="MORNING"), afternoon=rows.filter(r=>r.shift==="AFTERNOON")
    const swapCandidates=[]
    for(const a of morning)for(const b of afternoon){
      if(hardWanted(config,a.employee_id,date)&&hardWanted(config,a.employee_id,date)!=="AFTERNOON")continue
      if(hardWanted(config,b.employee_id,date)&&hardWanted(config,b.employee_id,date)!=="MORNING")continue
      if(a.receiving||b.receiving)continue
      const before=targetPenalty(config,assignments,a.employee_id)+targetPenalty(config,assignments,b.employee_id)+employeeCounts(assignments,a.employee_id).switches+employeeCounts(assignments,b.employee_id).switches
      let swapped=changeOne(assignments,a.employee_id,date,"AFTERNOON")
      swapped=changeOne(swapped,b.employee_id,date,"MORNING")
      const after=targetPenalty(config,swapped,a.employee_id)+targetPenalty(config,swapped,b.employee_id)+employeeCounts(swapped,a.employee_id).switches+employeeCounts(swapped,b.employee_id).switches
      let gain=before-after
      const manager=(config.employees||[]).find(e=>e.active&&e.role==="STORE_MANAGER")
      if(config.manager_trend?.enabled!==false&&manager&&(a.employee_id===manager.id||b.employee_id===manager.id)){
        const weekday=Math.round((new Date(date+"T00:00:00")-new Date(config.week_start+"T00:00:00"))/86400000)
        const trend=(config.manager_trend?.scores||[]).find(r=>Number(r.weekday)===weekday)
        if(trend){
          const managerFrom=a.employee_id===manager.id?"MORNING":"AFTERNOON"
          const managerTo=managerFrom==="MORNING"?"AFTERNOON":"MORNING"
          const fromScore=Number(managerFrom==="MORNING"?trend.morning:trend.afternoon)||0
          const toScore=Number(managerTo==="MORNING"?trend.morning:trend.afternoon)||0
          gain+=(toScore-fromScore)/15
        }
      }
      if(manualTouched.has(key(a.employee_id,date)))gain-=1.2
      if(manualTouched.has(key(b.employee_id,date)))gain-=1.2
      if(gain>1.5)swapCandidates.push({a,b,gain,before,after})
    }
    swapCandidates.sort((x,y)=>y.gain-x.gain)
    const pick=swapCandidates[0]
    if(pick){
      const id=`swap:${date}:${pick.a.employee_id}:${pick.b.employee_id}`
      if(!dismissed.has(id)){
        const reasons=[]
        if(pick.after<pick.before)reasons.push("giảm lệch target/đảo ca")
        const touched=manualTouched.has(key(pick.a.employee_id,date))||manualTouched.has(key(pick.b.employee_id,date))
        if(touched)reasons.push("có ô đã chỉnh tay nên hệ thống chỉ đề xuất, không tự đổi")
        out.push({id,type:"SWAP_SHIFT",severity:"optimization",title:`Đổi ca ${employeeName(config,pick.a.employee_id)} ↔ ${employeeName(config,pick.b.employee_id)} ${dayLabel(config,date)}`,reason:(reasons.join("; ")||"giữ đủ người mỗi ca nhưng làm lịch cân bằng hơn"),date,employee_a:pick.a.employee_id,employee_b:pick.b.employee_id,score:-pick.gain})
      }
    }
  }

  // Surface validator findings as non-action informational items.
  for(const [idx,error] of (validation?.errors||[]).entries()){
    const id=`error:${idx}:${error}`; if(!dismissed.has(id))out.push({id,type:"INFO",severity:"critical",title:"Cần xử lý trước khi xuất Excel",reason:error,score:-999})
  }
  for(const [idx,warning] of (validation?.warnings||[]).slice(0,6).entries()){
    const id=`warning:${idx}:${warning}`; if(!dismissed.has(id)&&!out.some(x=>x.reason.includes(warning)))out.push({id,type:"INFO",severity:"optimization",title:"Có thể tối ưu thêm",reason:warning,score:999})
  }
  return out.sort((a,b)=>severityRank(a.severity)-severityRank(b.severity)||(a.score??0)-(b.score??0)).slice(0,10)
}

export function applySmartSuggestion(config,assignments,suggestion){
  let next=assignments.map(row=>({...row}))
  if(suggestion.type==="MOVE_SHIFT"){
    next=changeOne(next,suggestion.employee_id,suggestion.date,suggestion.to_shift)
    return rebalanceManualMorningTimes(config,next,suggestion.date)
  }
  if(suggestion.type==="SET_RECEIVING"){
    return next.map(row=>row.employee_id===suggestion.employee_id&&row.date===suggestion.date?{...row,receiving:!!suggestion.value}:row)
  }
  if(suggestion.type==="SWAP_SHIFT"){
    const left=next.find(r=>r.employee_id===suggestion.employee_a&&r.date===suggestion.date)
    const right=next.find(r=>r.employee_id===suggestion.employee_b&&r.date===suggestion.date)
    if(!left||!right)return next
    const leftShift=left.shift,rightShift=right.shift
    next=changeOne(next,suggestion.employee_a,suggestion.date,rightShift)
    next=changeOne(next,suggestion.employee_b,suggestion.date,leftShift)
    return rebalanceManualMorningTimes(config,next,suggestion.date)
  }
  return next
}

export function summarizeCurrentSchedule(config,validation,suggestions){
  const critical=(validation?.errors||[]).length
  const important=suggestions.filter(s=>s.severity==="important").length
  const optimization=suggestions.filter(s=>s.severity==="optimization").length
  if(critical)return {tone:"error",headline:`Lịch còn ${critical} lỗi bắt buộc`,detail:"Cần xử lý lỗi đỏ trước khi xuất Excel."}
  if(important)return {tone:"warn",headline:`Lịch hợp lệ nhưng còn ${important} điểm nên chỉnh`,detail:optimization?`Ngoài ra có ${optimization} gợi ý tối ưu thêm.`:"Các thay đổi đều cần người dùng đồng ý."}
  if(optimization)return {tone:"ok",headline:`Lịch hợp lệ · ${optimization} điểm có thể tối ưu`,detail:"Có thể xuất Excel ngay hoặc xem thêm gợi ý."}
  return {tone:"ok",headline:"Lịch hiện tại đã ổn",detail:"Không phát hiện điểm cần xử lý thêm từ các rule hiện có."}
}

export function buildLockedOptimizationConfig(config,assignments,manualTouched){
  const next=structuredClone(config)
  const touchedRows=assignments.filter(row=>manualTouched?.has?.(key(row.employee_id,row.date)))
  const touchedKeys=new Set(touchedRows.map(row=>key(row.employee_id,row.date)))
  next.requests=(next.requests||[]).filter(r=>!touchedKeys.has(key(r.employee_id,r.date))||["PREFER_MORNING","PREFER_AFTERNOON"].includes(r.type))
  next.morning_time_overrides=(next.morning_time_overrides||[]).filter(r=>!touchedKeys.has(key(r.employee_id,r.date)))
  for(const row of touchedRows){
    const type=row.shift==="MORNING"?"MUST_MORNING":row.shift==="AFTERNOON"?"MUST_AFTERNOON":"OFF"
    next.requests.push({employee_id:row.employee_id,date:row.date,type})
    if(row.shift==="MORNING"&&["06:00","07:00"].includes(row.start_time)){
      next.morning_time_overrides.push({employee_id:row.employee_id,date:row.date,start:row.start_time})
    }
  }
  return next
}

export function restoreTouchedReceiving(generated,current,manualTouched){
  const currentMap=new Map(current.map(row=>[key(row.employee_id,row.date),row]))
  return generated.map(row=>{
    const k=key(row.employee_id,row.date)
    if(!manualTouched?.has?.(k))return row
    const before=currentMap.get(k)
    if(!before||row.shift!=="AFTERNOON")return row
    return {...row,receiving:!!before.receiving}
  })
}


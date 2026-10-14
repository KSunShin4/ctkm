export function rebalanceManualMorningTimes(config, assignments, date) {
  const result = assignments.map(row => ({...row}))
  const morning = result.filter(row => row.date === date && row.shift === "MORNING")
  if (!morning.length || morning.length > 3) return result

  const overrides = new Map(
    (config?.morning_time_overrides || [])
      .filter(item => item.date === date)
      .map(item => [item.employee_id, item.start])
  )

  if (morning.length <= 2) {
    for (const row of morning) {
      row.start_time = overrides.get(row.employee_id) === "07:00" ? "07:00" : "06:00"
    }
    return result
  }

  const forced07 = morning.filter(row => overrides.get(row.employee_id) === "07:00")
  const forced06 = new Set(
    morning
      .filter(row => overrides.get(row.employee_id) === "06:00")
      .map(row => row.employee_id)
  )

  let late = null
  if (forced07.length === 1) {
    late = forced07[0]
  } else if (forced07.length === 0) {
    const currentLate = morning.filter(
      row => row.start_time === "07:00" && !forced06.has(row.employee_id)
    )
    if (currentLate.length === 1) {
      late = currentLate[0]
    } else {
      const managerId = (config?.employees || []).find(
        employee => employee.active && employee.role === "STORE_MANAGER"
      )?.id
      const candidates = morning.filter(row => !forced06.has(row.employee_id))
      late = candidates.find(row => row.employee_id === managerId) || candidates[0] || null
    }
  }

  if (late) {
    for (const row of morning) {
      row.start_time = row.employee_id === late.employee_id ? "07:00" : "06:00"
    }
  } else {
    // Multiple explicit 07:00 locks are a real HARD conflict. Preserve them so
    // validation can explain the problem instead of silently deleting a lock.
    for (const row of morning) {
      const forced = overrides.get(row.employee_id)
      if (forced === "07:00" || forced === "06:00") row.start_time = forced
    }
  }
  return result
}

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
  if(critical)return {tone:"error",headline:`Lịch còn ${critical} lỗi bắt buộc`,detail:"Đây là cảnh báo nghiệp vụ; bạn vẫn có thể xuất Excel nếu muốn."}
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

export function getExportDockState({validation, dirty, message=""}={}){
  if(String(message).startsWith("Lỗi xuất Excel")){
    return {
      tone:"invalid",
      label:"Xuất Excel chưa thành công",
      detail:String(message).replace(/^Lỗi xuất Excel:\s*/,"")||"Kiểm tra lại lịch rồi thử lại.",
      buttonLabel:"Kiểm tra lại & Xuất Excel",
    }
  }
  if(!validation){
    return {
      tone:"pending",
      label:"Đang kiểm tra lịch",
      detail:"Nút xuất sẽ kiểm tra lại đúng lịch hiện tại trước khi tạo file.",
      buttonLabel:"Kiểm tra & Xuất Excel",
    }
  }
  if(validation.status==="INVALID"){
    return {
      tone:"invalid",
      label:"Lịch còn lỗi bắt buộc",
      detail:`${validation.errors?.length||0} lỗi đang được cảnh báo · vẫn có thể xuất đúng lịch hiện tại.`,
      buttonLabel:"Vẫn xuất Excel",
    }
  }
  if(!dirty){
    return {
      tone:"ready",
      label:"Đã xuất Excel bản hiện tại",
      detail:"Nếu chỉnh lịch tiếp, hệ thống sẽ xuất một bản mới theo thay đổi mới nhất.",
      buttonLabel:"Xuất lại Excel",
    }
  }
  if(validation.status==="VALID_WITH_WARNINGS"||(validation.warnings?.length||0)>0){
    return {
      tone:"warning",
      label:"Có cảnh báo nhưng vẫn có thể xuất",
      detail:`${validation.warnings?.length||0} cảnh báo · Excel vẫn lấy đúng lịch đang nhìn thấy.`,
      buttonLabel:"Kiểm tra & Xuất Excel",
    }
  }
  return {
    tone:"ready",
    label:"Lịch sẵn sàng xuất",
    detail:"Excel sẽ lấy đúng lịch hiện tại và không chạy lại optimizer.",
    buttonLabel:"Kiểm tra & Xuất Excel",
  }
}

function addDaysUtil(iso, n) {
  const [y, m, d] = String(iso).split("-").map(Number)
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() + n)
  const yr = dt.getFullYear(), mo = String(dt.getMonth() + 1).padStart(2, "0"), da = String(dt.getDate()).padStart(2, "0")
  return `${yr}-${mo}-${da}`
}

function fmtDateUtil(iso) {
  const parts = String(iso).split("-")
  return parts.length >= 3 ? `${parts[2]}/${parts[1]}` : iso
}

export function validateConfigPreflight(config) {
  const errors = []
  if (!config) return { valid: true, errors }

  const employees = config.employees || []
  const active = employees.filter(e => e.active)
  if (active.length === 0) {
    errors.push("Cần ít nhất 1 nhân viên đang hoạt động.")
    return { valid: false, errors }
  }

  const managers = active.filter(e => e.role === "STORE_MANAGER")
  if (managers.length === 0) {
    errors.push("Chưa có Cửa hàng trưởng (CHT) nào đang hoạt động. Vui lòng chọn đúng 1 CHT.")
  } else if (managers.length > 1) {
    errors.push(`Có ${managers.length} CHT đang hoạt động. Hệ thống yêu cầu phải có đúng 1 CHT.`)
  }

  const activeIds = new Set(active.map(e => e.id))
  const staffing = config.staffing || []
  const receivingDays = config.receiving_days || []

  for (const s of staffing) {
    const m = Number(s.morning || 0)
    const a = Number(s.afternoon || 0)
    const dLabel = dayLabel(config, s.date)
    const fDate = fmtDateUtil(s.date)
    if (m > 3) {
      errors.push(`${dLabel} (${fDate}): Ca Sáng tối đa 3 người (hiện đặt ${m}).`)
    }
    if (m + a > active.length) {
      errors.push(
        `${dLabel} (${fDate}): Nhu cầu ${m} Sáng + ${a} Chiều (${m + a} người) vượt số nhân viên đang có (${active.length} người).`
      )
    }
  }

  for (const r of receivingDays) {
    const s = staffing.find(item => item.date === r.date)
    const aft = Number(s?.afternoon || 0)
    const rCount = Number(r.count || 0)
    const dLabel = dayLabel(config, r.date)
    const fDate = fmtDateUtil(r.date)
    if (rCount > aft) {
      errors.push(
        `Ngày nhận hàng ${dLabel} (${fDate}): Số người nhận hàng (${rCount}) vượt quá quân số ca Chiều (${aft}).`
      )
    }
  }

  for (const [idx, p] of (config.pairing_rules || []).entries()) {
    const type = p.relation_type || (p.max_same_shifts_per_week != null ? "MAX" : "UNLIMITED")
    if (["MAX", "MIN", "EXACT", "PREFER_TOGETHER"].includes(type)) {
      const count = p.count ?? p.max_same_shifts_per_week
      if (count === null || count === "" || isNaN(count)) {
        errors.push(`Quan hệ #${idx + 1} (${employeeName(config, p.employee_a)} ↔ ${employeeName(config, p.employee_b)}): Thiếu số ca/tuần cho loại ${type}.`)
      }
    }
  }

  const hardByEmpDate = new Map()
  for (const f of config.fixed_weekday_rules || []) {
    if (f.level === "HARD" && activeIds.has(f.employee_id)) {
      const d = addDaysUtil(config.week_start, Number(f.weekday))
      const k = `${f.employee_id}|${d}`
      if (!hardByEmpDate.has(k)) hardByEmpDate.set(k, [])
      hardByEmpDate.get(k).push({
        source: f.source === "REGIONAL" ? "QLKV" : "Ca cố định",
        shift: f.shift,
      })
    }
  }

  for (const req of config.requests || []) {
    if (["OFF", "MUST_MORNING", "MUST_AFTERNOON"].includes(req.type) && activeIds.has(req.employee_id)) {
      const shift = req.type === "OFF" ? "OFF" : req.type === "MUST_MORNING" ? "MORNING" : "AFTERNOON"
      const k = `${req.employee_id}|${req.date}`
      if (!hardByEmpDate.has(k)) hardByEmpDate.set(k, [])
      hardByEmpDate.get(k).push({
        source: "Nguyện vọng",
        shift,
      })
    }
  }

  for (const [k, entries] of hardByEmpDate.entries()) {
    const distinct = new Set(entries.map(e => e.shift))
    if (distinct.size > 1) {
      const [empId, d] = k.split("|")
      const name = employeeName(config, empId)
      const dLabel = dayLabel(config, d)
      const fDate = fmtDateUtil(d)
      const desc = entries.map(e => `${e.source} (${e.shift === "MORNING" ? "Sáng" : e.shift === "AFTERNOON" ? "Chiều" : "OFF"})`).join(" vs ")
      errors.push(`Xung đột ca bắt buộc: ${name} ngày ${dLabel} (${fDate}) có ${desc}.`)
    }
  }

  return { valid: errors.length === 0, errors }
}

export const DRAFT_STORAGE_KEY = "ctkm.scheduling.draft.v1"

export function saveDraft(data, storage = typeof localStorage !== "undefined" ? localStorage : null) {
  if (!storage || !data || !data.config) return false
  try {
    const payload = {
      version: 1,
      savedAt: Date.now(),
      config: data.config,
      assignments: Array.isArray(data.assignments) ? data.assignments : [],
      manualTouched: Array.from(data.manualTouched || []),
      variant: data.variant || "manual",
    }
    storage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

export function loadDraft(storage = typeof localStorage !== "undefined" ? localStorage : null) {
  if (!storage) return null
  try {
    const raw = storage.getItem(DRAFT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object" || !parsed.config) return null
    return {
      config: parsed.config,
      assignments: Array.isArray(parsed.assignments) ? parsed.assignments : [],
      manualTouched: new Set(Array.isArray(parsed.manualTouched) ? parsed.manualTouched : []),
      variant: parsed.variant || "manual",
      savedAt: parsed.savedAt || null,
    }
  } catch {
    return null
  }
}

export function clearDraft(storage = typeof localStorage !== "undefined" ? localStorage : null) {
  if (!storage) return false
  try {
    storage.removeItem(DRAFT_STORAGE_KEY)
    return true
  } catch {
    return false
  }
}


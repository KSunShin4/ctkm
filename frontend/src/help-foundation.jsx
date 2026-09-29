import React,{useId,useState} from "react"
import {useUiPreferences} from "./ui-preferences.js"

export const MODULE_HELP={
  schedule:{title:"Xếp lịch",summary:"Tạo, chỉnh và xuất lịch tuần.",quickStart:"Đi theo 6 bước từ chọn tuần đến xuất Excel. HARD/SOFT và các rule nâng cao chỉ cần mở khi bạn cần tinh chỉnh."},
  ops:{title:"CTKM / Tem",summary:"Tổng hợp CTKM, POG, Clearance, Tem R và hỗ trợ kiểm tem.",mapping:"Nếu hệ thống không đủ chắc chắn về tên cột, hãy xác nhận mapping theo giá trị thực tế trước khi tiếp tục."},
  guide:{title:"Hướng dẫn",summary:"Tra cứu Quick Start, khái niệm và lỗi thường gặp theo từng module."},
  assistant:{title:"Trợ lý",summary:"Đưa gợi ý và giải thích; người dùng vẫn là người quyết định áp dụng."},
  settings:{title:"Cài đặt",summary:"Cấu hình chung; không chứa thao tác nghiệp vụ hằng ngày."},
}
export function HelpTip({title="Trợ giúp",text,children}){
  const prefs=useUiPreferences()
  const [open,setOpen]=useState(false);const id=useId();const body=text||children
  if(!prefs.help)return null
  return <span className="help-tip-wrap"><button type="button" className="help-tip-button" aria-label={title} aria-expanded={open} aria-controls={id} onClick={()=>setOpen(v=>!v)}>?</button>{open&&<span role="tooltip" id={id} className="help-tip-popover"><strong>{title}</strong><span>{body}</span></span>}</span>
}
export const helpTipCss=`.help-tip-wrap{position:relative;display:inline-flex}.help-tip-button{width:25px;height:25px;border:1px solid #d0d5dd;border-radius:50%;background:#fff;color:#475467;font:800 11px inherit;cursor:pointer}.help-tip-button:hover{border-color:#98a2b3;color:#101828}.help-tip-popover{position:absolute;right:0;top:31px;z-index:120;width:min(280px,75vw);padding:11px 12px;border:1px solid #d0d5dd;border-radius:10px;background:#fff;box-shadow:0 8px 24px rgba(16,24,40,.14);font-size:10px;line-height:1.5;color:#475467}.help-tip-popover strong,.help-tip-popover span{display:block}.help-tip-popover strong{margin-bottom:3px;color:#101828}`

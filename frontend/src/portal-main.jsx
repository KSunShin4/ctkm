import React from "react"
import ReactDOM from "react-dom/client"
import GuideApp from "./GuideApp.jsx"
import PortalPlaceholderApp from "./PortalPlaceholderApp.jsx"

const path=window.location.pathname
const root=ReactDOM.createRoot(document.getElementById("root"))
if(path.startsWith("/assistant")){
  root.render(<PortalPlaceholderApp module="assistant"/>)
}else{
  root.render(<GuideApp/>)
}

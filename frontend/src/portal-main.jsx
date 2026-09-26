import React from "react"
import ReactDOM from "react-dom/client"
import GuideApp from "./GuideApp.jsx"
import PortalPlaceholderApp from "./PortalPlaceholderApp.jsx"
import AssistantShowcase from "./AssistantShowcase.jsx"
import OverviewDashboard from "./OverviewDashboard.jsx"
const path=window.location.pathname
const root=ReactDOM.createRoot(document.getElementById("root"))
if(path.startsWith("/guide"))root.render(<GuideApp/>)
else if(path.startsWith("/assistant"))root.render(<AssistantShowcase/>)
else if(path.startsWith("/settings"))root.render(<PortalPlaceholderApp module="settings"/>)
else root.render(<OverviewDashboard/>)

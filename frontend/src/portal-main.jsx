import React from "react"
import ReactDOM from "react-dom/client"
import GuideApp from "./GuideApp.jsx"
import AssistantShowcase from "./AssistantShowcase.jsx"
import OverviewDashboard from "./OverviewDashboard.jsx"
import SettingsApp from "./SettingsApp.jsx"
const path=window.location.pathname
const root=ReactDOM.createRoot(document.getElementById("root"))
if(path.startsWith("/guide"))root.render(<GuideApp/>)
else if(path.startsWith("/assistant"))root.render(<AssistantShowcase/>)
else if(path.startsWith("/settings"))root.render(<SettingsApp/>)
else root.render(<OverviewDashboard/>)

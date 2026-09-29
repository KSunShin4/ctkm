import React from "react"
import ReactDOM from "react-dom/client"
import GuideApp from "./GuideApp.jsx"
import AssistantShowcase from "./AssistantShowcase.jsx"
import HistoryApp from "./HistoryApp.jsx"
import SettingsApp from "./SettingsApp.jsx"
import {UiPreferenceRoot,uiPreferenceCss} from "./ui-preferences.js"
const path=window.location.pathname
const root=ReactDOM.createRoot(document.getElementById("root"))
const render=component=>root.render(<UiPreferenceRoot><style>{uiPreferenceCss}</style>{component}</UiPreferenceRoot>)
if(path.startsWith("/guide"))render(<GuideApp/>)
else if(path.startsWith("/assistant"))render(<AssistantShowcase/>)
else if(path.startsWith("/history"))render(<HistoryApp/>)
else if(path.startsWith("/settings"))render(<SettingsApp/>)
else window.location.replace("/?module=ctkm")

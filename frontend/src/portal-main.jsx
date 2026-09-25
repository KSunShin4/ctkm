import React from "react"
import ReactDOM from "react-dom/client"
import PortalPlaceholderApp from "./PortalPlaceholderApp.jsx"

const path=window.location.pathname
const module=path.startsWith("/assistant")?"assistant":"guide"
ReactDOM.createRoot(document.getElementById("root")).render(<PortalPlaceholderApp module={module}/>)

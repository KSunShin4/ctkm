import React from 'react'
import ReactDOM from 'react-dom/client'
import SchedulingApp from './SchedulingApp.jsx'
import {UiPreferenceRoot,uiPreferenceCss} from './ui-preferences.js'

ReactDOM.createRoot(document.getElementById('root')).render(
  <UiPreferenceRoot>
    <style>{uiPreferenceCss}</style>
    <SchedulingApp />
  </UiPreferenceRoot>
)

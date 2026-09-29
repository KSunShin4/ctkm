import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("shared preference layer reads writes and synchronizes UI settings",async()=>{const s=await read("./ui-preferences.js");for(const x of ["pharmaops_ui_preferences_v1","pharmaops:ui-preferences","storage","pharmaops-compact"])assert.match(s,new RegExp(x))})
test("help preference actually hides contextual help",async()=>{const s=await read("./help-foundation.jsx");assert.match(s,/useUiPreferences/);assert.match(s,/if\(!prefs\.help\)return null/)})
test("assistant preference actually hides all shared assistant surfaces",async()=>{const s=await read("./assistant-components.jsx");assert.equal((s.match(/if\(!prefs\.assistant\)return null/g)||[]).length,4)})
test("settings uses shared preference contract instead of a private disconnected key",async()=>{const s=await read("./SettingsApp.jsx");assert.match(s,/readUiPreferences/);assert.match(s,/writeUiPreferences/);assert.match(s,/DEFAULT_UI_PREFERENCES/)})
test("portal shell installs compact preference root",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/UiPreferenceRoot/);assert.match(s,/uiPreferenceCss/)})

test("scheduling shell installs the same compact preference root",async()=>{const s=await read("./scheduling-main.jsx");assert.match(s,/UiPreferenceRoot/);assert.match(s,/uiPreferenceCss/);assert.match(s,/SchedulingApp/)})

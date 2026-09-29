import { useState, useCallback, useRef, useEffect } from "react"
import ProductNav from "./ProductNav.jsx"
import {HelpTip, MODULE_HELP, helpTipCss} from "./help-foundation.jsx"
import {Mascot, GuideBubble, assistantComponentCss} from "./assistant-components.jsx"

const API = import.meta.env.VITE_API_BASE_URL || ""  // relative /api by default; override in production if needed

// ─── Design tokens ────────────────────────────────────────────────────────────
// Clean pharmacy/operations UI, optimized for desktop and phone camera use.
const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #fafafa;
    --surface:   #ffffff;
    --surface2:  #f6f6f6;
    --border:    #e8e8e8;
    --border2:   #d4d4d4;
    --text:      #171717;
    --text2:     #525252;
    --text3:     #8a8a8a;
    --accent:    #171717;
    --accent2:   #000000;
    --green:     #087f5b;
    --red:       #d92d20;
    --blue:      #2563eb;
    --font:      Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --mono:      'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    --radius:    8px;
    --radius-lg: 12px;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }

  /* Layout */
  .shell     { display: flex; flex-direction: column; min-height: 100vh; }
  .topbar    { border-bottom: 1px solid var(--border); padding: 0 32px;
               display: flex; align-items: center; gap: 12px; height: 68px;
               background: rgba(255,255,255,.96); z-index: 5; }
  .topbar-logo { font-size: 19px; font-weight: 750; letter-spacing: -0.5px; color: var(--text); }
  .topbar-logo span { color: var(--green); }
  .topbar-sub  { font-size: 12px; color: var(--text3); margin-left: 4px; }
  .module-nav { display: flex; gap: 4px; margin-left: 22px; padding: 3px;
                background: var(--surface2); border-radius: 9px; }
  .module-nav button { border: 0; background: transparent; color: var(--text2); padding: 7px 12px;
                       border-radius: 8px; font-family: var(--font); font-size: 12px;
                       font-weight: 650; cursor: pointer; transition: .15s ease; }
  .module-nav button:hover { color: var(--text); }
  .module-nav button.active { color: var(--text); background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
  .backend-status { margin-left: auto; display: flex; align-items: center; gap: 7px;
                    font-size: 11px; color: var(--text3); font-family: var(--mono); }
  .auth-actions { display:flex; align-items:center; gap:8px; }
  .auth-input { width:118px; border:1px solid var(--border2); border-radius:7px;
                padding:7px 9px; font:12px var(--font); outline:none; }
  .auth-input:focus { border-color:var(--accent); }
  .auth-button { border:1px solid var(--border2); background:#fff; border-radius:7px;
                 padding:7px 10px; font:600 11px var(--font); cursor:pointer; }
  .auth-error { color:var(--red); font-size:11px; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.ok   { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .status-dot.warn { background: var(--accent); }
  .status-dot.err  { background: var(--red); }
  .main      { flex: 1; display: grid; grid-template-columns: 340px minmax(0, 1fr);
               gap: 0; height: calc(100vh - 68px); overflow: hidden; }
  .sidebar   { border-right: 1px solid var(--border); overflow-y: auto;
               padding: 24px 20px; display: flex; flex-direction: column; gap: 16px;
               background: #fff; }
  .content   { overflow-y: auto; padding: 28px 32px 48px; }
  .main.expiration-mode { grid-template-columns: 1fr; }
  .main.expiration-mode .sidebar { display: none; }
  .main.expiration-mode .content { width: 100%; max-width: 1120px; margin: 0 auto; }
  .main.expiration-mode .content > :not(.expiration-card) { display: none; }
  .main.inventory-mode { display:block; height:auto; overflow:visible; }
  .main.inventory-mode .sidebar { display:none; }
  .main.inventory-mode .content { width:100%; max-width:1120px; margin:0 auto; }
  .main.inventory-mode .content > :not(.inventory-card) { display:none; }
  .main.ctkm-mode .expiration-card { display: none; }
  .main.ctkm-mode .inventory-card { display:none; }
  .main.ctkm-mode .tem-r-card { display: none; }
  .main.temr-mode { display: block; height: calc(100vh - 68px); overflow-y: auto; }
  .main.temr-mode .content { display: none; }
  .main.temr-mode .sidebar { width: 100%; max-width: 620px; margin: 0 auto; border: 0;
                            background: transparent; overflow: visible; padding: 32px 20px; }
  .main.temr-mode .sidebar > :not(.tem-r-card) { display: none; }

  /* Cards */
  .card      { background: var(--surface); border: 1px solid var(--border);
               border-radius: var(--radius-lg); padding: 20px; box-shadow: none; }
  .card-title { font-size: 13px; font-weight: 650; letter-spacing: -.01em;
                color: var(--text2); margin-bottom: 16px; }

  /* File drop zone */
  .dropzone  { border: 1px dashed var(--border2); border-radius: var(--radius);
               padding: 20px 16px; text-align: center; cursor: pointer;
               transition: all .15s; background: var(--surface2); }
  .dropzone:hover, .dropzone.over { border-color: var(--text); background: #fafafa; }
  .dropzone.filled { border-style: solid; border-color: var(--green); }
  .dropzone-icon { font-size: 24px; margin-bottom: 6px; }
  .dropzone-label { font-size: 13px; font-weight: 500; color: var(--text); }
  .dropzone-sub   { font-size: 11px; color: var(--text3); margin-top: 3px; }
  .dropzone-file  { font-size: 12px; color: var(--green); font-family: var(--mono);
                    margin-top: 6px; word-break: break-all; }

  /* Month picker */
  .month-input { width: 100%; background: var(--surface2); border: 1px solid var(--border2);
                 border-radius: var(--radius); padding: 9px 12px; color: var(--text);
                 font-family: var(--mono); font-size: 14px; outline: none;
                 transition: border-color .15s; }
  .month-input:focus { border-color: var(--accent); }
  .entry-input { width: 100%; min-height: 132px; resize: vertical; background: var(--surface2);
                 border: 1px solid var(--border2); border-radius: var(--radius); padding: 11px 12px;
                 color: var(--text); font-family: var(--mono); font-size: 13px; outline: none;
                 line-height: 1.65; }
  .entry-input:focus { border-color: var(--accent); }
  .expiration-grid { display: grid; grid-template-columns: minmax(250px, .75fr) minmax(340px, 1.25fr);
                     gap: 16px; align-items: start; }
  .result-status { display: inline-flex; padding: 2px 8px; border-radius: 999px;
                   font-size: 11px; font-weight: 600; white-space: nowrap; }
  .result-status.matched { color: #067647; background: #ecfdf3; }
  .result-status.related { color: #1d4ed8; background: #eff6ff; }
  .result-status.invalid, .result-status.not_found,
  .result-status.batch_mismatch, .result-status.date_mismatch { color: #b42318; background: #fef3f2; }
  .camera-wrap { position: relative; overflow: hidden; border: 1px solid var(--border2);
                 border-radius: var(--radius); background: #050608; margin-top: 10px; }
  .camera-video { display: block; width: 100%; max-height: 320px; object-fit: cover; }
  .camera-guide { position: absolute; inset: 22% 10%; border: 2px solid var(--accent);
                  border-radius: 10px; box-shadow: 0 0 0 999px rgba(0,0,0,.3); pointer-events: none; }
  .camera-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }

  .sheet-select {
    width: 100%; background: var(--surface2); border: 1px solid var(--border2);
    border-radius: var(--radius); padding: 9px 12px; color: var(--text);
    font-family: var(--font); font-size: 13px; outline: none;
    transition: border-color .15s; margin-top: 10px;
  }
  .sheet-select:focus { border-color: var(--accent); }
  .ops-assistant{display:flex;align-items:flex-start;gap:10px;margin:0 0 14px;padding:12px;border:1px solid var(--border);border-radius:var(--radius-lg);background:var(--surface)}.ops-assistant .mascot-avatar{width:42px;height:42px;border-radius:14px}.ops-assistant-copy{flex:1;min-width:0}.ops-assistant-title{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:750;margin-bottom:6px}.metric-help{display:flex;align-items:center;justify-content:center;gap:5px}
  .mapping-row { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 10px;
                 align-items: center; margin-bottom: 8px; }
  .mapping-field { color: var(--text2); font-size: 12px; }
  .mapping-row .sheet-select { width: 100%; min-width: 0; }
  .sheet-hint { font-size: 11px; color: var(--text3); margin-top: 6px; }

  /* Button */
  .btn { display: flex; align-items: center; justify-content: center; gap: 8px;
         width: 100%; min-height: 44px; padding: 11px 14px; border-radius: var(--radius); border: none;
         font-family: var(--font); font-size: 14px; font-weight: 600;
         cursor: pointer; transition: all .15s; }
  .btn-primary { background: var(--accent); color: #fff; box-shadow: none; }
  .btn-primary:hover:not(:disabled) { background: var(--accent2); }
  .btn-primary:disabled { opacity: .4; cursor: not-allowed; }
  .btn-ghost { background: var(--surface2); color: var(--text);
               border: 1px solid var(--border2); }
  .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }

  /* Spinner */
  .spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.35);
             border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Status strip */
  .status-strip { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
                  border-radius: var(--radius); font-size: 13px; font-weight: 500; }
  .status-strip.info    { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
  .status-strip.success { background: #ecfdf3; color: #067647; border: 1px solid #abefc6; }
  .status-strip.warn    { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
  .status-strip.error   { background: #fef3f2; color: #b42318; border: 1px solid #fecdca; }
  .expiration-card { padding: 20px 0; border: 0; background: transparent; box-shadow: none; }
  .expiration-header { display: flex; align-items: flex-start; justify-content: space-between;
                       gap: 16px; margin-bottom: 22px; }
  .expiration-kicker { color: var(--green); font-size: 11px; font-weight: 750;
                       letter-spacing: .08em; text-transform: uppercase; margin-bottom: 5px; }
  .expiration-title { font-size: 30px; line-height: 1.15; letter-spacing: -.8px; font-weight: 720; }
  .expiration-subtitle { margin-top: 7px; color: var(--text2); font-size: 13px; }
  .format-pill { padding: 7px 10px; border-radius: 7px; border: 1px solid var(--border);
                 background: #fff; color: var(--text2); font-family: var(--mono); font-size: 11px; white-space: nowrap; }
  .ctkm-mode .sidebar .card { border: 0; border-bottom: 1px solid var(--border);
                              border-radius: 0; padding: 16px 2px 22px; background: transparent; }
  .advanced-card.hidden { display: none !important; }
  .advanced-toggle { background: transparent; border: 0; color: var(--text2); font-family: var(--font);
                     font-size: 12px; font-weight: 650; cursor: pointer; text-align: left;
                     padding: 2px 2px 10px; }
  .advanced-toggle:hover { color: var(--text); }

  /* Summary grid */
  .summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .stat-box { background: var(--surface2); border: 1px solid var(--border);
              border-radius: var(--radius); padding: 14px 16px; }
  .stat-num  { font-size: 26px; font-weight: 600; font-family: var(--mono);
               color: var(--accent); letter-spacing: -1px; line-height: 1; }
  .stat-label { font-size: 11px; color: var(--text2); margin-top: 4px; }
  .stat-sub   { font-size: 10px; color: var(--text3); margin-top: 2px; }

  /* Tab bar */
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border);
          margin-bottom: 20px; overflow-x: auto; }
  .tab  { padding: 9px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
          border-bottom: 2px solid transparent; color: var(--text2); white-space: nowrap;
          background: none; border-top: none; border-left: none; border-right: none;
          font-family: var(--font); transition: all .12s; }
  .tab:hover  { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-badge  { display: inline-flex; align-items: center; justify-content: center;
                background: var(--border2); color: var(--text2); border-radius: 10px;
                font-size: 10px; padding: 1px 6px; margin-left: 6px; font-family: var(--mono); }
  .tab.active .tab-badge { background: var(--accent); color: #0f1117; }

  /* Table */
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }
  table { border-collapse: collapse; width: 100%; min-width: 600px; font-size: 12.5px; }
  thead th { background: var(--surface2); padding: 9px 12px; text-align: left;
             font-size: 11px; font-weight: 600; color: var(--text2); white-space: nowrap;
             border-bottom: 1px solid var(--border2); letter-spacing: .04em; }
  tbody td { padding: 8px 12px; border-bottom: 1px solid var(--border);
             color: var(--text); max-width: 220px; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono);
             font-size: 12px; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: var(--surface2); }

  /* Warnings */
  .warn-list { display: flex; flex-direction: column; gap: 8px; }
  .warn-item { background: var(--surface2); border-left: 3px solid var(--accent);
               border-radius: 0 var(--radius) var(--radius) 0;
               padding: 10px 14px; font-size: 12.5px; color: var(--text2); }

  /* Empty */
  .empty { text-align: center; padding: 60px 20px; color: var(--text3); }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-title { font-size: 15px; font-weight: 500; color: var(--text2); margin-bottom: 6px; }

  /* Download bar */
  .download-bar { display: flex; align-items: center; gap: 12px; padding: 14px 18px;
                  background: var(--surface); border: 1px solid var(--border);
                  border-radius: var(--radius-lg); margin-bottom: 24px; }
  .download-info { flex: 1; }
  .download-name { font-size: 13px; font-weight: 600; color: var(--text); }
  .download-meta { font-size: 11px; color: var(--text3); margin-top: 2px; font-family: var(--mono); }

  /* Progress */
  .progress-wrap { margin: 16px 0; }
  .progress-bar  { height: 3px; background: var(--border); border-radius: 99px; overflow: hidden; }
  .progress-fill { height: 100%; background: var(--accent);
                   animation: progress-pulse 1.5s ease-in-out infinite; }
  @keyframes progress-pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  .progress-label { font-size: 11px; color: var(--text3); margin-top: 6px; font-family: var(--mono); }

  /* Section title */
  .section-title { font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text); }
  .section-title span { color: var(--text3); font-weight: 400; font-size: 13px; margin-left: 8px; }

  /* Row count */
  .row-count { font-size: 11px; color: var(--text3); margin-bottom: 10px; font-family: var(--mono); }

  .output-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }

  /* Responsive */
  @media (max-width: 768px) {
    body { font-size: 13px; }
    .topbar { height: auto; min-height: 56px; padding: 10px 16px; flex-wrap: wrap; }
    .topbar-logo { font-size: 16px; }
    .topbar-sub { display: none; }
    .module-nav { order: 3; width: 100%; margin: 2px 0 0; }
    .module-nav button { flex: 1; min-height: 38px; }
    .backend-status { font-size: 10px; }
    .main { display: flex; flex-direction: column; height: auto; overflow: visible; }
    .sidebar { border-right: none; border-bottom: 1px solid var(--border);
               max-height: none; overflow: visible; padding: 16px 12px; gap: 16px; order: 2; }
    .content { overflow: visible; padding: 16px 12px 28px; order: 1; }
    .card { padding: 16px 12px; border-radius: 10px; }
    .expiration-card { padding: 20px 16px; border-radius: 16px; }
    .expiration-header { display: block; margin-bottom: 18px; }
    .expiration-title { font-size: 21px; }
    .format-pill { display: inline-flex; margin-top: 12px; }
    .summary-grid, .output-field-grid { grid-template-columns: 1fr; }
    .download-bar { align-items: stretch; flex-direction: column; }
    .download-bar .btn { width: 100% !important; }
    .empty { padding: 36px 12px; }

    /* Mapping is a form on mobile, so cards are easier to use than a wide table. */
    .mapping-table { overflow: visible !important; max-height: none !important; border: 0; }
    .mapping-table table,
    .mapping-table tbody,
    .mapping-table tr,
    .mapping-table td { display: block; width: 100%; min-width: 0; }
    .mapping-table thead { display: none; }
    .mapping-table tbody { display: grid; gap: 10px; }
    .mapping-table tr { padding: 12px; background: var(--surface2);
                        border: 1px solid var(--border); border-radius: var(--radius); }
    .mapping-table tbody td { max-width: none; white-space: normal; overflow: visible;
                              border: 0; padding: 3px 0; font-family: var(--font); }
    .mapping-table tbody td:first-child { font-family: var(--mono); font-weight: 600;
                                          overflow-wrap: anywhere; color: var(--text); }
    .mapping-table tbody td:nth-child(2),
    .mapping-table tbody td:nth-child(3) { display: inline; color: var(--text2); font-size: 11px; }
    .mapping-table tbody td:nth-child(2)::before { content: "Gợi ý: "; color: var(--text3); }
    .mapping-table tbody td:nth-child(3)::before { content: " · Tin cậy: "; color: var(--text3); }
    .mapping-table tbody td:last-child { margin-top: 8px; }
    .mapping-table .sheet-select { min-width: 0 !important; width: 100%; min-height: 44px; }
    .mapping-row { grid-template-columns: 1fr; gap: 5px; padding: 8px 0; }
  }

  @media (max-width: 380px) {
    .topbar { align-items: flex-start; }
    .backend-status { width: 100%; margin-left: 0; }
    .stat-num { font-size: 22px; }
  }
  @media (max-width: 900px) { .expiration-grid { grid-template-columns: 1fr; } }

  /* ── Approved mockup alignment: one shared PharmaOps shell ─────────────── */
  body { background:#f5f7fb; color:#17202a; }
  .shell { min-height:calc(100vh - 58px); background:#f5f7fb; }
  .ops-page-head { max-width:1180px; margin:0 auto; padding:24px 18px 14px; }
  .ops-hero { display:flex; justify-content:space-between; align-items:flex-start; gap:24px;
              padding:22px 24px; background:#fff; border:1px solid #e4e7ec;
              border-radius:18px; box-shadow:0 2px 10px rgba(16,24,40,.04); }
  .ops-hero-copy { min-width:0; max-width:680px; }
  .ops-kicker { color:#087f5b; font-size:10px; font-weight:900; letter-spacing:.09em;
                text-transform:uppercase; }
  .ops-hero h1 { margin:6px 0 7px; font-size:28px; line-height:1.15; letter-spacing:-.65px;
                 color:#17202a; font-weight:760; }
  .ops-hero p { margin:0; color:#667085; font-size:12px; line-height:1.6; }
  .ops-hero-side { min-width:290px; display:flex; flex-direction:column; align-items:flex-end; gap:10px; }
  .ops-backend-status { margin-left:0; padding:6px 9px; border:1px solid #e4e7ec;
                        border-radius:999px; background:#f9fafb; color:#667085; }
  .admin-pill { padding:4px 7px; border-radius:999px; background:#ecfdf3; color:#067647;
                font-size:9px; font-weight:900; letter-spacing:.04em; }
  .auth-actions { justify-content:flex-end; }
  .auth-input { background:#fff; border-color:#d0d5dd; }
  .auth-button { color:#344054; border-color:#d0d5dd; }
  .ops-tool-tabs { display:flex; align-items:center; gap:5px; margin-top:12px; padding:6px;
                   background:#fff; border:1px solid #e4e7ec; border-radius:14px;
                   box-shadow:0 1px 4px rgba(16,24,40,.03); overflow-x:auto; scrollbar-width:none; }
  .ops-tool-tabs::-webkit-scrollbar { display:none; }
  .ops-tool-tab,.ops-tool-link { display:inline-flex; align-items:center; gap:7px; min-height:38px;
                                 flex:0 0 auto; padding:8px 11px; border:0; border-radius:10px;
                                 background:transparent; color:#475467; text-decoration:none;
                                 font:750 11px var(--font); cursor:pointer; white-space:nowrap; }
  .ops-tool-tab:hover,.ops-tool-link:hover { background:#f2f4f7; color:#17202a; }
  .ops-tool-tab.active { background:#eef4ff; color:#175cd3; box-shadow:inset 0 0 0 1px #d1e0ff; }
  .ops-tool-icon { width:18px; height:18px; border-radius:6px; display:grid; place-items:center;
                   background:#f2f4f7; font-size:10px; font-weight:900; }
  .ops-tool-tab.active .ops-tool-icon { background:#dbeafe; color:#175cd3; }
  .ops-tool-divider { width:1px; height:22px; background:#e4e7ec; margin:0 2px; flex:0 0 1px; }

  .main { width:100%; max-width:1180px; margin:0 auto; padding:0 18px 80px;
          display:grid; grid-template-columns:360px minmax(0,1fr); gap:14px;
          height:auto; overflow:visible; align-items:start; }
  .sidebar { border:0; background:transparent; padding:0; gap:12px; overflow:visible; }
  .content { padding:0; overflow:visible; min-width:0; }
  .card { border:1px solid #e4e7ec; border-radius:16px; padding:18px;
          background:#fff; box-shadow:0 2px 10px rgba(16,24,40,.035); }
  .card-title { color:#344054; font-size:12px; font-weight:800; margin-bottom:13px; }
  .ctkm-mode .sidebar .card { border:1px solid #e4e7ec; border-radius:16px; padding:18px;
                              background:#fff; box-shadow:0 2px 10px rgba(16,24,40,.035); }
  .dropzone { background:#f9fafb; border-color:#d0d5dd; border-radius:11px; }
  .dropzone:hover,.dropzone.over { border-color:#84adff; background:#f5f8ff; }
  .dropzone.filled { border-color:#6ce9a6; background:#f6fef9; }
  .btn { border-radius:10px; }
  .btn-primary { background:#175cd3; }
  .btn-primary:hover:not(:disabled) { background:#1849a9; }
  .btn-ghost { background:#fff; border-color:#d0d5dd; color:#344054; }
  .btn-ghost:hover { border-color:#84adff; color:#175cd3; }
  .summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
  .stat-box { background:#fff; border-color:#e4e7ec; border-radius:12px; }
  .stat-num { color:#175cd3; font-size:24px; }
  .tabs { background:#fff; border:1px solid #e4e7ec; border-radius:12px; padding:4px;
          margin-bottom:12px; overflow-x:auto; }
  .tab { border-radius:8px; border-bottom:0; padding:8px 11px; }
  .tab.active { background:#eef4ff; color:#175cd3; border-bottom-color:transparent; }
  .tab.active .tab-badge { background:#175cd3; color:#fff; }
  .table-wrap { background:#fff; border-color:#e4e7ec; border-radius:12px; }
  .ctkm-workspace{margin-top:10px;background:linear-gradient(180deg,#fff,#fbfdff);border:1px solid #e1e9f5;border-radius:18px;padding:16px;box-shadow:0 8px 24px rgba(39,85,145,.05)}
  .ctkm-workspace-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:13px}.ctkm-workspace-kicker{font-size:9px;color:#1769ff;font-weight:950;text-transform:uppercase;letter-spacing:.09em}.ctkm-workspace h2{margin:3px 0 4px;font-size:18px;color:#173052}.ctkm-workspace p{margin:0;color:#788ba8;font-size:10px;line-height:1.45}.ctkm-shelf-cta{flex:0 0 auto;text-decoration:none;background:#e9fbf3;color:#0b8b59;border:1px solid #c8f0dd;border-radius:10px;padding:9px 11px;font-size:9px;font-weight:900}
  .ctkm-operation-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin-bottom:10px}.ctkm-operation-tabs button{border:1px solid #e4ebf5;background:#f8faff;border-radius:11px;padding:9px 8px;color:#647995;display:flex;justify-content:center;align-items:center;gap:6px;font:850 9px var(--font);cursor:pointer}.ctkm-operation-tabs button b{padding:2px 6px;background:#fff;border-radius:999px;color:#627995}.ctkm-operation-tabs button.active{border-color:#bad3ff;background:#eaf2ff;color:#1769ff}.ctkm-operation-tabs button.active b{background:#1769ff;color:#fff}
  .ctkm-list-tools{display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:8px;margin-bottom:10px}.ctkm-search{display:flex;align-items:center;gap:7px;border:1px solid #dce6f2;background:#fff;border-radius:10px;padding:0 10px}.ctkm-search span{color:#8ba0bc;font-size:18px}.ctkm-search input{border:0;outline:0;min-width:0;width:100%;padding:10px 0;background:transparent;font:500 10px var(--font)}.ctkm-list-tools select{border:1px solid #dce6f2;border-radius:10px;background:#fff;color:#526985;padding:9px;font:750 9px var(--font)}.ctkm-filter-note{font-size:9px;color:#7c8fa8;margin-top:8px}
  @media(max-width:760px){.ctkm-workspace{padding:12px;border-radius:15px}.ctkm-workspace-head{display:block}.ctkm-shelf-cta{display:inline-flex;margin-top:10px}.ctkm-operation-tabs{display:flex;overflow-x:auto}.ctkm-operation-tabs button{flex:0 0 auto;min-width:88px}.ctkm-list-tools{grid-template-columns:1fr}.ctkm-workspace .table-wrap table{min-width:760px}}
  thead th { position:sticky; top:0; z-index:1; background:#f8fafc; color:#475467;
             border-bottom-color:#e4e7ec; }
  tbody td { border-bottom-color:#f0f1f3; }
  tbody tr:hover td { background:#f9fafb; }
  .expiration-card { background:#fff; border:1px solid #e4e7ec; border-radius:18px; padding:22px;
                     box-shadow:0 2px 10px rgba(16,24,40,.04); }
  .tem-r-card{border-color:#eadcff!important;background:linear-gradient(180deg,#fff,#fdfaff)!important}
  .inventory-card{background:linear-gradient(180deg,#fff,#fffaf5);border:1px solid #f0e1cf;border-radius:18px;padding:22px;box-shadow:0 8px 28px rgba(130,85,35,.05);margin-bottom:20px}
  .inventory-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.inventory-kicker{font-size:9px;font-weight:950;color:#e87918;text-transform:uppercase;letter-spacing:.09em}.inventory-head h1{font-size:22px;margin:4px 0 4px;color:#173052}.inventory-head p{margin:0;color:#7b8ba1;font-size:10px;line-height:1.5}.inventory-rule{max-width:360px;padding:9px 11px;border-radius:11px;background:#fff7e9;color:#a55f15;border:1px solid #f6dfbd;font-size:9px;font-weight:750}
  .inventory-setup{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(0,1.2fr);gap:12px;margin-bottom:14px}.inventory-config{background:#fff;border:1px solid #e8edf4;border-radius:14px;padding:13px}.inventory-config h3{margin:0 0 8px;font-size:11px}.inventory-config-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.inventory-config select{width:100%;border:1px solid #dce6f2;border-radius:9px;background:#fff;padding:9px;font:700 9px var(--font)}.inventory-run{margin-top:10px}
  .inventory-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}.inventory-stat{padding:10px;border-radius:12px;background:#fff;border:1px solid #e5ebf3}.inventory-stat span{display:block;color:#7b8da7;font-size:8px}.inventory-stat strong{display:block;margin-top:3px;font-size:20px}.inventory-stat.ok strong{color:#0c9d65}.inventory-stat.warn strong{color:#d77216}.inventory-stat.bad strong{color:#d34852}
  .inventory-tools{display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:8px;margin:10px 0}.inventory-tools input,.inventory-tools select{border:1px solid #dce5ef;border-radius:10px;background:#fff;padding:10px;font:600 9px var(--font);outline:0}.inventory-status{display:inline-flex;padding:4px 7px;border-radius:999px;font-size:8px;font-weight:900}.inventory-status.ok{background:#e9f9f1;color:#0b8d5d}.inventory-status.stock_missing{background:#fff0f1;color:#c83d48}.inventory-status.stock_conflict{background:#fff0f1;color:#c83d48}.inventory-status.location_missing{background:#fff5df;color:#b86b12}.inventory-position-list{font-size:9px;color:#657a98;max-width:260px;white-space:normal}
  @media(max-width:760px){.inventory-card{padding:14px}.inventory-head{display:block}.inventory-rule{margin-top:10px;max-width:none}.inventory-setup{grid-template-columns:1fr}.inventory-config-row{grid-template-columns:1fr}.inventory-stats{grid-template-columns:1fr 1fr}.inventory-tools{grid-template-columns:1fr}.inventory-card .table-wrap table{min-width:820px}}
  .main.expiration-mode { display:block; max-width:1180px; height:auto; overflow:visible; }
  .main.expiration-mode .content { width:100%; max-width:none; margin:0; }
  .main.temr-mode { display:block; max-width:1180px; height:auto; overflow:visible; }
  .main.temr-mode .sidebar { width:100%; max-width:760px; margin:0 auto; border:0;
                            background:transparent; overflow:visible; padding:0; }

  @media (max-width: 760px) {
    body { padding-bottom:68px; }
    .ops-page-head { padding:14px 10px 10px; }
    .ops-hero { display:block; padding:17px 16px; border-radius:15px; }
    .ops-hero h1 { font-size:22px; }
    .ops-hero-side { min-width:0; width:100%; margin-top:14px; align-items:stretch; }
    .ops-backend-status { align-self:flex-start; }
    .auth-actions { width:100%; display:grid; grid-template-columns:1fr 1fr auto; gap:6px; justify-content:stretch; }
    .auth-input { width:100%; min-width:0; }
    .auth-error { grid-column:1 / -1; }
    .ops-tool-tabs { position:sticky; top:52px; z-index:40; border-radius:12px; }
    .main { display:flex; flex-direction:column; padding:0 10px 86px; gap:12px; }
    .sidebar { order:1; padding:0; border:0; gap:12px; }
    .content { order:2; padding:0; }
    .card { border-radius:14px; padding:15px; }
    .summary-grid { grid-template-columns:1fr 1fr; }
  }
  @media (max-width: 430px) {
    .auth-actions { grid-template-columns:1fr; }
    .summary-grid { grid-template-columns:1fr; }
    .ops-tool-divider { display:none; }
  }
`

// ─── Helpers ──────────────────────────────────────────────────────────────────
function useDropzone(onFile) {
  const [over, setOver] = useState(false)
  const ref = useRef()
  const onDrop = useCallback(e => {
    e.preventDefault(); setOver(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.endsWith(".xlsx")) onFile(f)
  }, [onFile])
  const onDrag = useCallback(e => { e.preventDefault(); setOver(true) }, [])
  const onLeave = useCallback(() => setOver(false), [])
  const onClick = () => ref.current?.click()
  const onChange = e => { const f = e.target.files[0]; if (f) onFile(f) }
  return { ref, over, onDrop, onDrag, onLeave, onClick, onChange }
}

function expirationTime(value) {
  const [day, month, year] = String(value || "").split("/").map(Number)
  return day && month && year ? new Date(year, month - 1, day).getTime() : 0
}

function expirationDisplayRows(result, filter, sort) {
  const rows = (result?.results || []).flatMap(query => {
    if (!query.related_rows?.length) return [{...query, rowKey:`${query.line}-input`, exact:query.status === "matched"}]
    return query.related_rows.map((related, index) => ({
      ...query, ...related,
      rowKey: `${query.line}-${related.batch_number}-${related.exp_date}-${index}`,
      exact: query.status === "matched" && related.batch_number === query.batch_number && related.exp_date === query.exp_date,
      status: query.status === "matched" && related.batch_number === query.batch_number && related.exp_date === query.exp_date ? "matched" : "related",
      message: related.batch_number === query.batch_number && related.exp_date === query.exp_date ? query.message : "Cùng mã P · lô/hạn dùng khác",
    }))
  }).filter(row => filter === "all" || (filter === "matched" ? row.exact : !row.exact))
  return rows.sort((a, b) => {
    if (sort === "expiry_asc") return expirationTime(a.exp_date) - expirationTime(b.exp_date)
    if (sort === "item") return String(a.item_id || "").localeCompare(String(b.item_id || "")) || expirationTime(b.exp_date) - expirationTime(a.exp_date)
    if (sort === "input") return a.line - b.line
    return expirationTime(b.exp_date) - expirationTime(a.exp_date)
  })
}

function fmt(n) { return typeof n === "number" ? n.toLocaleString("vi-VN") : n ?? "—" }

function normalizeColumn(text) {
  return String(text ?? "").trim().toLowerCase().replace(/\s+/g, " ")
}

function buildColumnSignature(columns) {
  return (columns || []).map(normalizeColumn).sort().join("|")
}

function readJsonStorage(key, fallback) {
  try {
    if (typeof window === "undefined") return fallback
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

function writeJsonStorage(key, value) {
  try {
    if (typeof window === "undefined") return
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore storage failures
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function Dropzone({ label, sub, file, onFile }) {
  const dz = useDropzone(onFile)
  return (
    <div
      className={`dropzone${file ? " filled" : ""}${dz.over ? " over" : ""}`}
      onDrop={dz.onDrop}
      onDragOver={dz.onDrag}
      onDragLeave={dz.onLeave}
      onClick={dz.onClick}
    >
      <input ref={dz.ref} type="file" accept=".xlsx" style={{display:"none"}} onChange={dz.onChange} />
      <div className="dropzone-icon">{file ? "✓" : "↑"}</div>
      <div className="dropzone-label">{label}</div>
      <div className="dropzone-sub">{sub}</div>
      {file && <div className="dropzone-file">{file.name}</div>}
    </div>
  )
}

function StatBox({ num, label, sub, accent }) {
  return (
    <div className="stat-box">
      <div className="stat-num" style={accent ? {color: accent} : {}}>{fmt(num)}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function DataTable({ headers, rows, totalRows }) {
  if (!headers?.length) return <p style={{color:"var(--text3)",fontSize:13}}>Không có dữ liệu.</p>
  return (
    <>
      <div className="row-count">
        Hiển thị {rows.length} / {totalRows} dòng
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{headers.map((h,i) => <th key={i} title={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row,ri) => (
              <tr key={ri}>
                {row.map((cell,ci) => <td key={ci} title={cell}>{cell || "—"}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

const CTKM_OPERATIONAL_SHEETS = [
  ["TỔNG HỢP - TEM","Tất cả"],
  ["Gắn tem","Gắn"],
  ["Tháo tem","Tháo"],
  ["Chờ gắn","Chờ"],
  ["Cần review","Cần review"],
]

function CtkmPreviewWorkspace({ preview, activeSheet, setActiveSheet }) {
  const [query,setQuery]=useState("")
  const sheets=preview?.sheets||{}
  const operational=CTKM_OPERATIONAL_SHEETS.filter(([name])=>sheets[name])
  const technical=Object.keys(sheets).filter(name=>!CTKM_OPERATIONAL_SHEETS.some(([operationalName])=>operationalName===name))
  const selected=sheets[activeSheet]||sheets[operational[0]?.[0]]||null
  const normalized=query.trim().toLocaleLowerCase("vi")
  const filteredRows=selected?.rows?.filter(row=>!normalized||row.some(value=>String(value??"").toLocaleLowerCase("vi").includes(normalized)))||[]
  const selectedName=activeSheet&&sheets[activeSheet]?activeSheet:operational[0]?.[0]

  return <section className="ctkm-workspace">
    <div className="ctkm-workspace-head">
      <div><div className="ctkm-workspace-kicker">Danh sách vận hành</div><h2>CTKM tại cửa hàng</h2><p>Ưu tiên Gắn / Tháo / Chờ / Review. Dữ liệu audit vẫn được giữ trong workbook và nhóm “Dữ liệu khác”.</p></div>
      <a className="ctkm-shelf-cta" href="/scan-tem?mode=shelf">✓ Kiểm theo kệ</a>
    </div>
    <div className="ctkm-operation-tabs">
      {operational.map(([name,label])=><button key={name} className={selectedName===name?"active":""} onClick={()=>{setActiveSheet(name);setQuery("")}}><span>{label}</span><b>{sheets[name].total_rows.toLocaleString("vi-VN")}</b></button>)}
    </div>
    <div className="ctkm-list-tools">
      <label className="ctkm-search"><span>⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Tìm mã SP, tên sản phẩm, kệ, channel…"/></label>
      {technical.length>0&&<select value={technical.includes(selectedName)?selectedName:""} onChange={e=>{if(e.target.value){setActiveSheet(e.target.value);setQuery("")}}}><option value="">Dữ liệu khác / audit</option>{technical.map(name=><option key={name} value={name}>{name} · {sheets[name].total_rows.toLocaleString("vi-VN")}</option>)}</select>}
    </div>
    {selected&&<DataTable headers={selected.headers} rows={filteredRows} totalRows={selected.total_rows}/>}
    {query&&selected&&<div className="ctkm-filter-note">Đang lọc {filteredRows.length} / {selected.rows.length} dòng preview. Tìm kiếm chỉ thay đổi hiển thị, không thay đổi workbook.</div>}
  </section>
}

// ─── Main App ─────────────────────────────────────────────────────────────────
const STEPS = { idle: "idle", running: "running", done: "done", error: "error" }
const STEP_LABELS = [
  "Đọc và chuẩn hoá file…",
  "Phân loại sheet CTKM…",
  "Gemini nhận diện cột…",
  "Lọc theo tháng…",
  "Ghép CTKM ↔ POG…",
  "Soát lệch & xuất file…",
]
const FACT_FIELDS = [
  "item_id",
  "item_name",
  "campaign_name",
  "campaign_detail",
  "promo_from",
  "promo_to",
  "channel",
  "normal_price",
  "promo_price",
  "product_type",
]
const POG_FIELDS = [
  "item_id",
  "item_name",
  "store_id",
  "pog_code",
  "location_id",
  "facing",
]
const OUTPUT_FIELDS = [
  "item_id",
  "item_name",
  "campaign_name",
  "campaign_detail",
  "promo_from",
  "promo_to",
  "channel",
  "normal_price",
  "promo_price",
  "product_type",
  "store_id",
  "pog_code",
  "location_id",
  "facing",
]
const OUTPUT_PRESET_KEY = "ctkm.output.columns.v1"
const MAPPING_PRESET_PREFIX = "ctkm.mapping.preset.v1"
const TEM_R_RESULT_KEY = "ctkm.temr.last-result.v1"
const TEM_R_REQUIRED_COLUMNS = ["STOREID", "POGCODE", "FIXELID", "LOCATIONID", "ITEMID", "ITEMNAME"]
const TEM_R_FIELD_LABELS = {
  STOREID:"Mã cửa hàng", POGCODE:"Mã POG", FIXELID:"Mã kệ",
  LOCATIONID:"Vị trí trên kệ", ITEMID:"Mã sản phẩm", ITEMNAME:"Tên sản phẩm",
}

export default function App() {
  const initialModule = () => { const requested = new URLSearchParams(window.location.search).get("module"); return ["ctkm","expiration","temr","inventory"].includes(requested) ? requested : "ctkm" }
  const [activeModule, setActiveModule] = useState(initialModule)
  const [adminToken, setAdminToken] = useState(() => sessionStorage.getItem("ctkm.admin.token") || "")
  const [adminUsername, setAdminUsername] = useState("admin")
  const [adminPassword, setAdminPassword] = useState("")
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState("")
  const [ctkmAdvanced, setCtkmAdvanced] = useState(false)
  const [ctkmFile, setCtkmFile]   = useState(null)
  const [clearanceFile, setClearanceFile] = useState(null)
  const [pogFile, setPogFile]     = useState(null)
  const [month, setMonth]         = useState(() => {
    const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`
  })
  const [strict, setStrict]       = useState(false)
  const [ctkmSheetOptions, setCtkmSheetOptions] = useState([])
  const [ctkmSheetName, setCtkmSheetName] = useState("")
  const [ctkmSheetLoading, setCtkmSheetLoading] = useState(false)
  const [ctkmSheetError, setCtkmSheetError] = useState("")
  const [pogSnapshotMonth, setPogSnapshotMonth] = useState("")
  const [pogSheetOptions, setPogSheetOptions] = useState([])
  const [pogSheetName, setPogSheetName] = useState("")
  const [pogSheetLoading, setPogSheetLoading] = useState(false)
  const [pogInspectError, setPogInspectError] = useState("")
  const [mappingPreview, setMappingPreview] = useState(null)
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingError, setMappingError] = useState("")
  const [mappingSaving, setMappingSaving] = useState(false)
  const [mappingSaved, setMappingSaved] = useState("")
  const [savedOnly, setSavedOnly] = useState(false)
  const [ctkmMappingOverride, setCtkmMappingOverride] = useState({})
  const [pogMappingOverride, setPogMappingOverride] = useState({})
  const [selectedOutputColumns, setSelectedOutputColumns] = useState([])
  const [savedPresets, setSavedPresets] = useState([])
  const [presetLoading, setPresetLoading] = useState(false)
  const [presetError, setPresetError] = useState("")
  const [temRFile, setTemRFile] = useState(null)
  const [temRLoading, setTemRLoading] = useState(false)
  const [temRResult, setTemRResult] = useState(() => readJsonStorage(TEM_R_RESULT_KEY, null))
  const [temRError, setTemRError] = useState("")
  const [temRColumns, setTemRColumns] = useState([])
  const [temRSheetOptions, setTemRSheetOptions] = useState([])
  const [temRSheetName, setTemRSheetName] = useState("")
  const [temRItemColumn, setTemRItemColumn] = useState("")
  const [temRStockColumn, setTemRStockColumn] = useState("")
  const [temRMaxDistance, setTemRMaxDistance] = useState(1)
  const [temRColumnMapping, setTemRColumnMapping] = useState({})
  const [temRInspecting, setTemRInspecting] = useState(false)
  const [temRInspectInfo, setTemRInspectInfo] = useState(null)
  const [inventoryLoading, setInventoryLoading] = useState(false)
  const [inventoryResult, setInventoryResult] = useState(null)
  const [inventoryError, setInventoryError] = useState("")
  const [inventoryQuery, setInventoryQuery] = useState("")
  const [inventoryFilter, setInventoryFilter] = useState("all")
  const [expirationFile, setExpirationFile] = useState(null)
  const [expirationEntries, setExpirationEntries] = useState("")
  const [expirationLoading, setExpirationLoading] = useState(false)
  const [expirationResult, setExpirationResult] = useState(null)
  const [expirationError, setExpirationError] = useState("")
  const [expirationFilter, setExpirationFilter] = useState("all")
  const [expirationSort, setExpirationSort] = useState("expiry_desc")
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraMessage, setCameraMessage] = useState("")
  const [cameraError, setCameraError] = useState("")
  const cameraVideoRef = useRef(null)
  const cameraStreamRef = useRef(null)
  const cameraFrameRef = useRef(null)
  const cameraBusyRef = useRef(false)
  const cameraLastScanRef = useRef({ value: "", at: 0 })
  const healthFailureRef = useRef(0)
  const busyRef = useRef(false)
  const [step, setStep]           = useState(STEPS.idle)
  const [stepIdx, setStepIdx]     = useState(0)
  const [jobId, setJobId]         = useState(null)
  const [result, setResult]       = useState(null)   // {summary, warnings}
  const [preview, setPreview]     = useState(null)   // {sheets:{...}}
  const [activeSheet, setActiveSheet] = useState(null)
  const [error, setError]         = useState(null)
  const [backendStatus, setBackendStatus] = useState("checking") // checking | ok | offline
  const [queueStatus, setQueueStatus] = useState(null)
  const [mappingConfirmation, setMappingConfirmation] = useState(null)
  const [confirmCtkmMapping, setConfirmCtkmMapping] = useState({})
  const [confirmPogMapping, setConfirmPogMapping] = useState({})
  const [confirmClearanceMapping, setConfirmClearanceMapping] = useState({})
  const [mappingConfirmSaving, setMappingConfirmSaving] = useState(false)

  useEffect(() => {
    busyRef.current = temRLoading || inventoryLoading || expirationLoading || step === STEPS.running
  }, [temRLoading, inventoryLoading, expirationLoading, step])

  const isAdmin = !!adminToken
  const authFetch = useCallback((url, options = {}) => {
    const headers = new Headers(options.headers || {})
    if (adminToken) headers.set("Authorization", `Bearer ${adminToken}`)
    return fetch(url, {...options, headers})
  }, [adminToken])

  const logoutAdmin = useCallback(() => {
    sessionStorage.removeItem("ctkm.admin.token")
    setAdminToken("")
    setAdminPassword("")
    setAuthError("")
    setActiveModule("expiration")
  }, [])

  const loginAdmin = async (event) => {
    event.preventDefault()
    setAuthLoading(true); setAuthError("")
    try {
      const body = new FormData()
      body.append("username", adminUsername)
      body.append("password", adminPassword)
      const res = await fetch(`${API}/api/auth/login`, {method:"POST", body})
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không đăng nhập được")
      sessionStorage.setItem("ctkm.admin.token", data.access_token)
      setAdminToken(data.access_token)
      setAdminPassword("")
    } catch (e) {
      setAuthError(e.message)
    } finally {
      setAuthLoading(false)
    }
  }

  useEffect(() => {
    if (!adminToken) return
    authFetch(`${API}/api/auth/me`).then(res => {
      if (res.status === 401) logoutAdmin()
    }).catch(() => {})
  }, [adminToken, authFetch, logoutAdmin])

  const waitingJobs = queueStatus?.waiting?.length || 0
  const ownQueuePosition = queueStatus?.waiting?.[0]?.position || 0
  const queueHasWaiting = waitingJobs > 0

  useEffect(() => {
    const stored = readJsonStorage(OUTPUT_PRESET_KEY, [])
    if (Array.isArray(stored)) {
      setSelectedOutputColumns(stored.filter(x => typeof x === "string" && x.trim()))
    }
  }, [])

  const refreshPresets = useCallback(async () => {
    if (!adminToken) return
    setPresetLoading(true)
    setPresetError("")
    try {
      const res = await authFetch(`${API}/api/presets`)
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không tải được preset")
      setSavedPresets(data.items || [])
    } catch (e) {
      setPresetError(e.message)
    } finally {
      setPresetLoading(false)
    }
  }, [adminToken, authFetch])

  useEffect(() => {
    if (isAdmin) refreshPresets()
  }, [isAdmin, refreshPresets])

  const canRun = ctkmFile && pogFile && month && step !== STEPS.running
    && backendStatus === "ok"
    && (!ctkmSheetOptions.length || !!ctkmSheetName)
    && (!pogSheetOptions.length || !!pogSheetName)
  const temRSelectedSources = [
    ...TEM_R_REQUIRED_COLUMNS.map(field => temRColumnMapping[field]).filter(Boolean),
    temRStockColumn,
  ].filter(Boolean)
  const temRMappingComplete = TEM_R_REQUIRED_COLUMNS.every(field => temRColumnMapping[field])
    && !!temRStockColumn
    && Number.isFinite(temRMaxDistance) && temRMaxDistance > 0
    && new Set(temRSelectedSources).size === temRSelectedSources.length

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const res = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(8000) })
        if (cancelled) return
        if (res.ok) {
          healthFailureRef.current = 0
          setBackendStatus("ok")
        } else if (!busyRef.current && ++healthFailureRef.current >= 3) {
          setBackendStatus("offline")
        }
      } catch {
        if (!cancelled) {
          if (busyRef.current) healthFailureRef.current = 0
          else if (++healthFailureRef.current >= 3) setBackendStatus("offline")
        }
      }
    }
    check()
    const iv = setInterval(check, 30000)
    return () => { cancelled = true; clearInterval(iv) }
  }, [])

  useEffect(() => {
    let cancelled = false
    const inspect = async () => {
      if (!ctkmFile) {
        setCtkmSheetOptions([])
        setCtkmSheetName("")
        setCtkmSheetError("")
        setCtkmSheetLoading(false)
        return
      }
      setCtkmSheetLoading(true)
      setCtkmSheetError("")
      try {
        const fd = new FormData()
        fd.append("ctkm_file", ctkmFile)
        const res = await authFetch(`${API}/api/inspect-ctkm`, { method: "POST", body: fd })
        const data = await res.json()
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không đọc được sheet CTKM")
        if (!cancelled) {
          const sheets = data.sheet_names || []
          setCtkmSheetOptions(sheets)
          setCtkmSheetName(data.suggested_sheet || sheets[0] || "")
        }
      } catch (e) {
        if (!cancelled) {
          setCtkmSheetOptions([])
          setCtkmSheetName("")
          setCtkmSheetError(e.message)
        }
      } finally {
        if (!cancelled) setCtkmSheetLoading(false)
      }
    }
    inspect()
    return () => { cancelled = true }
  }, [ctkmFile, authFetch])

  useEffect(() => {
    let cancelled = false
    const inspect = async () => {
      if (!pogFile) {
        setPogSnapshotMonth("")
        setPogSheetOptions([])
        setPogSheetName("")
        setPogInspectError("")
        setPogSheetLoading(false)
        return
      }
      setPogSheetLoading(true)
      setPogInspectError("")
      try {
        const fd = new FormData()
        fd.append("pog_file", pogFile)
        if (pogSheetName) fd.append("pog_sheet_name", pogSheetName)
        const res = await authFetch(`${API}/api/inspect-pog`, { method: "POST", body: fd })
        const data = await res.json()
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không đọc được snapshot POG")
        if (!cancelled) {
          const sheets = data.sheet_names || []
          setPogSheetOptions(sheets)
          setPogSheetName(data.suggested_sheet || sheets[0] || "")
          setPogSnapshotMonth(data.snapshot_month || "")
        }
      } catch (e) {
        if (!cancelled) {
          setPogSnapshotMonth("")
          setPogSheetOptions([])
          setPogSheetName("")
          setPogInspectError(e.message)
        }
      } finally {
        if (!cancelled) setPogSheetLoading(false)
      }
    }
    inspect()
    return () => { cancelled = true }
  }, [pogFile, pogSheetName, authFetch])

  useEffect(() => {
    let cancelled = false
    const inspect = async () => {
      if (!temRFile) {
        setTemRColumns([])
        setTemRStockColumn("")
        setTemRItemColumn("")
        setTemRSheetOptions([])
        setTemRSheetName("")
        setTemRColumnMapping({})
        setTemRInspectInfo(null)
        setInventoryResult(null)
        setInventoryError("")
        return
      }
      setTemRInspecting(true)
      setTemRError("")
      try {
        const fd = new FormData()
        fd.append("tem_r_file", temRFile)
        const res = await authFetch(`${API}/api/inspect-tem-r`, { method: "POST", body: fd })
        const data = await res.json()
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không đọc được cột trong file")
        if (!cancelled) {
          setTemRColumns(data.columns || [])
          setTemRSheetOptions(data.sheet_options || [])
          setTemRSheetName(data.sheet_name || "")
          setTemRItemColumn(data.suggested_item_column || "")
          setTemRStockColumn(data.suggested_stock_column || "")
          setTemRColumnMapping(data.suggested_mapping || {})
          setTemRInspectInfo({sheetName:data.sheet_name, headerRow:data.header_row})
        }
      } catch (e) {
        if (!cancelled) setTemRError(e.message)
      } finally {
        if (!cancelled) setTemRInspecting(false)
      }
    }
    inspect()
    return () => { cancelled = true }
  }, [temRFile, authFetch])

  useEffect(() => {
    setMappingPreview(null)
    setMappingError("")
    setCtkmMappingOverride({})
    setPogMappingOverride({})
  }, [ctkmFile, ctkmSheetName, pogFile])

  useEffect(() => {
    writeJsonStorage(OUTPUT_PRESET_KEY, selectedOutputColumns)
  }, [selectedOutputColumns])

  useEffect(() => {
    if (temRResult?.job_id) writeJsonStorage(TEM_R_RESULT_KEY, temRResult)
  }, [temRResult])

  useEffect(() => {
    if (!mappingPreview) return
    const ctkmSig = buildColumnSignature(mappingPreview.ctkm_preview?.columns || [])
    const pogSig = buildColumnSignature(mappingPreview.pog_preview?.columns || [])
    if (!ctkmSig && !pogSig) return
    const key = `${MAPPING_PRESET_PREFIX}:${ctkmSig}::${pogSig}`
    const payload = {
      ctkm: ctkmMappingOverride,
      pog: pogMappingOverride,
      output: selectedOutputColumns,
      savedAt: new Date().toISOString(),
    }
    writeJsonStorage(key, payload)
  }, [mappingPreview, ctkmMappingOverride, pogMappingOverride, selectedOutputColumns])

  const deletePreset = async (key) => {
    try {
      const res = await authFetch(`${API}/api/presets?key=${encodeURIComponent(key)}`, { method: "DELETE" })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không xoá được preset")
      await refreshPresets()
    } catch (e) {
      setPresetError(e.message)
    }
  }

  // Simulate progress steps during API call
  const simulateProgress = useCallback(() => {
    setStepIdx(0)
    let i = 0
    const iv = setInterval(() => {
      i++; setStepIdx(i)
      if (i >= STEP_LABELS.length - 1) clearInterval(iv)
    }, 1800)
    return iv
  }, [])

  const waitForJob = async (jobId, onUpdate) => {
    while (true) {
      const res = await authFetch(`${API}/api/job/${jobId}/status`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "Không đọc được trạng thái tác vụ")
      onUpdate?.(data)
      if (data.status === "completed" || data.status === "awaiting_mapping_confirmation") return data
      if (data.status === "failed") throw new Error(data.error || "Tác vụ xử lý thất bại")
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
  }

  const handleRun = async () => {
    setStep(STEPS.running); setError(null); setResult(null)
    setPreview(null); setJobId(null); setActiveSheet(null)
    const iv = simulateProgress()
    const fd = new FormData()
    fd.append("ctkm_file", ctkmFile)
    fd.append("pog_file",  pogFile)
    if (clearanceFile) fd.append("clearance_file", clearanceFile)
    fd.append("month",     month)
    fd.append("strict_month", strict)
    fd.append("mapping_mode", savedOnly ? "saved_only" : "auto")
    if (ctkmSheetName) fd.append("ctkm_sheet_name", ctkmSheetName)
    if (pogSheetName) fd.append("pog_sheet_name", pogSheetName)
    if (Object.keys(ctkmMappingOverride).length > 0) {
      fd.append("ctkm_mapping_override", JSON.stringify(ctkmMappingOverride))
    }
    if (Object.keys(pogMappingOverride).length > 0) {
      fd.append("pog_mapping_override", JSON.stringify(pogMappingOverride))
    }
    if (selectedOutputColumns.length > 0) {
      fd.append("selected_output_columns", JSON.stringify(selectedOutputColumns))
    }
    try {
      const res = await authFetch(`${API}/api/jobs/ctkm`, { method: "POST", body: fd })
      if (!res.ok) {
        const err = await res.json()
        if (res.status === 429) {
          // Rate limit — thông báo thân thiện hơn
          const detail = err.detail || {}
          const msg = typeof detail === "object"
            ? (detail.suggestion || detail.message || "Gemini free tier bị quá tải.")
            : detail
          throw new Error("⏳ " + msg)
        }
        const detail = err.detail || "Lỗi không xác định từ server."
        throw new Error(typeof detail === "object" ? JSON.stringify(detail) : detail)
      }
      const accepted = await res.json()
      setJobId(accepted.job_id)
      const data = await waitForJob(accepted.job_id, status => {
        setQueueStatus(prev => ({...(prev || {}), waiting: status.queue_position
          ? [{job_id:status.job_id, position:status.queue_position}] : []}))
      })
      if (data.status === "awaiting_mapping_confirmation") {
        clearInterval(iv)
        const confirmation = data.mapping_confirmation || {}
        setMappingConfirmation({jobId:data.job_id, ...confirmation})
        setConfirmCtkmMapping(confirmation.ctkm?.mapping || {})
        setConfirmPogMapping(confirmation.pog?.mapping || {})
        setConfirmClearanceMapping(confirmation.clearance?.mapping || {})
        return
      }
      clearInterval(iv); setStepIdx(STEP_LABELS.length)
      setResult({ summary: data.summary, warnings: data.warnings })
      setStep(STEPS.done)
      refreshPresets()
      // Load preview
      const pres = await authFetch(`${API}/api/preview/${data.job_id}?rows=100`)
      if (pres.ok) {
        const pdata = await pres.json()
        setPreview(pdata)
        setActiveSheet(Object.keys(pdata.sheets)[0])
      }
    } catch (e) {
      clearInterval(iv)
      setError(e.message); setStep(STEPS.error)
    }
  }

  const confirmAndResumeMapping = async () => {
    if (!mappingConfirmation?.jobId) return
    setMappingConfirmSaving(true); setError(null)
    try {
      const fd = new FormData()
      fd.append("ctkm_mapping", JSON.stringify(confirmCtkmMapping))
      fd.append("pog_mapping", JSON.stringify(confirmPogMapping))
      if (mappingConfirmation.clearance) {
        fd.append("clearance_mapping", JSON.stringify(confirmClearanceMapping))
      }
      fd.append("save_preset", "true")
      const res = await authFetch(`${API}/api/job/${mappingConfirmation.jobId}/mapping-confirmation`, {method:"POST", body:fd})
      const accepted = await res.json()
      if (!res.ok) throw new Error(accepted.detail || "Không xác nhận được mapping")
      setMappingConfirmation(null); setStep(STEPS.running)
      const data = await waitForJob(accepted.job_id)
      if (data.status === "awaiting_mapping_confirmation") {
        const confirmation = data.mapping_confirmation || {}
        setMappingConfirmation({jobId:data.job_id, ...confirmation})
        setConfirmCtkmMapping(confirmation.ctkm?.mapping || {})
        setConfirmPogMapping(confirmation.pog?.mapping || {})
        setConfirmClearanceMapping(confirmation.clearance?.mapping || {})
        return
      }
      setResult({summary:data.summary, warnings:data.warnings}); setStep(STEPS.done); refreshPresets()
      const pres = await authFetch(`${API}/api/preview/${data.job_id}?rows=100`)
      if (pres.ok) { const pdata = await pres.json(); setPreview(pdata); setActiveSheet(Object.keys(pdata.sheets)[0]) }
    } catch (e) { setError(e.message); setStep(STEPS.error) }
    finally { setMappingConfirmSaving(false) }
  }

  const downloadAdminFile = async (downloadJobId, onError = setError) => {
    try {
      const res = await authFetch(`${API}/api/download/${downloadJobId}`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || "Không tải được file")
      }
      const blob = await res.blob()
      const disposition = res.headers.get("content-disposition") || ""
      const matchedName = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
      const filename = matchedName ? decodeURIComponent(matchedName[1]) : `ket_qua_${downloadJobId}.xlsx`
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url; anchor.download = filename; anchor.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      onError(e.message)
    }
  }

  const handleDownload = () => {
    if (jobId) downloadAdminFile(jobId)
  }

  const handleTemR = async () => {
    if (!temRFile || !temRMappingComplete || backendStatus !== "ok") return
    setTemRLoading(true)
    setTemRError("")
    try {
      const fd = new FormData()
      fd.append("tem_r_file", temRFile)
      fd.append("max_location_distance", String(temRMaxDistance))
      fd.append("stock_column", temRStockColumn)
      fd.append("column_mapping", JSON.stringify(temRColumnMapping))
      fd.append("sheet_name", temRSheetName)
      if (temRInspectInfo?.headerRow) fd.append("header_row", String(temRInspectInfo.headerRow))
      const res = await authFetch(`${API}/api/jobs/tem-r`, { method: "POST", body: fd })
      const accepted = await res.json()
      if (!res.ok) throw new Error(typeof accepted.detail === "string" ? accepted.detail : "Không thể đưa Tem R vào hàng đợi")
      const data = await waitForJob(accepted.job_id, status => {
        setQueueStatus(prev => ({...(prev || {}), waiting: status.queue_position
          ? [{job_id:status.job_id, position:status.queue_position}] : []}))
      })
      setTemRResult(data)
      writeJsonStorage(TEM_R_RESULT_KEY, data)
    } catch (e) {
      setTemRError(e.message)
    } finally {
      setTemRLoading(false)
    }
  }

  const downloadTemR = () => {
    if (temRResult?.job_id) downloadAdminFile(temRResult.job_id, setTemRError)
  }

  const handleInventoryInspect = async () => {
    if (!temRFile || !temRMappingComplete || backendStatus !== "ok") return
    setInventoryLoading(true)
    setInventoryError("")
    setInventoryResult(null)
    try {
      const fd = new FormData()
      fd.append("tem_r_file", temRFile)
      fd.append("stock_column", temRStockColumn)
      fd.append("column_mapping", JSON.stringify(temRColumnMapping))
      if (temRSheetName) fd.append("sheet_name", temRSheetName)
      if (temRInspectInfo?.headerRow) fd.append("header_row", String(temRInspectInfo.headerRow))
      const res = await fetch(`${API}/api/inspect-inventory`, {method:"POST", body:fd})
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không kiểm tra được tồn kho")
      setInventoryResult(data)
      setInventoryQuery("")
      setInventoryFilter("all")
    } catch (e) {
      setInventoryError(e.message)
    } finally {
      setInventoryLoading(false)
    }
  }

  const handleExpirationCheck = async () => {
    if (!expirationFile || !expirationEntries.trim() || backendStatus !== "ok") return
    setExpirationLoading(true)
    setExpirationError("")
    setExpirationResult(null)
    try {
      const fd = new FormData()
      fd.append("expiration_file", expirationFile)
      fd.append("entries", expirationEntries)
      const res = await fetch(`${API}/api/check-expiration`, { method: "POST", body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Không thể kiểm tra dữ liệu")
      setExpirationResult(data)
    } catch (e) {
      setExpirationError(e.message)
    } finally {
      setExpirationLoading(false)
    }
  }

  const appendScannedEntry = useCallback((rawValue) => {
    const value = String(rawValue || "").trim()
    const parts = value.split(";").map(part => part.trim())
    if (parts.length !== 3 || !/^P\w+$/i.test(parts[0]) || !/^\d{2}\/\d{2}\/\d{4}$/.test(parts[2])) {
      setCameraMessage(`Đã đọc “${value}” nhưng không đúng mẫu MÃ_P;SỐ_LÔ;DD/MM/YYYY`)
      return false
    }
    const normalized = `${parts[0].toUpperCase()};${parts[1]};${parts[2]}`
    let added = false
    setExpirationEntries(previous => {
      const existing = previous.split(/\r?\n/).map(line => line.trim().toUpperCase())
      if (existing.includes(normalized.toUpperCase())) return previous
      added = true
      return previous.trim() ? `${previous.trim()}\n${normalized}` : normalized
    })
    setExpirationResult(null)
    setCameraMessage(added ? `Đã thêm: ${normalized}` : `Đã có trong danh sách: ${normalized}`)
    if (added && navigator.vibrate) navigator.vibrate(100)
    return added
  }, [])

  const stopCamera = useCallback(() => {
    if (cameraFrameRef.current) cancelAnimationFrame(cameraFrameRef.current)
    cameraFrameRef.current = null
    cameraStreamRef.current?.getTracks().forEach(track => track.stop())
    cameraStreamRef.current = null
    cameraBusyRef.current = false
    if (cameraVideoRef.current) cameraVideoRef.current.srcObject = null
    setCameraActive(false)
  }, [])

  const startCamera = async () => {
    setCameraError("")
    setCameraMessage("")
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Trình duyệt không hỗ trợ truy cập camera.")
      return
    }
    if (!("BarcodeDetector" in window)) {
      setCameraError("Trình duyệt này chưa hỗ trợ quét QR/barcode. Hãy dùng Chrome hoặc Edge phiên bản mới.")
      return
    }
    try {
      const formats = await window.BarcodeDetector.getSupportedFormats()
      const preferred = ["qr_code", "data_matrix", "code_128", "code_39"]
      const enabled = preferred.filter(format => formats.includes(format))
      const detector = new window.BarcodeDetector(enabled.length ? { formats: enabled } : undefined)
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      cameraStreamRef.current = stream
      setCameraActive(true)
      requestAnimationFrame(async () => {
        const video = cameraVideoRef.current
        if (!video) return stopCamera()
        video.srcObject = stream
        await video.play()
        const scan = async () => {
          if (!cameraStreamRef.current) return
          if (!cameraBusyRef.current && video.readyState >= 2) {
            cameraBusyRef.current = true
            try {
              const codes = await detector.detect(video)
              const now = Date.now()
              for (const code of codes) {
                const value = code.rawValue?.trim()
                const last = cameraLastScanRef.current
                if (value && (value !== last.value || now - last.at > 2500)) {
                  cameraLastScanRef.current = { value, at: now }
                  appendScannedEntry(value)
                  break
                }
              }
            } catch {
              // A frame may fail while the camera is focusing; continue scanning.
            } finally {
              cameraBusyRef.current = false
            }
          }
          cameraFrameRef.current = requestAnimationFrame(scan)
        }
        scan()
      })
    } catch (e) {
      stopCamera()
      const denied = e?.name === "NotAllowedError"
      setCameraError(denied ? "Bạn chưa cấp quyền sử dụng camera." : `Không mở được camera: ${e.message}`)
    }
  }

  useEffect(() => () => stopCamera(), [stopCamera])

  const handlePreviewMapping = async (manualOnly = false) => {
    if (!ctkmFile || !pogFile || !ctkmSheetName || !pogSheetName || backendStatus !== "ok") return
    setMappingLoading(true)
    setMappingError("")
    setMappingSaved("")
    try {
      const fd = new FormData()
      fd.append("ctkm_file", ctkmFile)
      fd.append("pog_file", pogFile)
      fd.append("ctkm_sheet_name", ctkmSheetName)
      fd.append("pog_sheet_name", pogSheetName)
      fd.append("manual_only", String(manualOnly))
      const res = await authFetch(`${API}/api/preview-mapping`, { method: "POST", body: fd })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Không lấy được mapping preview")
      }
      setMappingPreview(data)
      if ((data.mapping_warnings || []).length > 0) {
        setMappingError(
          "Gemini không khả dụng. Bạn vẫn có thể chọn mapping thủ công bên dưới. " +
          data.mapping_warnings.join(" · ")
        )
      }
      const sharedPreset = data?.stored_preset || null
      const ctkmCols = data?.ctkm_preview?.columns || []
      const pogCols = data?.pog_preview?.columns || []
      const presetKey = `${MAPPING_PRESET_PREFIX}:${buildColumnSignature(ctkmCols)}::${buildColumnSignature(pogCols)}`
      const storedPreset = sharedPreset || readJsonStorage(presetKey, null)
      const storedCtkm = storedPreset?.ctkm_mapping || storedPreset?.ctkm
      const storedPog = storedPreset?.pog_mapping || storedPreset?.pog
      const storedOutput = storedPreset?.output_columns || storedPreset?.output

      const nextCtkm = {}
      Object.entries(data?.ctkm_mapping?.mapping || {}).forEach(([src, dst]) => {
        nextCtkm[src] = dst
      })
      const nextPog = {}
      Object.entries(data?.pog_mapping?.mapping || {}).forEach(([src, dst]) => {
        nextPog[src] = dst
      })

      if (storedCtkm) {
        setCtkmMappingOverride({ ...nextCtkm, ...storedCtkm })
      } else {
        setCtkmMappingOverride(nextCtkm)
      }

      if (storedPog) {
        setPogMappingOverride({ ...nextPog, ...storedPog })
      } else {
        setPogMappingOverride(nextPog)
      }

      if (Array.isArray(storedOutput)) {
        setSelectedOutputColumns(storedOutput.filter(x => typeof x === "string" && x.trim()))
      }

      if (!sharedPreset && storedPreset) {
        writeJsonStorage(presetKey, storedPreset)
      }
    } catch (e) {
      setMappingPreview(null)
      setMappingError(e.message)
    } finally {
      setMappingLoading(false)
    }
  }

  const updateCtkmMapping = (sourceColumn, canonicalField) => {
    setCtkmMappingOverride(prev => {
      const next = { ...prev }
      if (canonicalField) next[sourceColumn] = canonicalField
      else delete next[sourceColumn]
      return next
    })
  }

  const updatePogMapping = (sourceColumn, canonicalField) => {
    setPogMappingOverride(prev => {
      const next = { ...prev }
      if (canonicalField) next[sourceColumn] = canonicalField
      else delete next[sourceColumn]
      return next
    })
  }

  const saveApprovedMapping = async () => {
    if (!isAdmin || !mappingPreview) return
    setMappingSaving(true)
    setMappingError("")
    setMappingSaved("")
    try {
      const fd = new FormData()
      fd.append("ctkm_columns", JSON.stringify(mappingPreview.ctkm_preview?.columns || []))
      fd.append("pog_columns", JSON.stringify(mappingPreview.pog_preview?.columns || []))
      fd.append("ctkm_mapping", JSON.stringify(ctkmMappingOverride))
      fd.append("pog_mapping", JSON.stringify(pogMappingOverride))
      fd.append("selected_output_columns", JSON.stringify(selectedOutputColumns))
      const res = await authFetch(`${API}/api/presets`, { method: "POST", body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Khong luu duoc mapping")
      setMappingSaved("Đã lưu mapping. Lần sau có thể bật chế độ chỉ dùng mapping đã lưu.")
      refreshPresets()
    } catch (e) {
      setMappingError(e.message)
    } finally {
      setMappingSaving(false)
    }
  }

  const toggleOutputColumn = (field) => {
    setSelectedOutputColumns(prev => (
      prev.includes(field) ? prev.filter(x => x !== field) : [...prev, field]
    ))
  }

  // ── Summary stats from result.summary dict ─────────────────────────────────
  const S = result?.summary ?? {}
  const matched   = S["So dong khop (Matched)"]         ?? "—"
  const itemMatch = S["So item duy nhat khop"]           ?? "—"
  const ctkmMiss  = S["So dong CTKM thieu vi tri ke"]    ?? "—"
  const locationReview = S["So dong can kiem tra vi tri"] ?? "—"
  const pogMiss   = S["So dong POG khong co CTKM phu hop"] ?? S["So dong len ke thieu CTKM"] ?? "—"
  const overlapW  = S["So canh bao trung thoi gian"]     ?? "—"
  const hoaDon    = S["  Trong do CTKM theo hoa don"]    ?? 0

  const warnings  = result?.warnings ?? []


  const mappingConfirmationModal = mappingConfirmation ? (
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.68)",zIndex:9999,display:"flex",alignItems:"center",justifyContent:"center",padding:20}}>
      <div className="card" style={{width:"min(960px,96vw)",maxHeight:"90vh",overflow:"auto"}}>
        <div className="ops-assistant"><Mascot state="warning"/><div className="ops-assistant-copy"><div className="ops-assistant-title">Cần bạn xác nhận mapping <HelpTip title="Mapping theo dữ liệu" text={MODULE_HELP.ops.mapping}/></div><GuideBubble>Hệ thống chỉ đang đề xuất tên trường từ header và giá trị mẫu. Hãy kiểm tra cột nguồn trước khi xác nhận; giá trị nguồn không bị sửa.</GuideBubble></div></div>
        <div className="card-title">Cần xác nhận mapping để tiếp tục</div>
        <div className="sheet-hint" style={{marginBottom:16}}>{mappingConfirmation.reason}</div>
        {[
          ["CTKM",mappingConfirmation.ctkm,confirmCtkmMapping,setConfirmCtkmMapping,FACT_FIELDS],
          ["POG",mappingConfirmation.pog,confirmPogMapping,setConfirmPogMapping,POG_FIELDS],
          mappingConfirmation.clearance
            ? ["Clearance",mappingConfirmation.clearance,confirmClearanceMapping,setConfirmClearanceMapping,FACT_FIELDS]
            : null,
        ].filter(Boolean).map(([label,info,values,setter,fields]) => (
          <div key={label} style={{marginBottom:18}}><div className="card-title">{label}</div>
            <div className="table-wrap mapping-table"><table><thead><tr><th>Cột nguồn</th><th>Gợi ý</th><th>Tin cậy</th><th>Xác nhận</th></tr></thead><tbody>
              {[...new Set([...Object.keys(info?.mapping||{}),...(info?.unmapped||[])])].map(src => <tr key={src}>
                <td>{src}</td><td>{info?.mapping?.[src]||"(chưa map)"}</td><td>{info?.confidence?.[src]??"—"}</td><td>
                  <select className="sheet-select" value={values[src]||""} onChange={e=>setter(prev=>({...prev,[src]:e.target.value}))}>
                    <option value="">(không sử dụng)</option>{fields.map(field=><option key={field} value={field}>{field}</option>)}
                  </select></td></tr>)}
            </tbody></table></div>
          </div>
        ))}
        <button className="btn btn-primary" onClick={confirmAndResumeMapping} disabled={mappingConfirmSaving}>
          {mappingConfirmSaving?"Đang xác nhận…":"Xác nhận và tiếp tục job"}
        </button>
      </div>
    </div>
  ) : null

  return (
    <>
      <style>{css}</style><style>{helpTipCss}</style><style>{assistantComponentCss}</style>
      <ProductNav current={activeModule}/>
      <div className="shell">
        <div className="ops-page-head">
          <section className="ops-hero" aria-labelledby="ops-page-title">
            <div className="ops-hero-copy">
              <div className="ops-kicker">CTKM / Tem</div>
              <h1 id="ops-page-title">
                {activeModule === "ctkm" && "Tổng hợp chương trình khuyến mãi"}
                {activeModule === "expiration" && "Kiểm tra hạn dùng"}
                {activeModule === "temr" && "Phân bổ Tem R"}
                {activeModule === "inventory" && "Kiểm tồn kho"}
              </h1>
              <p>
                {activeModule === "ctkm" && "Chuẩn bị file nguồn, kiểm tra mapping, đối chiếu POG và xuất workbook hành động."}
                {activeModule === "expiration" && "Tra cứu mã sản phẩm, lô và hạn dùng trong một màn hình vận hành gọn."}
                {activeModule === "temr" && "Đọc đúng giá trị đang hiển thị trong file nguồn và tạo file phân bổ Tem R."}
                {activeModule === "inventory" && "Kiểm tồn store-level và coverage POG mà không cộng lặp tồn giữa nhiều vị trí kệ."}
              </p>
            </div>
            <div className="ops-hero-side">
              <div className="backend-status ops-backend-status">
                <span className={`status-dot ${
                  backendStatus === "ok" ? "ok" : backendStatus === "checking" ? "warn" : "err"
                }`} />
                {backendStatus === "ok" && "Backend kết nối"}
                {backendStatus === "checking" && "Đang kiểm tra backend…"}
                {backendStatus === "offline" && "Mất kết nối backend"}
              </div>
              {isAdmin ? (
                <div className="auth-actions">
                  <span className="admin-pill">ADMIN</span>
                  <button className="auth-button" onClick={logoutAdmin}>Đăng xuất</button>
                </div>
              ) : (
                <form className="auth-actions" onSubmit={loginAdmin}>
                  <input className="auth-input" value={adminUsername}
                    onChange={e => setAdminUsername(e.target.value)} placeholder="Tài khoản quản trị" />
                  <input className="auth-input" type="password" value={adminPassword}
                    onChange={e => setAdminPassword(e.target.value)} placeholder="Mật khẩu" />
                  <button className="auth-button" disabled={authLoading || !adminPassword}>
                    {authLoading ? "Đang vào…" : "Quản trị"}
                  </button>
                  {authError && <span className="auth-error">{authError}</span>}
                </form>
              )}
            </div>
          </section>

        </div>

        <div className={`main ${activeModule}-mode`}>

          {/* ── Sidebar ─────────────────────────────────────────────────────── */}
          <div className="sidebar">

            {/* File CTKM */}
            <div className="card">
              <div className="card-title">1 · File chương trình KM</div>
              <Dropzone
                label="File CTKM (.xlsx)"
                sub="Kéo thả hoặc click để chọn"
                file={ctkmFile}
                onFile={setCtkmFile}
              />
              {ctkmFile && (
                <>
                  {ctkmSheetLoading && (
                    <div className="sheet-hint">Đang đọc sheet CTKM…</div>
                  )}
                  {!ctkmSheetLoading && ctkmSheetOptions.length > 0 && (
                    <>
                      <select
                        className="sheet-select"
                        value={ctkmSheetName}
                        onChange={e => setCtkmSheetName(e.target.value)}
                      >
                        {ctkmSheetOptions.map(sn => (
                          <option key={sn} value={sn}>{sn}</option>
                        ))}
                      </select>
                      <div className="sheet-hint">
                        Chọn sheet CTKM cần tổng hợp trước khi chạy.
                      </div>
                    </>
                  )}
                  {ctkmSheetError && (
                    <div className="sheet-hint" style={{color:"var(--red)"}}>
                      {ctkmSheetError}
                    </div>
                  )}
                  {ctkmAdvanced && ctkmSheetName && pogFile && (
                    <>
                      <button
                        className="btn btn-ghost"
                        style={{marginTop:12}}
                        onClick={() => handlePreviewMapping(false)}
                        disabled={mappingLoading}
                      >
                        {mappingLoading ? "Đang lấy mapping…" : "Xem / duyệt mapping"}
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{marginTop:8}}
                        onClick={() => handlePreviewMapping(true)}
                        disabled={mappingLoading}
                      >
                        Mapping thủ công (không gọi Gemini)
                      </button>
                    </>
                  )}
                  {mappingError && (
                    <div className="sheet-hint" style={{color:"var(--red)"}}>
                      {mappingError}
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="card">
              <div className="card-title">1b · File Clearance (tùy chọn)</div>
              <Dropzone
                label="File Clearance (.xlsx)"
                sub="Bổ sung để tạo sheet xác nhận CTKM / Clearance"
                file={clearanceFile}
                onFile={setClearanceFile}
              />
            </div>

            {ctkmAdvanced && mappingPreview && (
              <div className="card">
                {(mappingPreview.mapping_warnings || []).length > 0 && (
                  <div className="sheet-hint" style={{color:"var(--accent)", marginBottom:12}}>
                    Không lấy được gợi ý từ Gemini. Hãy chọn các cột thủ công rồi bấm “Lưu mapping đã xác nhận”.
                  </div>
                )}
                <div className="card-title">Mapping CTKM cần duyệt</div>
                <div className="sheet-hint" style={{marginBottom:12}}>
                  Sheet: <b>{mappingPreview.ctkm_sheet_name}</b>. Sửa các cột mơ hồ trước khi chạy.
                </div>
                <div className="table-wrap mapping-table" style={{maxHeight:420, overflowY:"auto"}}>
                  <table>
                    <thead>
                      <tr>
                        <th>Cột gốc</th>
                        <th>Gợi ý</th>
                        <th>Confidence</th>
                        <th>Chốt lại</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(Object.entries(mappingPreview.ctkm_mapping?.mapping || {})).map(([src, dst]) => (
                        <tr key={src}>
                          <td title={src}>{src}</td>
                          <td>{dst}</td>
                          <td>{fmt(mappingPreview.ctkm_mapping?.confidence?.[src])}</td>
                          <td>
                            <select
                              className="sheet-select"
                              style={{marginTop:0, minWidth:190}}
                              value={ctkmMappingOverride[src] || dst || ""}
                              onChange={e => updateCtkmMapping(src, e.target.value)}
                            >
                              <option value="">(không map)</option>
                              {FACT_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                      {(mappingPreview.ctkm_mapping?.unmapped || []).map(src => (
                        <tr key={src}>
                          <td title={src}>{src}</td>
                          <td>(KHÔNG MAP)</td>
                          <td>—</td>
                          <td>
                            <select
                              className="sheet-select"
                              style={{marginTop:0, minWidth:190}}
                              value={ctkmMappingOverride[src] || ""}
                              onChange={e => updateCtkmMapping(src, e.target.value)}
                            >
                              <option value="">(không map)</option>
                              {FACT_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="sheet-hint" style={{marginTop:10}}>
                  Mapping đã duyệt sẽ được gửi vào backend, nên lần chạy sau có thể dùng cache thay vì gọi Gemini lại.
                </div>
                <div className="card-title" style={{marginTop:20}}>Mapping POG cần duyệt</div>
                <div className="sheet-hint" style={{marginBottom:12}}>
                  Sheet: <b>{mappingPreview.pog_sheet_name}</b>. Kiểm tra kỹ các cột `item_id`, `store_id`, `pog_code` nếu có.
                </div>
                <div className="table-wrap mapping-table" style={{maxHeight:320, overflowY:"auto"}}>
                  <table>
                    <thead>
                      <tr>
                        <th>Cột gốc</th>
                        <th>Gợi ý</th>
                        <th>Confidence</th>
                        <th>Chốt lại</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(Object.entries(mappingPreview.pog_mapping?.mapping || {})).map(([src, dst]) => (
                        <tr key={src}>
                          <td title={src}>{src}</td>
                          <td>{dst}</td>
                          <td>{fmt(mappingPreview.pog_mapping?.confidence?.[src])}</td>
                          <td>
                            <select
                              className="sheet-select"
                              style={{marginTop:0, minWidth:190}}
                              value={pogMappingOverride[src] || dst || ""}
                              onChange={e => updatePogMapping(src, e.target.value)}
                            >
                              <option value="">(không map)</option>
                              {POG_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                      {(mappingPreview.pog_mapping?.unmapped || []).map(src => (
                        <tr key={src}>
                          <td title={src}>{src}</td>
                          <td>(KHÔNG MAP)</td>
                          <td>—</td>
                          <td>
                            <select
                              className="sheet-select"
                              style={{marginTop:0, minWidth:190}}
                              value={pogMappingOverride[src] || ""}
                              onChange={e => updatePogMapping(src, e.target.value)}
                            >
                              <option value="">(không map)</option>
                              {POG_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button
                  className="btn btn-primary"
                  style={{marginTop:16}}
                  onClick={saveApprovedMapping}
                  disabled={!isAdmin || mappingSaving}
                >
                  {!isAdmin ? "Đăng nhập admin để lưu preset chung" : mappingSaving ? <><div className="spinner" /> Đang lưu mapping…</> : "Lưu mapping đã xác nhận"}
                </button>
                {mappingSaved && <div className="sheet-hint" style={{color:"var(--green)"}}>{mappingSaved}</div>}
              </div>
            )}

            {/* File POG */}
            <div className="card">
              <div className="card-title">2 · File vị trí kệ (POG)</div>
              <Dropzone
                label="File POG (.xlsx)"
                sub="Snapshot tháng tương ứng"
                file={pogFile}
                onFile={setPogFile}
              />
              {pogSheetLoading && (
                <div className="sheet-hint">Đang đọc danh sách sheet POG…</div>
              )}
              {!pogSheetLoading && pogSheetOptions.length > 0 && (
                <>
                  <select
                    className="sheet-select"
                    value={pogSheetName}
                    onChange={e => {
                      setPogSheetName(e.target.value)
                      setMappingPreview(null)
                      setPogMappingOverride({})
                    }}
                  >
                    {pogSheetOptions.map(sn => (
                      <option key={sn} value={sn}>{sn}</option>
                    ))}
                  </select>
                  <div className="sheet-hint">Chỉ sheet POG đã chọn sẽ được đọc đầy đủ.</div>
                </>
              )}
              {pogFile && pogSnapshotMonth && (
                <div className="sheet-hint">
                  Snapshot POG đọc được: <b>{pogSnapshotMonth}</b>
                </div>
              )}
              {pogFile && pogInspectError && (
                <div className="sheet-hint" style={{color:"var(--red)"}}>
                  {pogInspectError}
                </div>
              )}
            </div>

            {/* Tháng + options */}
            <div className="card">
              <div className="card-title">3 · Tháng báo cáo</div>
              <input
                type="month"
                className="month-input"
                value={month}
                onChange={e => setMonth(e.target.value)}
              />
              {pogSnapshotMonth && month && pogSnapshotMonth !== month && (
                <div className="sheet-hint" style={{color:"var(--accent)"}}>
                  POG đang là {pogSnapshotMonth}, còn tháng báo cáo là {month}.
                </div>
              )}
              {ctkmSheetOptions.length > 1 && !ctkmSheetName && (
                <div className="sheet-hint" style={{color:"var(--accent)"}}>
                  Hãy chọn sheet CTKM để tiếp tục.
                </div>
              )}
              {ctkmAdvanced && (
                <>
                  <label style={{
                    display:"flex", alignItems:"center", gap:8,
                    marginTop:14, fontSize:12.5, color:"var(--text2)", cursor:"pointer"
                  }}>
                    <input type="checkbox" checked={strict} onChange={e => setStrict(e.target.checked)} />
                    Dừng nếu tháng POG không khớp
                  </label>
                  <label style={{
                    display:"flex", alignItems:"center", gap:8,
                    marginTop:10, fontSize:12.5, color:"var(--text2)", cursor:"pointer"
                  }}>
                    <input type="checkbox" checked={savedOnly} onChange={e => setSavedOnly(e.target.checked)} />
                    Chỉ dùng mapping đã lưu (không gọi Gemini)
                  </label>
                </>
              )}
            </div>

            <button className="advanced-toggle" onClick={() => setCtkmAdvanced(value => !value)}>
              {ctkmAdvanced ? "− Ẩn thiết lập nâng cao" : "+ Thiết lập nâng cao"}
            </button>

            <div className={`card advanced-card ${ctkmAdvanced ? "" : "hidden"}`}>
              <div className="card-title">4 · Cột output mong muốn</div>
              <div className="sheet-hint">
                Chọn cột cần giữ trong file kết quả. Để trống nghĩa là dùng mặc định toàn bộ cột.
              </div>
              <div className="output-field-grid">
                {OUTPUT_FIELDS.map(field => (
                  <label key={field} style={{display:"flex", gap:8, alignItems:"center", fontSize:12.5, color:"var(--text2)", cursor:"pointer"}}>
                    <input
                      type="checkbox"
                      checked={selectedOutputColumns.includes(field)}
                      onChange={() => toggleOutputColumn(field)}
                      style={{accentColor:"var(--accent)"}}
                    />
                    {field}
                  </label>
                ))}
              </div>
              <div className="sheet-hint" style={{marginTop:10}}>
                Nếu không chọn gì, hệ thống sẽ xuất theo cấu trúc mặc định hiện tại.
              </div>
            </div>

            <div className={`card advanced-card ${ctkmAdvanced ? "" : "hidden"}`}>
              <div className="card-title">5 · Preset đã lưu</div>
              <div className="sheet-hint">
                Các mapping và output đã chốt sẽ được lưu ở backend theo signature workbook.
              </div>
              <button className="btn btn-ghost" style={{marginTop:12}} onClick={refreshPresets} disabled={!isAdmin || presetLoading}>
                {presetLoading ? "Đang tải…" : "Làm mới preset"}
              </button>
              {presetError && (
                <div className="sheet-hint" style={{color:"var(--red)", marginTop:8}}>{presetError}</div>
              )}
              <div style={{display:"flex", flexDirection:"column", gap:10, marginTop:12}}>
                {savedPresets.length === 0 && !presetLoading && (
                  <div className="sheet-hint">Chưa có preset nào.</div>
                )}
                {savedPresets.map(item => (
                  <div key={item.key} style={{
                    border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "10px 12px",
                    background: "var(--surface2)",
                  }}>
                    <div style={{fontSize:12, color:"var(--text)", fontFamily:"var(--mono)", wordBreak:"break-all"}}>
                      {item.key.slice(0, 36)}{item.key.length > 36 ? "…" : ""}
                    </div>
                    <div className="sheet-hint">
                      {item.updated_at ? `Cập nhật: ${item.updated_at}` : "Chưa rõ thời gian"}
                      {item.has_ctkm_mapping ? " · CTKM" : ""}
                      {item.has_pog_mapping ? " · POG" : ""}
                      {item.has_output_columns ? " · Output" : ""}
                    </div>
                    <button
                      className="btn btn-ghost"
                      style={{marginTop:8, padding:"8px 12px"}}
                      onClick={() => deletePreset(item.key)} disabled={!isAdmin}
                    >
                      Xoá preset
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="card tem-r-card">
              <div className="card-title" style={{display:"flex",alignItems:"center",gap:7}}>Tem R · phân bổ theo tồn và vị trí kệ <HelpTip title="Tem R" text="Chọn đúng sheet, mã P và cột tồn kho theo giá trị đang hiển thị. Mapping chỉ xác định cột dùng để tính; không thay đổi dữ liệu nguồn."/></div>
              <Dropzone
                label="File Tem R (.xlsx)"
                sub="Tải file lên rồi chọn các cột dùng để phân bổ"
                file={temRFile}
                onFile={file => {
                  setTemRFile(file)
                  setTemRResult(null)
                  localStorage.removeItem(TEM_R_RESULT_KEY)
                }}
              />
              {temRInspecting && <div className="sheet-hint">Đang đọc danh sách cột…</div>}
              {temRFile && !temRInspecting && !temRError && temRColumns.length === 0 && (
                <div className="status-strip warn" style={{marginTop:10}}>Không đọc được cột nào trong file Tem R.</div>
              )}
              {temRFile && !temRInspecting && temRColumns.length > 0 && (
                <>
                  {temRInspectInfo && (
                    <div className="sheet-hint" style={{color:"var(--green)"}}>
                      Đã đọc sheet “{temRInspectInfo.sheetName}”, tiêu đề tại dòng {temRInspectInfo.headerRow}: {temRColumns.length} cột.
                    </div>
                  )}
                  <label className="sheet-hint" style={{display:"block", marginTop:12}}>Sheet chứa mã P và tồn kho</label>
                  <select className="sheet-select" value={temRSheetName} onChange={e => {
                    const option = temRSheetOptions.find(item => item.sheet_name === e.target.value)
                    setTemRSheetName(e.target.value)
                    setTemRColumns(option?.columns || [])
                    setTemRItemColumn(option?.suggested_item_column || "")
                    setTemRStockColumn(option?.suggested_stock_column || "")
                    setTemRColumnMapping(option?.suggested_mapping || {})
                    setTemRInspectInfo(option ? {sheetName:option.sheet_name, headerRow:option.header_row} : null)
                  }}>
                    {temRSheetOptions.map(option => <option key={option.sheet_name} value={option.sheet_name}>{option.sheet_name}</option>)}
                  </select>
                  <div className="sheet-hint" style={{display:"block", marginTop:12}}>Xác nhận các cột bắt buộc</div>
                  {TEM_R_REQUIRED_COLUMNS.map(field => (
                    <div className="mapping-row" key={field}>
                      <label className="sheet-hint">{TEM_R_FIELD_LABELS[field]}</label>
                      <select
                        className="sheet-select"
                        value={temRColumnMapping[field] || ""}
                        onChange={e => {
                          const value = e.target.value
                          setTemRColumnMapping(current => ({...current, [field]:value}))
                          if (field === "ITEMID") setTemRItemColumn(value)
                        }}
                      >
                        <option value="">— Chọn cột —</option>
                        {temRColumns.map(column => <option key={column} value={column}>{column}</option>)}
                      </select>
                    </div>
                  ))}
                  <label className="sheet-hint" style={{display:"block", marginTop:12}}>
                    Cột nào chứa số lượng tồn kho?
                  </label>
                  <select
                    className="sheet-select"
                    value={temRStockColumn}
                    onChange={e => setTemRStockColumn(e.target.value)}
                  >
                    <option value="">— Chọn cột tồn kho —</option>
                    {temRColumns.map(column => <option key={column} value={column}>{column}</option>)}
                  </select>
                  <div className="sheet-hint">
                    Hệ thống chỉ gợi ý; hãy kiểm tra và xác nhận trước khi phân bổ.
                  </div>
                  <label className="sheet-hint" style={{display:"block", marginTop:12}}>
                    Khoảng cách vị trí tối đa được phép thay
                  </label>
                  <input
                    className="month-input"
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={temRMaxDistance}
                    onChange={e => setTemRMaxDistance(Number(e.target.value))}
                  />
                  {temRSelectedSources.length !== new Set(temRSelectedSources).size && (
                    <div className="sheet-hint" style={{color:"var(--red)"}}>
                      Mỗi trường phải sử dụng một cột khác nhau.
                    </div>
                  )}
                </>
              )}
              <button
                className="btn btn-primary"
                style={{marginTop:12}}
                disabled={!temRFile || !temRMappingComplete || temRInspecting || temRLoading || backendStatus !== "ok"}
                onClick={handleTemR}
              >
                {temRLoading
                  ? <><div className="spinner" /> {ownQueuePosition ? `Đang chờ · vị trí ${ownQueuePosition}…` : "Đang phân bổ Tem R…"}</>
                  : "Phân bổ Tem R"}
              </button>
              {temRLoading && queueHasWaiting && (
                <div className="status-strip info" style={{marginTop:10}}>
                  Tác vụ của bạn đang ở vị trí {ownQueuePosition || waitingJobs} trong hàng chờ. Không cần bấm lại.
                </div>
              )}
              {temRError && <div className="sheet-hint" style={{color:"var(--red)"}}>{temRError}</div>}
              {temRResult && (
                <>
                  <div className="sheet-hint" style={{color:"var(--green)"}}>
                    Đã thay {fmt(temRResult.summary?.tem_r_replaced_rows)} vị trí;
                    bỏ qua {fmt(temRResult.summary?.tem_r_skipped_stock_rows)} dòng thiếu/lỗi tồn kho;
                    ngoại lệ {fmt(temRResult.summary?.tem_r_exceptions)}.
                  </div>
                  <button className="btn btn-ghost" style={{marginTop:10}} onClick={downloadTemR}>
                    Tải file Tem R kết quả
                  </button>
                </>
              )}
            </div>

            {backendStatus === "offline" && (
              <div className="status-strip error">
                ⚠ Tạm thời mất kết nối backend. Hệ thống sẽ tự kiểm tra lại; dữ liệu bạn đã chọn vẫn được giữ nguyên.
              </div>
            )}

            {/* Run button */}
            <button
              className="btn btn-primary"
              disabled={!canRun}
              onClick={handleRun}
            >
              {step === STEPS.running
                ? <><div className="spinner" /> {ownQueuePosition ? `Đang chờ · vị trí ${ownQueuePosition}…` : "Đang xử lý…"}</>
                : "▶ Chạy pipeline"}
            </button>

            {/* Progress */}
            {step === STEPS.running && (
              <div className="progress-wrap">
                <div className="progress-bar">
                  <div className="progress-fill"
                    style={{width:`${Math.round((stepIdx/STEP_LABELS.length)*100)}%`,
                            transition:"width .4s"}} />
                </div>
                <div className="progress-label">
                  {STEP_LABELS[Math.min(stepIdx, STEP_LABELS.length-1)]}
                </div>
              </div>
            )}

            {/* Error */}
            {step === STEPS.error && error && (
              <div className="status-strip error">⚠ {error}</div>
            )}

            {/* Warnings */}
            {warnings.length > 0 && (
              <div>
                <div className="card-title" style={{marginBottom:8}}>Cảnh báo</div>
                <div className="warn-list">
                  {warnings.map((w,i) => (
                    <div key={i} className="warn-item">{w}</div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Main content ─────────────────────────────────────────────── */}
          <div className="content">
            <section className="inventory-card">
              <div className="inventory-head">
                <div><div className="inventory-kicker">Kiểm tồn kho</div><h1>Tồn store-level ↔ vị trí POG</h1><p>Dùng cùng file nguồn Tem R/POG. Không cộng tồn lặp khi một SKU xuất hiện ở nhiều vị trí.</p></div>
                <div className="inventory-rule">Stock 0 là dữ liệu hợp lệ · stock thiếu/#N/A là lỗi · nhiều giá trị tồn cho cùng Store+ITEMID phải review.</div>
              </div>
              <div className="inventory-setup">
                <Dropzone label="File tồn / POG (.xlsx)" sub="Có STOREID, ITEMID, POG, vị trí và cột tồn" file={temRFile} onFile={file=>{setTemRFile(file);setInventoryResult(null);setInventoryError("")}}/>
                <div className="inventory-config">
                  <h3>Cấu hình dữ liệu</h3>
                  {temRInspecting ? <div className="sheet-hint">Đang đọc file…</div> : <>
                    <div className="inventory-config-row">
                      <select value={temRSheetName} onChange={e=>setTemRSheetName(e.target.value)}>
                        <option value="">Chọn sheet</option>
                        {temRSheetOptions.map(option=><option key={option.sheet_name} value={option.sheet_name}>{option.sheet_name}</option>)}
                      </select>
                      <select value={temRStockColumn} onChange={e=>setTemRStockColumn(e.target.value)}>
                        <option value="">Chọn cột tồn kho</option>
                        {temRColumns.map(column=><option key={column} value={column}>{column}</option>)}
                      </select>
                    </div>
                    <div className="sheet-hint" style={{marginTop:8}}>Mapping Store / ITEMID / POG dùng cùng mapping Tem R đã nhận diện. Nếu file lạ, mở Tem R để xác nhận mapping chi tiết.</div>
                    <button className="btn btn-primary inventory-run" disabled={!temRMappingComplete||inventoryLoading||backendStatus!=="ok"} onClick={handleInventoryInspect}>
                      {inventoryLoading?<><div className="spinner"/> Đang kiểm tồn…</>:"Kiểm tồn kho"}
                    </button>
                  </>}
                  {inventoryError&&<div className="status-strip error" style={{marginTop:10}}>⚠ {inventoryError}</div>}
                </div>
              </div>
              {inventoryResult&&(()=>{
                const labels={ok:"Bình thường",stock_missing:"Lỗi tồn kho",stock_conflict:"Xung đột tồn",location_missing:"Thiếu vị trí"}
                const query=inventoryQuery.trim().toLocaleLowerCase("vi")
                const rows=(inventoryResult.rows||[]).filter(row=>(inventoryFilter==="all"||row.status===inventoryFilter)&&(!query||[row.item_id,row.item_name,row.store_id,...(row.pog_codes||[]),...(row.fixel_ids||[])].some(value=>String(value||"").toLocaleLowerCase("vi").includes(query))))
                return <>
                  <div className="inventory-stats">
                    <div className="inventory-stat"><span>Tổng SKU store-level</span><strong>{fmt(inventoryResult.total_items)}</strong></div>
                    <div className="inventory-stat ok"><span>Bình thường</span><strong>{fmt(inventoryResult.counts?.ok||0)}</strong></div>
                    <div className="inventory-stat bad"><span>Lỗi / xung đột tồn</span><strong>{fmt((inventoryResult.counts?.stock_missing||0)+(inventoryResult.counts?.stock_conflict||0))}</strong></div>
                    <div className="inventory-stat warn"><span>Thiếu vị trí POG</span><strong>{fmt(inventoryResult.counts?.location_missing||0)}</strong></div>
                  </div>
                  <div className="inventory-tools"><input value={inventoryQuery} onChange={e=>setInventoryQuery(e.target.value)} placeholder="Tìm ITEMID, tên, Store, POG, kệ…"/><select value={inventoryFilter} onChange={e=>setInventoryFilter(e.target.value)}><option value="all">Tất cả trạng thái</option><option value="stock_missing">Lỗi tồn kho</option><option value="stock_conflict">Xung đột tồn</option><option value="location_missing">Thiếu vị trí</option><option value="ok">Bình thường</option></select></div>
                  <div className="row-count">Hiển thị {rows.length} / {inventoryResult.total_items} SKU</div>
                  <div className="table-wrap"><table><thead><tr><th>Store</th><th>ITEMID</th><th>Tên sản phẩm</th><th>Tồn kho</th><th>Số vị trí</th><th>POG / Kệ / Location</th><th>Trạng thái</th></tr></thead><tbody>
                    {rows.map(row=><tr key={row.store_id+"|"+row.item_id}><td>{row.store_id||"—"}</td><td>{row.item_id}</td><td>{row.item_name||"—"}</td><td>{row.stock??(row.stock_values?.length?row.stock_values.join(" / "):"—")}</td><td>{row.position_count}</td><td><div className="inventory-position-list">{(row.positions||[]).map(position=>position.join(" · ")).join(" | ")||"—"}</div></td><td><span className={"inventory-status "+row.status}>{labels[row.status]||row.status}</span></td></tr>)}
                  </tbody></table></div>
                </>
              })()}
            </section>
            <div className="card expiration-card" style={{marginBottom:20}}>
              <div className="expiration-header">
                <div>
                  <div className="expiration-kicker">Kiểm tra hạn dùng</div>
                  <h1 className="expiration-title">Quét và đối chiếu sản phẩm</h1>
                  <div className="expiration-subtitle">Tải dữ liệu tồn kho, sau đó nhập tay hoặc quét mã trên sản phẩm.</div>
                </div>
                <div className="format-pill">MÃ_P;SỐ_LÔ;DD/MM/YYYY</div>
              </div>
              <div className="expiration-grid">
                <div>
                  <Dropzone
                    label="File hạn dùng (.xlsx)"
                    sub="Cần có ITEMID, BATCHNUMER, EXPDATE"
                    file={expirationFile}
                    onFile={file => { setExpirationFile(file); setExpirationResult(null); setExpirationError("") }}
                  />
                  <div className="sheet-hint" style={{marginTop:8}}>
                    Quét QR/barcode có nội dung: MÃ_P;SỐ_LÔ;DD/MM/YYYY
                  </div>
                  <div className="camera-actions">
                    {!cameraActive ? (
                      <button className="btn btn-ghost" onClick={startCamera}>Mở camera</button>
                    ) : (
                      <button className="btn btn-ghost" onClick={stopCamera}>■ Tắt camera</button>
                    )}
                    <button
                      className="btn btn-ghost"
                      onClick={() => { setExpirationEntries(""); setExpirationResult(null); setCameraMessage("") }}
                      disabled={!expirationEntries}
                    >
                      Xóa danh sách
                    </button>
                  </div>
                  {cameraActive && (
                    <div className="camera-wrap">
                      <video ref={cameraVideoRef} className="camera-video" playsInline muted />
                      <div className="camera-guide" />
                    </div>
                  )}
                  {cameraMessage && (
                    <div className="status-strip info" style={{marginTop:10}}>{cameraMessage}</div>
                  )}
                  {cameraError && (
                    <div className="status-strip error" style={{marginTop:10}}>⚠ {cameraError}</div>
                  )}
                </div>
                <div>
                  <textarea
                    className="entry-input"
                    value={expirationEntries}
                    onChange={e => setExpirationEntries(e.target.value)}
                    placeholder={"Mỗi sản phẩm một dòng, ví dụ:\nP29352;00526;18/03/2029"}
                    spellCheck="false"
                  />
                  <button
                    className="btn btn-primary"
                    style={{marginTop:10}}
                    onClick={handleExpirationCheck}
                    disabled={!expirationFile || !expirationEntries.trim() || expirationLoading || backendStatus !== "ok"}
                  >
                    {expirationLoading ? <><div className="spinner" /> Đang kiểm tra…</> : "Kiểm tra dữ liệu"}
                  </button>
                  {expirationError && <div className="status-strip error" style={{marginTop:10}}>⚠ {expirationError}</div>}
                </div>
              </div>

              {expirationResult && (
                <div style={{marginTop:18}}>
                  <div className={`status-strip ${expirationResult.unmatched ? "warn" : "success"}`}>
                    Sheet {expirationResult.sheet_name}: khớp {expirationResult.matched}/{expirationResult.total} dòng
                  </div>
                  <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginTop:12}}>
                    <select className="sheet-select" style={{marginTop:0}} value={expirationFilter} onChange={e => setExpirationFilter(e.target.value)}>
                      <option value="all">Tất cả dòng</option>
                      <option value="matched">Chỉ dòng khớp chính xác</option>
                      <option value="related">Chỉ lô/ngày khác cùng mã P</option>
                    </select>
                    <select className="sheet-select" style={{marginTop:0}} value={expirationSort} onChange={e => setExpirationSort(e.target.value)}>
                      <option value="expiry_desc">Hạn tốt nhất trước</option>
                      <option value="expiry_asc">Hạn gần nhất trước</option>
                      <option value="item">Theo mã sản phẩm</option>
                      <option value="input">Theo thứ tự nhập</option>
                    </select>
                  </div>
                  <div className="table-wrap" style={{marginTop:12}}>
                    <table>
                      <thead>
                        <tr>
                          <th>#</th><th>Sản phẩm</th><th>Số lô</th><th>Hạn dùng</th>
                          <th>Tồn</th><th>Trạng thái</th><th>Đối chiếu</th>
                        </tr>
                      </thead>
                      <tbody>
                        {expirationDisplayRows(expirationResult, expirationFilter, expirationSort).map(row => (
                          <tr key={row.rowKey}>
                            <td>{row.line}</td>
                            <td style={{minWidth:220}}>
                              <div style={{fontFamily:"var(--mono)", fontWeight:650}}>{row.item_id || row.input}</div>
                              {row.item_name && <div style={{fontFamily:"var(--font)", color:"var(--text2)", marginTop:3}}>{row.item_name}</div>}
                            </td>
                            <td>{row.batch_number || "—"}</td>
                            <td>{row.exp_date || "—"}</td>
                            <td>{row.on_hand ? `${row.on_hand}${row.inventory_unit ? ` ${row.inventory_unit}` : ""}` : "—"}</td>
                            <td><span className={`result-status ${row.status}`}>{row.status === "matched" ? "Khớp chính xác" : row.status === "related" ? "Cùng mã P" : "Không khớp"}</span></td>
                            <td style={{minWidth:220, whiteSpace:"normal", fontFamily:"var(--font)"}}>
                              <div>{row.message}</div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>


            {/* Idle state */}
            {step === STEPS.idle && (
              <div className="empty">
                <div className="empty-icon">📊</div>
                <div className="empty-title">Chọn file và tháng để bắt đầu</div>
                <div style={{fontSize:13,color:"var(--text3)",marginTop:6}}>
                  Upload file CTKM + file POG, chọn tháng báo cáo rồi nhấn Chạy pipeline
                </div>
              </div>
            )}

            {/* Running state */}
            {step === STEPS.running && (
              <div className="empty">
                <div className="empty-icon">⚙️</div>
                <div className="empty-title">Pipeline đang chạy…</div>
                <div style={{fontSize:13,color:"var(--text3)",marginTop:6}}>
                  {queueHasWaiting
                    ? `Tác vụ của bạn đang ở vị trí ${ownQueuePosition || waitingJobs} trong hàng chờ. Không cần bấm lại.`
                    : `Gemini đang nhận diện cột, ghép CTKM với POG theo tháng ${month}`}
                </div>
                <div style={{maxWidth:320,margin:"20px auto 0"}}>
                  {STEP_LABELS.map((label, i) => (
                    <div key={i} style={{
                      display:"flex", alignItems:"center", gap:10,
                      padding:"6px 0", fontSize:12.5,
                      color: i < stepIdx ? "var(--green)"
                           : i === stepIdx ? "var(--text)"
                           : "var(--text3)"
                    }}>
                      <span style={{fontFamily:"var(--mono)", fontSize:11, width:20, textAlign:"right"}}>
                        {i < stepIdx ? "✓" : i === stepIdx ? "▶" : String(i+1).padStart(2,"0")}
                      </span>
                      {label}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Done state */}
            {step === STEPS.done && result && (
              <>
                {/* Download bar */}
                <div className="download-bar">
                  <div style={{fontSize:24}}>📥</div>
                  <div className="download-info">
                    <div className="download-name">tong_hop_ctkm_{month}.xlsx</div>
                    <div className="download-meta">Workbook thao tác và audit · sẵn sàng tải xuống</div>
                  </div>
                  <button className="btn btn-primary" style={{width:"auto",padding:"10px 20px"}}
                    onClick={handleDownload}>
                    Tải xuống
                  </button>
                </div>

                {/* Summary stats */}
                <div className="ops-assistant"><Mascot state={Number(locationReview)>0||Number(overlapW)>0?"warning":"success"}/><div className="ops-assistant-copy"><div className="ops-assistant-title">Trợ lý kết quả CTKM <HelpTip title="Nguyên tắc hành động" text="POG chỉ cung cấp vị trí kệ (store/pog/location/facing), không quyết định Gắn, Tháo hay Chờ. Hành động CTKM vẫn theo rule nghiệp vụ và business date."/></div><GuideBubble>{Number(locationReview)>0||Number(overlapW)>0?"Có dữ liệu cần review. Hãy kiểm tra vị trí POG và cảnh báo trùng trước khi thao tác tem.":"Chưa thấy metric vị trí/trùng thời gian cần chú ý trong kết quả này."}</GuideBubble></div></div>
                <div className="section-title">
                  Kết quả tháng {month}
                </div>
                <div className="summary-grid" style={{marginBottom:28}}>
                  <StatBox num={matched}   label="Dòng khớp (CTKM + kệ)" sub={`${fmt(itemMatch)} item duy nhất`} />
                  <StatBox num={ctkmMiss}  label={<span className="metric-help">Thiếu vị trí POG <HelpTip title="CTKM thiếu vị trí kệ" text="CTKM vẫn là bản ghi CTKM hợp lệ nhưng chưa nối được vị trí kệ. Không dùng việc thiếu POG để tự đổi quyết định Gắn/Tháo."/></span>}
                    sub={hoaDon > 0 ? `${hoaDon} CTKM theo hóa đơn` : null}
                    accent="var(--accent)" />
                  <StatBox num={locationReview} label={<span className="metric-help">Cần review vị trí POG <HelpTip title="Review vị trí" text="Các dòng thiếu vị trí hoặc snapshot cần kiểm tra thủ công. Review vị trí là bước kiểm tra dữ liệu kệ, không phải một quyết định CTKM mới."/></span>}
                    sub="Gồm thiếu vị trí hoặc snapshot cần kiểm tra"
                    accent="var(--red)" />
                  <StatBox num={pogMiss}   label="POG không có CTKM phù hợp"
                    accent="var(--blue)" />
                  <StatBox num={overlapW}  label={<span className="metric-help">Cảnh báo trùng thời gian <HelpTip title="Overlap / conflict" text="Các CTKM có khoảng thời gian chồng lấn cần được đối chiếu theo SKU và channel. Cảnh báo không tự xoá hay gộp bản ghi nguồn."/></span>}
                    accent={overlapW > 0 ? "var(--red)" : "var(--green)"} />
                </div>

                {preview && <CtkmPreviewWorkspace preview={preview} activeSheet={activeSheet} setActiveSheet={setActiveSheet}/>}
              </>
            )}

            {/* Error state */}
            {step === STEPS.error && (
              <div className="empty">
                <div className="empty-icon">❌</div>
                <div className="empty-title">Pipeline gặp lỗi</div>
                <div style={{
                  marginTop:12, padding:"12px 16px", background:"var(--surface2)",
                  border:"1px solid var(--border)", borderRadius:"var(--radius)",
                  fontFamily:"var(--mono)", fontSize:12.5, color:"var(--red)",
                  maxWidth:560, margin:"12px auto 0"
                }}>
                  {error}
                </div>
                <button className="btn btn-ghost" style={{width:"auto",padding:"10px 20px",marginTop:20}}
                  onClick={() => setStep(STEPS.idle)}>
                  Thử lại
                </button>
              </div>
            )}

          </div>
        </div>
      </div>
    </>
  )
}

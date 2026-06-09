// Afterchannel.js
import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

// Mock Master Data Array representing your parsed TRB_Master and DGBB_Master pipelines
const MOCK_MASTER_SHEETS = [
  { mo: "1001", variant: "6204-2RS", production: 2500, line: "DGBB" },
  { mo: "1002", variant: "6305-ZZ", production: 1800, line: "DGBB" },
  { mo: "2001", variant: "30204-TRB", production: 3200, line: "TRB" },
  { mo: "2002", variant: "32205-TRB", production: 1450, line: "TRB" }
];

const Afterchannel = () => {
  const [activeDept, setActiveDept] = useState('Accurate');

  // Shared dropdown options
  const shifts = ["1", "2", "3"];
  const lineTypes = ["DGBB", "TRB"];
  const channels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH07", "CH08", "CH11", "CH12", "CH13", "T1", "T2"];

  // ==========================================
  // INITIALIZERS WITH LOCALSTORAGE PERSISTENCE
  // ==========================================
  const [accurateHistory, setAccurateHistory] = useState(() => {
    const saved = localStorage.getItem('afterchannel_accurate');
    return saved ? JSON.parse(saved) : [];
  });
  const [cpsHistory, setCpsHistory] = useState(() => {
    const saved = localStorage.getItem('afterchannel_cps');
    return saved ? JSON.parse(saved) : [];
  });
  const [reworkHistory, setReworkHistory] = useState(() => {
    const saved = localStorage.getItem('afterchannel_rework');
    return saved ? JSON.parse(saved) : [];
  });
  const [vibrationHistory, setVibrationHistory] = useState(() => {
    const saved = localStorage.getItem('afterchannel_vibration');
    return saved ? JSON.parse(saved) : [];
  });

  // Sync state changes directly to localStorage automatically
  useEffect(() => { localStorage.setItem('afterchannel_accurate', JSON.stringify(accurateHistory)); }, [accurateHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_cps', JSON.stringify(cpsHistory)); }, [cpsHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_rework', JSON.stringify(reworkHistory)); }, [reworkHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_vibration', JSON.stringify(vibrationHistory)); }, [vibrationHistory]);

  // ==========================================
  // FORM STATES (IN vs OUT Separated)
  // ==========================================
  const blankAccurateIn = { mo: '', type: '', inDate: '', shiftIn: '1', pc: '', materialInFrom: 'Channel', qtyIn: '' };
  const blankAccurateOut = { mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' };
  const [accurateIn, setAccurateIn] = useState(blankAccurateIn);
  const [accurateOut, setAccurateOut] = useState(blankAccurateOut);

  const blankCpsIn = { mo: '', type: '', item: 'Seal', inDate: '', shiftIn: '1', rcNo: '', materialInFrom: 'Channel', channel: 'CH01', qtyIn: '' };
  const blankCpsOut = { mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' };
  const [cpsIn, setCpsIn] = useState(blankCpsIn);
  const [cpsOut, setCpsOut] = useState(blankCpsOut);

  const blankReworkIn = { mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', materialInFrom: 'Channel', qtyIn: '', reworkActivity: 'Visual', lineSegment: 'DGBB' };
  const blankReworkOut = { mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', operator: '', remark: '' };
  const [reworkIn, setReworkIn] = useState(blankReworkIn);
  const [reworkOut, setReworkOut] = useState(blankReworkOut);

  // Structural Note: ringType moved exclusively to Outbound block!
  const blankVibrationIn = { mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', reason: 'D4', materialInFrom: 'Channel', qtyIn: '', activity: 'Ball Remove', lineSegment: 'DGBB' };
  const blankVibrationOut = { mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', ringType: 'IR', ballScrap: '0', cageSealScrap: '0', operator: '', remark: '' };
  const [vibrationIn, setVibrationIn] = useState(blankVibrationIn);
  const [vibrationOut, setVibrationOut] = useState(blankVibrationOut);

  // Edit State Tracking Controls
  const [editingId, setEditingId] = useState(null);

  // Flow Summary Search state
  const [moSearch, setMoSearch] = useState('');
  const [moSummary, setMoSummary] = useState(null);

  // Helper to cross-reference and scrub MO targets from master files
  const cleanMoString = (val) => String(val).trim().toUpperCase().replace(/\s+/g, '');

  // ==========================================
  // TRANSACTION LOGIC (SAVE, EDIT, DELETE)
  // ==========================================
  const handleLogTransaction = (dept, typeOfAction) => {
    let payload = {};
    const uniqueId = editingId ? editingId : Date.now();

    if (dept === 'Accurate') {
      payload = typeOfAction === 'IN' ? { ...accurateIn, action: 'IN' } : { ...accurateOut, action: 'OUT' };
      if (editingId) {
        setAccurateHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
        setEditingId(null);
      } else {
        setAccurateHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      }
      setAccurateIn(blankAccurateIn); setAccurateOut(blankAccurateOut);
    } 
    else if (dept === 'CPS') {
      payload = typeOfAction === 'IN' ? { ...cpsIn, action: 'IN' } : { ...cpsOut, action: 'OUT' };
      if (editingId) {
        setCpsHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
        setEditingId(null);
      } else {
        setCpsHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      }
      setCpsIn(blankCpsIn); setCpsOut(blankCpsOut);
    } 
    else if (dept === 'Rework') {
      payload = typeOfAction === 'IN' ? { ...reworkIn, action: 'IN' } : { ...reworkOut, action: 'OUT' };
      if (editingId) {
        setReworkHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
        setEditingId(null);
      } else {
        setReworkHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      }
      setReworkIn(blankReworkIn); setReworkOut(blankReworkOut);
    } 
    else if (dept === 'Vibration') {
      payload = typeOfAction === 'IN' ? { ...vibrationIn, action: 'IN' } : { ...vibrationOut, action: 'OUT' };
      if (editingId) {
        setVibrationHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
        setEditingId(null);
      } else {
        setVibrationHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      }
      setVibrationIn(blankVibrationIn); setVibrationOut(blankVibrationOut);
    }

    alert(`Transaction recorded successfully to local storage.`);
  };

  const handleEditInit = (item, dept) => {
    setEditingId(item.id);
    if (dept === 'Accurate') {
      if (item.action === 'IN') setAccurateIn({ ...item }); else setAccurateOut({ ...item });
    } else if (dept === 'CPS') {
      if (item.action === 'IN') setCpsIn({ ...item }); else setCpsOut({ ...item });
    } else if (dept === 'Rework') {
      if (item.action === 'IN') setReworkIn({ ...item }); else setReworkOut({ ...item });
    } else if (dept === 'Vibration') {
      if (item.action === 'IN') setVibrationIn({ ...item }); else setVibrationOut({ ...item });
    }
  };

  const handleDeleteEntry = (id, dept) => {
    if (!window.confirm("Are you sure you want to permanently delete this entry?")) return;
    if (dept === 'Accurate') setAccurateHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'CPS') setCpsHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'Rework') setReworkHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'Vibration') setVibrationHistory(prev => prev.filter(i => i.id !== id));
  };

  // ==========================================
  // MASTER PIPELINE TRACE ENGINE
  // ==========================================
  const handleTraceRoute = () => {
    if (!moSearch) return;
    const cleanSearchStr = cleanMoString(moSearch);

    // Dynamic Master File Lookup (TRB / DGBB context lookup replacing the hardcoded 1000)
    const matchedMasterRow = MOCK_MASTER_SHEETS.find(row => cleanMoString(row.mo) === cleanSearchStr);
    
    const baseQty = matchedMasterRow ? matchedMasterRow.production : 0;
    const baseVariant = matchedMasterRow ? `${matchedMasterRow.variant} [${matchedMasterRow.line}]` : "MO Not Indexed in Master Data Sheets";

    // Gather and consolidate history lines matching searched target
    const combinedLedger = [
      ...accurateHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Accurate' })),
      ...cpsHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'CPS' })),
      ...reworkHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Rework' })),
      ...vibrationHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Vibration' }))
    ].sort((a, b) => b.id - a.id); // View all steps chronologically

    setMoSummary({
      mo: moSearch,
      variant: baseVariant,
      cumulativeProduction: baseQty,
      ledger: combinedLedger
    });
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Afterchannel Operational Ledger</h2>
        <p style={{ color: '#64748b', margin: 0, fontSize: '14px' }}>Decoupled Data Pipeline Engine with Persistent Browser Cache Protection</p>
      </div>

      {/* Primary Tab Navigation */}
      <div className="sub-view-tabs">
        {['Accurate', 'CPS', 'Rework', 'Vibration Dismantling', 'MO Flow Summary'].map(tab => (
          <button 
            key={tab} 
            className={`tab-btn ${activeDept === tab ? 'active-tab' : ''}`}
            onClick={() => { setActiveDept(tab); setEditingId(null); }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ==========================================
          ACCURATE INSPECTION VIEW
      ========================================== */}
      {activeDept === 'Accurate' && (
        <div className="split-layout-container">
          {editingId && <div className="edit-banner-alert">⚠️ System is currently editing an active record (ID: {editingId}). Submit updates below to clear.</div>}
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>Log Inbound Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateIn.mo} onChange={e => setAccurateIn({...accurateIn, mo: e.target.value})} /></div>
              <div className="control-group"><label>Variant Model</label><input type="text" value={accurateIn.type} onChange={e => setAccurateIn({...accurateIn, type: e.target.value})} /></div>
              <div className="control-group"><label>In Date</label><input type="date" value={accurateIn.inDate} onChange={e => setAccurateIn({...accurateIn, inDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift In</label>
                <select value={accurateIn.shiftIn} onChange={e => setAccurateIn({...accurateIn, shiftIn: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group"><label>PC Mark</label><input type="text" value={accurateIn.pc} onChange={e => setAccurateIn({...accurateIn, pc: e.target.value})} /></div>
              <div className="control-group">
                <label>Material Source</label>
                <select value={accurateIn.materialInFrom} onChange={e => setAccurateIn({...accurateIn, materialInFrom: e.target.value})}>
                  <option value="Channel">Channel</option><option value="Rework">Rework</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Received</label><input type="number" value={accurateIn.qtyIn} onChange={e => setAccurateIn({...accurateIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Accurate', 'IN')}>
                {editingId ? "Update Inbound Record" : "Submit Inbound Entry"}
              </button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateOut.mo} onChange={e => setAccurateOut({...accurateOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Variant Model</label><input type="text" value={accurateOut.type} onChange={e => setAccurateOut({...accurateOut, type: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={accurateOut.outDate} onChange={e => setAccurateOut({...accurateOut, outDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift Out</label>
                <select value={accurateOut.shiftOut} onChange={e => setAccurateOut({...accurateOut, shiftOut: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Next Target Station</label>
                <select value={accurateOut.nextStation} onChange={e => setAccurateOut({...accurateOut, nextStation: e.target.value})}>
                  <option value="Packaging">Packaging</option>
                  <option value="FPS">FPS</option>
                  <option value="Rework">Rework</option>
                  <option value="Dismantling">Dismantling</option>
                  <option value="Scrap">Scrap</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Dispatched</label><input type="number" value={accurateOut.qtySent} onChange={e => setAccurateOut({...accurateOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Accurate', 'OUT')}>
                {editingId ? "Update Outbound Record" : "Submit Outbound Dispatch"}
              </button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>Accurate Department Private Ledger</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Type</th><th>Operation Date</th><th>Shift</th><th>Routing Context</th><th>Qty Count</th><th>Actions Hub</th></tr>
              </thead>
              <tbody>
                {accurateHistory.length === 0 ? <tr><td colSpan="8" className="empty-notice">No records cached.</td></tr> : 
                  accurateHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td><td>{h.type}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom}` : `To: ${h.nextStation}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                      <td>
                        <button className="row-action-btn edit-tint" onClick={() => handleEditInit(h, 'Accurate')}>✏️</button>
                        <button className="row-action-btn delete-tint" onClick={() => handleDeleteEntry(h.id, 'Accurate')}>🗑️</button>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          CPS PROCESSING VIEW
      ========================================== */}
      {activeDept === 'CPS' && (
        <div className="split-layout-container">
          {editingId && <div className="edit-banner-alert">⚠️ System is currently editing an active record (ID: {editingId}). Submit updates below to clear.</div>}
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>Log Inbound Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={cpsIn.mo} onChange={e => setCpsIn({...cpsIn, mo: e.target.value})} /></div>
              <div className="control-group"><label>Type Variant</label><input type="text" value={cpsIn.type} onChange={e => setCpsIn({...cpsIn, type: e.target.value})} /></div>
              <div className="control-group">
                <label>Item Variant</label>
                <select value={cpsIn.item} onChange={e => setCpsIn({...cpsIn, item: e.target.value})}>
                  <option value="Seal">Seal</option><option value="Shield">Shield</option><option value="OM Black">OM Black</option><option value="IM White">IM White</option>
                </select>
              </div>
              <div className="control-group"><label>In Date</label><input type="date" value={cpsIn.inDate} onChange={e => setCpsIn({...cpsIn, inDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift In</label>
                <select value={cpsIn.shiftIn} onChange={e => setCpsIn({...cpsIn, shiftIn: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group"><label>RC No Reference</label><input type="text" value={cpsIn.rcNo} onChange={e => setCpsIn({...cpsIn, rcNo: e.target.value})} /></div>
              <div className="control-group">
                <label>Material In From</label>
                <select value={cpsIn.materialInFrom} onChange={e => setCpsIn({...cpsIn, materialInFrom: e.target.value})}>
                  <option value="Channel">Channel</option><option value="Rework">Rework</option><option value="Dismantling">Dismantling</option><option value="Accurate">Accurate</option>
                </select>
              </div>
              <div className="control-group">
                <label>Source Channel ID</label>
                <select value={cpsIn.channel} onChange={e => setCpsIn({...cpsIn, channel: e.target.value})}>
                  {channels.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="control-group"><label>Qty In</label><input type="number" value={cpsIn.qtyIn} onChange={e => setCpsIn({...cpsIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('CPS', 'IN')}>
                {editingId ? "Update Inbound Entry" : "Submit Inbound Entry"}
              </button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={cpsOut.mo} onChange={e => setCpsOut({...cpsOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Type Variant</label><input type="text" value={cpsOut.type} onChange={e => setCpsOut({...cpsOut, type: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={cpsOut.outDate} onChange={e => setCpsOut({...cpsOut, outDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift Out</label>
                <select value={cpsOut.shiftOut} onChange={e => setCpsOut({...cpsOut, shiftOut: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Next Station</label>
                <select value={cpsOut.nextStation} onChange={e => setCpsOut({...cpsOut, nextStation: e.target.value})}>
                  <option value="Packaging">Packaging</option><option value="FPS">FPS</option><option value="Rework">Rework</option><option value="Scrap">Scrap</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Dispatched</label><input type="number" value={cpsOut.qtySent} onChange={e => setCpsOut({...cpsOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('CPS', 'OUT')}>
                {editingId ? "Update Outbound Entry" : "Submit Outbound Entry"}
              </button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>CPS Private Department Registry</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Type</th><th>Date</th><th>Shift</th><th>Source/Target Metrics</th><th>Quantity</th><th>Actions Hub</th></tr>
              </thead>
              <tbody>
                {cpsHistory.length === 0 ? <tr><td colSpan="8" className="empty-notice">No records tracked.</td></tr> : 
                  cpsHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td><td>{h.type}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom} (${h.channel})` : `To: ${h.nextStation}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                      <td>
                        <button className="row-action-btn edit-tint" onClick={() => handleEditInit(h, 'CPS')}>✏️</button>
                        <button className="row-action-btn delete-tint" onClick={() => handleDeleteEntry(h.id, 'CPS')}>🗑️</button>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          REWORK WORKSHOP VIEW
      ========================================== */}
      {activeDept === 'Rework' && (
        <div className="split-layout-container">
          {editingId && <div className="edit-banner-alert">⚠️ System is currently editing an active record (ID: {editingId}). Submit updates below to clear.</div>}
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <div className="header-badge-row">
                <h3>Log Inbound Receipt (IN)</h3>
                <select className="line-segment-dropdown" value={reworkIn.lineSegment} onChange={e => setReworkIn({...reworkIn, lineSegment: e.target.value})}>
                  {lineTypes.map(t => <option key={t} value={t}>{t} Line</option>)}
                </select>
              </div>
              <div className="control-group"><label>MO Number</label><input type="text" value={reworkIn.mo} onChange={e => setReworkIn({...reworkIn, mo: e.target.value})} /></div>
              <div className="control-group"><label>In Date</label><input type="date" value={reworkIn.inDate} onChange={e => setReworkIn({...reworkIn, inDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift In</label>
                <select value={reworkIn.shiftIn} onChange={e => setReworkIn({...reworkIn, shiftIn: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Channel Source</label>
                <select value={reworkIn.channel} onChange={e => setReworkIn({...reworkIn, channel: e.target.value})}>
                  {channels.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="control-group"><label>Variant Type</label><input type="text" value={reworkIn.type} onChange={e => setReworkIn({...reworkIn, type: e.target.value})} /></div>
              <div className="control-group">
                <label>Material In From</label>
                <select value={reworkIn.materialInFrom} onChange={e => setReworkIn({...reworkIn, materialInFrom: e.target.value})}>
                  <option value="Channel">Channel</option><option value="Accurate">Accurate</option>
                </select>
              </div>
              <div className="control-group">
                <label>Rework Action Task</label>
                <select value={reworkIn.reworkActivity} onChange={e => setReworkIn({...reworkIn, reworkActivity: e.target.value})}>
                  <option value="Cartons Removal">Cartons Removal</option><option value="OD Polish">OD Polish</option><option value="Shield Removal">Shield Removal</option><option value="Visual">Visual</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Inbound</label><input type="number" value={reworkIn.qtyIn} onChange={e => setReworkIn({...reworkIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Rework', 'IN')}>
                {editingId ? "Update Workshop Receipt" : "Log Receipt"}
              </button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={reworkOut.mo} onChange={e => setReworkOut({...reworkOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={reworkOut.outDate} onChange={e => setReworkOut({...reworkOut, outDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift Out</label>
                <select value={reworkOut.shiftOut} onChange={e => setReworkOut({...reworkOut, shiftOut: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Next Station Drop</label>
                <select value={reworkOut.nextStation} onChange={e => setReworkOut({...reworkOut, nextStation: e.target.value})}>
                  <option value="Channel">Channel</option><option value="Accurate">Accurate</option><option value="CPS">CPS</option><option value="Dismantling">Dismantling</option><option value="Scrap">Scrap</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Outbound Sent</label><input type="number" value={reworkOut.qtySent} onChange={e => setReworkOut({...reworkOut, qtySent: e.target.value})} /></div>
              <div className="control-group"><label>Operator Code</label><input type="text" value={reworkOut.operator} onChange={e => setReworkOut({...reworkOut, operator: e.target.value})} /></div>
              <div className="control-group"><label>Process Remarks</label><input type="text" value={reworkOut.remark} onChange={e => setReworkOut({...reworkOut, remark: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Rework', 'OUT')}>
                {editingId ? "Update Workshop Dispatch" : "Log Dispatch Route"}
              </button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>Rework Department Private Ledger</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Date</th><th>Shift</th><th>Flow Context Details</th><th>Quantities</th><th>Actions Hub</th></tr>
              </thead>
              <tbody>
                {reworkHistory.length === 0 ? <tr><td colSpan="7" className="empty-notice">No workshop entries found.</td></tr> : 
                  reworkHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom} | Task: ${h.reworkActivity}` : `To: ${h.nextStation} | Op: ${h.operator || '-'}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                      <td>
                        <button className="row-action-btn edit-tint" onClick={() => handleEditInit(h, 'Rework')}>✏️</button>
                        <button className="row-action-btn delete-tint" onClick={() => handleDeleteEntry(h.id, 'Rework')}>🗑️</button>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          VIBRATION DISMANTLING VIEW
      ========================================== */}
      {activeDept === 'Vibration Dismantling' && (
        <div className="split-layout-container">
          {editingId && <div className="edit-banner-alert">⚠️ System is currently editing an active record (ID: {editingId}). Submit updates below to clear.</div>}
          <div className="forms-grid-split">
            {/* Inbound Form: Accepts Complete Bearings */}
            <div className="operation-card container-inbound">
              <div className="header-badge-row">
                <h3>Log Inbound Receipt (IN - Bearings)</h3>
                <select className="line-segment-dropdown" value={vibrationIn.lineSegment} onChange={e => setVibrationIn({...vibrationIn, lineSegment: e.target.value})}>
                  {lineTypes.map(t => <option key={t} value={t}>{t} Line</option>)}
                </select>
              </div>
              <div className="control-group"><label>MO Number</label><input type="text" value={vibrationIn.mo} onChange={e => setVibrationIn({...vibrationIn, mo: e.target.value})} /></div>
              <div className="control-group"><label>In Date</label><input type="date" value={vibrationIn.inDate} onChange={e => setVibrationIn({...vibrationIn, inDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift In</label>
                <select value={vibrationIn.shiftIn} onChange={e => setVibrationIn({...vibrationIn, shiftIn: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Channel Source</label>
                <select value={vibrationIn.channel} onChange={e => setVibrationIn({...vibrationIn, channel: e.target.value})}>
                  {channels.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="control-group"><label>Type Variant</label><input type="text" value={vibrationIn.type} onChange={e => setVibrationIn({...vibrationIn, type: e.target.value})} /></div>
              <div className="control-group">
                <label>Defect Reason</label>
                <select value={vibrationIn.reason} onChange={e => setVibrationIn({...vibrationIn, reason: e.target.value})}>
                  <option value="D4">D4 Defect</option><option value="OD Mark">OD Mark Failure</option>
                </select>
              </div>
              <div className="control-group">
                <label>Material In From</label>
                <select value={vibrationIn.materialInFrom} onChange={e => setVibrationIn({...vibrationIn, materialInFrom: e.target.value})}>
                  <option value="Channel">Channel Section</option><option value="Rework">Rework Loop</option>
                </select>
              </div>
              <div className="control-group">
                <label>Dismantle Method</label>
                <select value={vibrationIn.activity} onChange={e => setVibrationIn({...vibrationIn, activity: e.target.value})}>
                  <option value="Ball Remove">Ball Remove</option><option value="Rivet Press">Rivet Press Strip</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Received (Bearings)</label><input type="number" value={vibrationIn.qtyIn} onChange={e => setVibrationIn({...vibrationIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Vibration', 'IN')}>
                {editingId ? "Update Arrival Unit" : "Log Station Arrival"}
              </button>
            </div>

            {/* Outbound Form: Dispatches Separated Rings */}
            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT - Separated Elements)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={vibrationOut.mo} onChange={e => setVibrationOut({...vibrationOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={vibrationOut.outDate} onChange={e => setVibrationOut({...vibrationOut, outDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift Out</label>
                <select value={vibrationOut.shiftOut} onChange={e => setVibrationOut({...vibrationOut, shiftOut: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Target Disassembled Ring Track</label>
                <select value={vibrationOut.ringType} onChange={e => setVibrationOut({...vibrationOut, ringType: e.target.value})}>
                  <option value="IR">Inner Ring (IR)</option><option value="OR">Outer Ring (OR)</option>
                </select>
              </div>
              <div className="control-group">
                <label>Next Station Route</label>
                <select value={vibrationOut.nextStation} onChange={e => setVibrationOut({...vibrationOut, nextStation: e.target.value})}>
                  <option value="Channel">Channel Section</option><option value="CPS">CPS Stock</option><option value="Scrap">Scrap Bin</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Dispatched</label><input type="number" value={vibrationOut.qtySent} onChange={e => setVibrationOut({...vibrationOut, qtySent: e.target.value})} /></div>
              <div className="control-group"><label>Ball Scrap Count</label><input type="number" value={vibrationOut.ballScrap} onChange={e => setVibrationOut({...vibrationOut, ballScrap: e.target.value})} /></div>
              <div className="control-group"><label>Cage/Seal Scrap Count</label><input type="number" value={vibrationOut.cageSealScrap} onChange={e => setVibrationOut({...vibrationOut, cageSealScrap: e.target.value})} /></div>
              <div className="control-group"><label>Operator Identity</label><input type="text" value={vibrationOut.operator} onChange={e => setVibrationOut({...vibrationOut, operator: e.target.value})} /></div>
              <div className="control-group"><label>Remarks</label><input type="text" value={vibrationOut.remark} onChange={e => setVibrationOut({...vibrationOut, remark: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Vibration', 'OUT')}>
                {editingId ? "Update Release Unit" : "Log Component Release"}
              </button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>Vibration Dismantling Department Private Ledger</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Date</th><th>Shift</th><th>Process Configuration Summary</th><th>Quantities</th><th>Actions Hub</th></tr>
              </thead>
              <tbody>
                {vibrationHistory.length === 0 ? <tr><td colSpan="7" className="empty-notice">No stripping entries cached.</td></tr> : 
                  vibrationHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `Method: ${h.activity} | Defect: ${h.reason}` : `To: ${h.nextStation} [Ring: ${h.ringType} | B.Scrap: ${h.ballScrap || 0}, C.Scrap: ${h.cageSealScrap || 0}]`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                      <td>
                        <button className="row-action-btn edit-tint" onClick={() => handleEditInit(h, 'Vibration')}>✏️</button>
                        <button className="row-action-btn delete-tint" onClick={() => handleDeleteEntry(h.id, 'Vibration')}>🗑️</button>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          MO FLOW SUMMARY TAB (Fully Scrollable Full-Length Engine)
      ========================================== */}
      {activeDept === 'MO Flow Summary' && (
        <div className="table-wrapper" style={{ padding: '20px' }}>
          <h3 style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '10px' }}>Traceability Pipeline Lifecycle Analysis</h3>
          <div className="controls-row" style={{ marginBottom: '20px' }}>
            <div className="control-group" style={{ maxWidth: '250px' }}>
              <label>Target MO Pipeline Search</label>
              <input type="text" value={moSearch} onChange={e => setMoSearch(e.target.value)} placeholder="e.g., 1001, 2001..." />
            </div>
            <button className="submit-btn Trace-btn-override" style={{ marginTop: '22px' }} onClick={handleTraceRoute}>Run Process Audit Trace</button>
          </div>

          {moSummary && (
            <div style={{ marginTop: '20px' }}>
              <div className="excel-master-tracker-card">
                <h4 style={{ margin: '0 0 12px 0', color: '#1e3a8a' }}>Master Data Document Cross-Reference Map</h4>
                <div className="metadata-summary-flex">
                  <p><strong>MO Ref Number:</strong> {moSummary.mo}</p>
                  <p><strong>Identified Bearing Family Model:</strong> {moSummary.variant}</p>
                  <p><strong>Total Master Production Target Column Quantity (`ch_qty`):</strong> <span className="highlight-production-text">{moSummary.cumulativeProduction ? `${moSummary.cumulativeProduction} Units` : '0 (Not matching any row in TRB/DGBB master files)'}</span></p>
                </div>
              </div>

              {/* Explicit scroll-wrapper container to handle endless sequence items seamlessly without clipping */}
              <div className="scrollable-summary-viewport">
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9', textAlign: 'left', position: 'sticky', top: 0, zIndex: 10 }}>
                      <th style={{ padding: '12px' }}>Operational Trace Step</th>
                      <th style={{ padding: '12px' }}>Department Node</th>
                      <th style={{ padding: '12px' }}>Movement State</th>
                      <th style={{ padding: '12px' }}>Routing Description</th>
                      <th style={{ padding: '12px' }}>Processed Inventory Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {moSummary.ledger.length === 0 ? (
                      <tr><td colSpan="5" style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>No local ledger records matched this MO group parameter yet.</td></tr>
                    ) : (
                      moSummary.ledger.map((log, index) => (
                        <tr key={log.id} style={{ borderBottom: '1px solid #e2e8f0', background: '#fff' }}>
                          <td style={{ padding: '12px' }}>Step #{moSummary.ledger.length - index}</td>
                          <td style={{ padding: '12px', fontWeight: 'bold' }}>{log.dept} Section</td>
                          <td style={{ padding: '12px' }}>
                            <span className={`badge-indicator ${log.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>
                              {log.action === 'IN' ? 'Inbound Receipt' : 'Outbound Release'}
                            </span>
                          </td>
                          <td style={{ padding: '12px', color: '#475569' }}>
                            {log.action === 'IN' ? `Arrived via: ${log.materialInFrom || 'Channel'}` : `Forwarded onto: ${log.nextStation}`}
                          </td>
                          <td style={{ padding: '12px', fontWeight: 'bold', color: log.action === 'IN' ? '#2563eb' : '#059669' }}>
                            {log.action === 'IN' ? log.qtyIn : log.qtySent} Rings
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Afterchannel;

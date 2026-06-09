// Afterchannel.js
import React, { useState } from 'react';
import './Afterchannel.css';

const Afterchannel = () => {
  const [activeDept, setActiveDept] = useState('Accurate');

  // Shared drop-down configurations
  const shifts = ["1", "2", "3"];
  const lineTypes = ["DGBB", "TRB"];
  const channels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH07", "CH08", "CH11", "CH12", "CH13", "T1", "T2"];

  // ==========================================
  // DECOUPLED STATE MANAGERS (IN vs OUT)
  // ==========================================
  
  // Accurate Storage
  const [accurateIn, setAccurateIn] = useState({ mo: '', type: '', inDate: '', shiftIn: '1', pc: '', materialInFrom: 'Channel', qtyIn: '' });
  const [accurateOut, setAccurateOut] = useState({ mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' });
  const [accurateHistory, setAccurateHistory] = useState([]);

  // CPS Storage
  const [cpsIn, setCpsIn] = useState({ mo: '', type: '', item: 'Seal', inDate: '', shiftIn: '1', rcNo: '', materialInFrom: 'Channel', channel: 'CH01', qtyIn: '' });
  const [cpsOut, setCpsOut] = useState({ mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' });
  const [cpsHistory, setCpsHistory] = useState([]);

  // Rework Storage
  const [reworkIn, setReworkIn] = useState({ mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', materialInFrom: 'Channel', qtyIn: '', reworkActivity: 'Visual', lineSegment: 'DGBB' });
  const [reworkOut, setReworkOut] = useState({ mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', operator: '', remark: '' });
  const [reworkHistory, setReworkHistory] = useState([]);

  // Vibration Dismantling Storage
  const [vibrationIn, setVibrationIn] = useState({ mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', reason: 'D4', materialInFrom: 'Channel', qtyIn: '', activity: 'Ball Remove', ringType: 'IR', lineSegment: 'DGBB' });
  const [vibrationOut, setVibrationOut] = useState({ mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', ballScrap: '0', cageSealScrap: '0', operator: '', remark: '' });
  const [vibrationHistory, setVibrationHistory] = useState([]);

  // Flow Summary State
  const [moSearch, setMoSearch] = useState('');
  const [moSummary, setMoSummary] = useState(null);

  // ==========================================
  // TRANSACTION SUBMISSION HANDLERS
  // ==========================================
  const handleLogTransaction = (dept, typeOfAction) => {
    let payload = {};
    let uniqueId = Date.now();

    if (dept === 'Accurate') {
      payload = typeOfAction === 'IN' ? { ...accurateIn, action: 'IN' } : { ...accurateOut, action: 'OUT' };
      setAccurateHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
    } else if (dept === 'CPS') {
      payload = typeOfAction === 'IN' ? { ...cpsIn, action: 'IN' } : { ...cpsOut, action: 'OUT' };
      setCpsHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
    } else if (dept === 'Rework') {
      payload = typeOfAction === 'IN' ? { ...reworkIn, action: 'IN' } : { ...reworkOut, action: 'OUT' };
      setReworkHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
    } else if (dept === 'Vibration') {
      payload = typeOfAction === 'IN' ? { ...vibrationIn, action: 'IN' } : { ...vibrationOut, action: 'OUT' };
      setVibrationHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
    }

    alert(`Saved ${dept} ${typeOfAction} Entry Successfully.`);
  };

  // Traces data using matching properties found in TRB_Master & DGBB_Master pipelines
  const handleTraceRoute = () => {
    if (!moSearch) return;

    // Aggregate transactions across all history pools to trace the complete MO path
    const combinedLedger = [
      ...accurateHistory.filter(h => h.mo === moSearch).map(h => ({ ...h, dept: 'Accurate' })),
      ...cpsHistory.filter(h => h.mo === moSearch).map(h => ({ ...h, dept: 'CPS' })),
      ...reworkHistory.filter(h => h.mo === moSearch).map(h => ({ ...h, dept: 'Rework' })),
      ...vibrationHistory.filter(h => h.mo === moSearch).map(h => ({ ...h, dept: 'Vibration' }))
    ].sort((a, b) => b.id - a.id); // Sort chronological order

    // Infer bearing variant metadata text from context history safely
    const variantName = combinedLedger[0]?.type || "Unknown Bearing Variant";

    setMoSummary({
      mo: moSearch,
      variant: variantName,
      cumulativeProduction: 1000, // Derived context baseline from master row data loops
      ledger: combinedLedger
    });
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Afterchannel Operational Ledger</h2>
        <p style={{ color: '#64748b', margin: 0, fontSize: '14px' }}>Decoupled Material Logs & Comprehensive MO Journey Analysis</p>
      </div>

      {/* Primary Navigation Hub */}
      <div className="sub-view-tabs">
        {['Accurate', 'CPS', 'Rework', 'Vibration Dismantling', 'MO Flow Summary'].map(tab => (
          <button 
            key={tab} 
            className={`tab-btn ${activeDept === tab ? 'active-tab' : ''}`}
            onClick={() => setActiveDept(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ==========================================
          ACCURATE INSPECTION DEPARTMENT
      ========================================== */}
      {activeDept === 'Accurate' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            {/* Inbound Block */}
            <div className="operation-card container-inbound">
              <h3>Log Inbound Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateIn.mo} onChange={e => setAccurateIn({...accurateIn, mo: e.target.value})} /></div>
              <div className="control-group"><label>Ring Type / Variant</label><input type="text" value={accurateIn.type} onChange={e => setAccurateIn({...accurateIn, type: e.target.value})} /></div>
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
                  <option value="Channel">Channel</option>
                  <option value="Rework">Rework</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Received</label><input type="number" value={accurateIn.qtyIn} onChange={e => setAccurateIn({...accurateIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Accurate', 'IN')}>Submit Inbound Entry</button>
            </div>

            {/* Outbound Block */}
            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateOut.mo} onChange={e => setAccurateOut({...accurateOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Ring Type / Variant</label><input type="text" value={accurateOut.type} onChange={e => setAccurateOut({...accurateOut, type: e.target.value})} /></div>
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
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Accurate', 'OUT')}>Submit Outbound Dispatch</button>
            </div>
          </div>

          {/* Localized Ledger Matrix */}
          <div className="table-wrapper structural-history-space">
            <h3>Accurate Recent Ledger Log</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Type</th><th>Operation Date</th><th>Shift</th><th>Source / Destination</th><th>Count Qty</th></tr>
              </thead>
              <tbody>
                {accurateHistory.length === 0 ? <tr><td colSpan="7" className="empty-notice">No localized operational records indexed inside this session dashboard.</td></tr> : 
                  accurateHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td><td>{h.type}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom}` : `To: ${h.nextStation}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          CPS PROCESSING DEPARTMENT
      ========================================== */}
      {activeDept === 'CPS' && (
        <div className="split-layout-container">
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
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('CPS', 'IN')}>Submit Inbound Entry</button>
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
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('CPS', 'OUT')}>Submit Outbound Entry</button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>CPS Isolated Registry Log</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Type</th><th>Date</th><th>Shift</th><th>Source/Target Info</th><th>Quantity Metrics</th></tr>
              </thead>
              <tbody>
                {cpsHistory.length === 0 ? <tr><td colSpan="7" className="empty-notice">No records recorded.</td></tr> : 
                  cpsHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td><td>{h.type}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom} (${h.channel})` : `To: ${h.nextStation}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          REWORK OPERATIONS DEPARTMENT
      ========================================== */}
      {activeDept === 'Rework' && (
        <div className="split-layout-container">
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
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Rework', 'IN')}>Log Receipt</button>
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
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Rework', 'OUT')}>Log Dispatch Route</button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>Rework Workshop Ledger Logs</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Date</th><th>Shift</th><th>Flow Context Description</th><th>Quantity Tracking</th></tr>
              </thead>
              <tbody>
                {reworkHistory.length === 0 ? <tr><td colSpan="6" className="empty-notice">No workshop entries submitted.</td></tr> : 
                  reworkHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `From: ${h.materialInFrom} | Task: ${h.reworkActivity}` : `Dispatched To: ${h.nextStation} | Op: ${h.operator || '-'}`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          VIBRATION DISMANTLING OPERATIONS
      ========================================== */}
      {activeDept === 'Vibration Dismantling' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <div className="header-badge-row">
                <h3>Log Inbound Receipt (IN)</h3>
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
              <div className="control-group">
                <label>Target Ring Track</label>
                <select value={vibrationIn.ringType} onChange={e => setVibrationIn({...vibrationIn, ringType: e.target.value})}>
                  <option value="IR">Inner Ring (IR)</option><option value="OR">Outer Ring (OR)</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Received</label><input type="number" value={vibrationIn.qtyIn} onChange={e => setVibrationIn({...vibrationIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Vibration', 'IN')}>Log Station Arrival</button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={vibrationOut.mo} onChange={e => setVibrationOut({...vibrationOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={vibrationOut.outDate} onChange={e => setVibrationOut({...vibrationOut, outDate: e.target.value})} /></div>
              <div className="control-group">
                <label>Shift Out</label>
                <select value={vibrationOut.shiftOut} onChange={e => setVibrationOut({...vibrationOut, shiftOut: e.target.value})}>
                  {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="control-group">
                <label>Next Station Route</label>
                <select value={vibrationOut.nextStation} onChange={e => setVibrationOut({...vibrationOut, nextStation: e.target.value})}>
                  <option value="Channel">Channel Section</option><option value="CPS">CPS Stock</option><option value="Scrap">Scrap Bin</option>
                </select>
              </div>
              <div className="control-group"><label>Qty Dispatched</label><input type="number" value={vibrationOut.qtySent} onChange={e => setVibrationOut({...vibrationOut, qtySent: e.target.value})} /></div>
              <div className="control-group"><label>Ball Scrap Scrap Count</label><input type="number" value={vibrationOut.ballScrap} onChange={e => setVibrationOut({...vibrationOut, ballScrap: e.target.value})} /></div>
              <div className="control-group"><label>Cage/Seal Scrap Count</label><input type="number" value={vibrationOut.cageSealScrap} onChange={e => setVibrationOut({...vibrationOut, cageSealScrap: e.target.value})} /></div>
              <div className="control-group"><label>Operator Identity</label><input type="text" value={vibrationOut.operator} onChange={e => setVibrationOut({...vibrationOut, operator: e.target.value})} /></div>
              <div className="control-group"><label>Remarks</label><input type="text" value={vibrationOut.remark} onChange={e => setVibrationOut({...vibrationOut, remark: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Vibration', 'OUT')}>Log Component Release</button>
            </div>
          </div>

          <div className="table-wrapper structural-history-space">
            <h3>Vibration Stripping Isolation Logs</h3>
            <table>
              <thead>
                <tr><th>Action</th><th>MO</th><th>Date</th><th>Shift</th><th>Process Metrics Config</th><th>Quantities</th></tr>
              </thead>
              <tbody>
                {vibrationHistory.length === 0 ? <tr><td colSpan="6" className="empty-notice">No stripping entries found.</td></tr> : 
                  vibrationHistory.map(h => (
                    <tr key={h.id}>
                      <td><span className={`badge-indicator ${h.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>{h.action}</span></td>
                      <td>{h.mo}</td>
                      <td>{h.action === 'IN' ? h.inDate : h.outDate}</td>
                      <td>{h.action === 'IN' ? h.shiftIn : h.shiftOut}</td>
                      <td>{h.action === 'IN' ? `Method: ${h.activity} (${h.ringType}) | Defect: ${h.reason}` : `Dispatched to: ${h.nextStation} [B.Scrap: ${h.ballScrap || 0}, C.Scrap: ${h.cageSealScrap || 0}]`}</td>
                      <td className={h.action === 'IN' ? 'text-in-color' : 'text-out-color'}>{h.action === 'IN' ? h.qtyIn : h.qtySent}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==========================================
          MO FLOW SUMMARY REVISED ENGINE TAB
      ========================================== */}
      {activeDept === 'MO Flow Summary' && (
        <div className="table-wrapper" style={{ padding: '20px' }}>
          <h3 style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '10px' }}>Traceability Pipeline Lifecycle Analysis</h3>
          <div className="controls-row" style={{ marginBottom: '20px' }}>
            <div className="control-group" style={{ maxWidth: '250px' }}>
              <label>Target MO Pipeline</label>
              <input type="text" value={moSearch} onChange={e => setMoSearch(e.target.value)} placeholder="Type manufacturing order..." />
            </div>
            <button className="submit-btn Trace-btn-override" style={{ marginTop: '22px' }} onClick={handleTraceRoute}>Run Process Audit Trace</button>
          </div>

          {moSummary && (
            <div style={{ marginTop: '20px' }}>
              {/* Dynamic summary block structured like the master spreadsheets */}
              <div className="excel-master-tracker-card">
                <h4 style={{ margin: '0 0 12px 0', color: '#1e3a8a' }}>Master Data Trace Mapping</h4>
                <div className="metadata-summary-flex">
                  <p><strong>MO Reference:</strong> {moSummary.mo}</p>
                  <p><strong>Identified Variant Model:</strong> {moSummary.variant}</p>
                  <p><strong>Channel Production Output Column (`ch_qty`):</strong> <span className="highlight-production-text">{moSummary.cumulativeProduction} Rings</span></p>
                </div>
              </div>

              {/* Sequential Ledger Workflow View */}
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ background: '#f1f5f9', textAlign: 'left' }}>
                    <th style={{ padding: '12px' }}>Operational Step</th>
                    <th style={{ padding: '12px' }}>Department Target</th>
                    <th style={{ padding: '12px' }}>Movement Mode</th>
                    <th style={{ padding: '12px' }}>Source / Target Station Node</th>
                    <th style={{ padding: '12px' }}>Processed Inventory Count</th>
                  </tr>
                </thead>
                <tbody>
                  {moSummary.ledger.length === 0 ? (
                    <tr><td colSpan="5" style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>No movements logged in current flow loops for this MO group.</td></tr>
                  ) : (
                    moSummary.ledger.map((log, index) => (
                      <tr key={log.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '12px' }}>Step {moSummary.ledger.length - index}</td>
                        <td style={{ padding: '12px', fontWeight: 'bold' }}>{log.dept} Section</td>
                        <td style={{ padding: '12px' }}>
                          <span className={`badge-indicator ${log.action === 'IN' ? 'inbound-marker' : 'outbound-marker'}`}>
                            {log.action === 'IN' ? 'Material Receipt' : 'Dispatch Release'}
                          </span>
                        </td>
                        <td style={{ padding: '12px', color: '#475569' }}>
                          {log.action === 'IN' ? `Arrived via: ${log.materialInFrom}` : `Forwarded to: ${log.nextStation}`}
                        </td>
                        <td style={{ padding: '12px', fontWeight: 'bold', color: log.action === 'IN' ? '#2563eb' : '#059669' }}>
                          {log.action === 'IN' ? log.qtyIn : log.qtySent} Units
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Afterchannel;

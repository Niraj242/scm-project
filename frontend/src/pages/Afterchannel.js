import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

// Using your environment variable fallback directly to match your SCM core layout
const API = process.env.REACT_APP_API_URL || 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeDept, setActiveDept] = useState('Accurate');
  const [masterVariants, setMasterVariants] = useState({});

  // Shared Core Configuration Options
  const shifts = ["1", "2", "3"];
  const lineTypes = ["DGBB", "TRB"];
  const channels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH07", "CH08", "CH11", "CH12", "CH13", "T1", "T2"];
  const reworkActivities = ["Visual Check", "Demagnetization", "Washing", "Rethreading", "Polishing"];
  const vibrationReasons = ["D4", "High Noise", "Wavy Track", "Vibration Spike", "Cage Defect"];
  const dismantlingActivities = ["Ball Remove", "Full Strip Down", "Inner Ring Salvage", "Outer Ring Salvage"];

  // Fetch parsed variant datasets from Google Sheets layout
  useEffect(() => {
    fetch(`${API}/api/mo-lookup`)
      .then(res => {
        if (!res.ok) throw new Error('Network response failure fetching mapping dictionary.');
        return res.json();
      })
      .then(json => {
        if (json.status === 'success') setMasterVariants(json.data);
      })
      .catch(err => console.error("Error setting master variant recommendation registry:", err));
  }, []);

  // Filter out applicable variants under the matched typed MO
  const getVariantsForMo = (moStr) => {
    if (!moStr) return [];
    const cleanMo = String(moStr).trim().toUpperCase();
    return masterVariants[cleanMo] || [];
  };

  // State initialization with complete localStorage tracking
  const [accurateHistory, setAccurateHistory] = useState(() => JSON.parse(localStorage.getItem('afterchannel_accurate')) || []);
  const [cpsHistory, setCpsHistory] = useState(() => JSON.parse(localStorage.getItem('afterchannel_cps')) || []);
  const [reworkHistory, setReworkHistory] = useState(() => JSON.parse(localStorage.getItem('afterchannel_rework')) || []);
  const [vibrationHistory, setVibrationHistory] = useState(() => JSON.parse(localStorage.getItem('afterchannel_vibration')) || []);

  useEffect(() => { localStorage.setItem('afterchannel_accurate', JSON.stringify(accurateHistory)); }, [accurateHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_cps', JSON.stringify(cpsHistory)); }, [cpsHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_rework', JSON.stringify(reworkHistory)); }, [reworkHistory]);
  useEffect(() => { localStorage.setItem('afterchannel_vibration', JSON.stringify(vibrationHistory)); }, [vibrationHistory]);

  // Form Field State Clean Slates
  const blankAccurateIn = { mo: '', type: '', inDate: '', shiftIn: '1', pc: '', materialInFrom: 'Channel', qtyIn: '' };
  const blankAccurateOut = { mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' };
  const blankCpsIn = { mo: '', type: '', item: 'Seal', inDate: '', shiftIn: '1', rcNo: '', materialInFrom: 'Channel', channel: 'CH01', qtyIn: '' };
  const blankCpsOut = { mo: '', type: '', outDate: '', shiftOut: '1', nextStation: 'Packaging', qtySent: '' };
  const blankReworkIn = { mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', materialInFrom: 'Channel', qtyIn: '', reworkActivity: 'Visual Check', lineSegment: 'DGBB' };
  const blankReworkOut = { mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', operator: '', remark: '' };
  const blankVibrationIn = { mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', reason: 'D4', materialInFrom: 'Channel', qtyIn: '', activity: 'Ball Remove', lineSegment: 'DGBB' };
  const blankVibrationOut = { mo: '', outDate: '', shiftOut: '1', nextStation: 'Channel', qtySent: '', ringType: 'IR', ballScrap: '0', cageSealScrap: '0', operator: '', remark: '' };

  const [accurateIn, setAccurateIn] = useState(blankAccurateIn);
  const [accurateOut, setAccurateOut] = useState(blankAccurateOut);
  const [cpsIn, setCpsIn] = useState(blankCpsIn);
  const [cpsOut, setCpsOut] = useState(blankCpsOut);
  const [reworkIn, setReworkIn] = useState(blankReworkIn);
  const [reworkOut, setReworkOut] = useState(blankReworkOut);
  const [vibrationIn, setVibrationIn] = useState(blankVibrationIn);
  const [vibrationOut, setVibrationOut] = useState(blankVibrationOut);

  const [editingId, setEditingId] = useState(null);
  const [moSearch, setMoSearch] = useState('');
  const [moSummary, setMoSummary] = useState(null);

  const cleanMoString = (val) => String(val).trim().toUpperCase().replace(/\s+/g, '');

  const handleLogTransaction = (dept, typeOfAction) => {
    let payload = {};
    const uniqueId = editingId ? editingId : Date.now();

    if (dept === 'Accurate') {
      payload = typeOfAction === 'IN' ? { ...accurateIn, action: 'IN' } : { ...accurateOut, action: 'OUT' };
      if (editingId) setAccurateHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
      else setAccurateHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      setAccurateIn(blankAccurateIn); setAccurateOut(blankAccurateOut);
    } 
    else if (dept === 'CPS') {
      payload = typeOfAction === 'IN' ? { ...cpsIn, action: 'IN' } : { ...cpsOut, action: 'OUT' };
      if (editingId) setCpsHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
      else setCpsHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      setCpsIn(blankCpsIn); setCpsOut(blankCpsOut);
    } 
    else if (dept === 'Rework') {
      payload = typeOfAction === 'IN' ? { ...reworkIn, action: 'IN' } : { ...reworkOut, action: 'OUT' };
      if (editingId) setReworkHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
      else setReworkHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      setReworkIn(blankReworkIn); setReworkOut(blankReworkOut);
    } 
    else if (dept === 'Vibration') {
      payload = typeOfAction === 'IN' ? { ...vibrationIn, action: 'IN' } : { ...vibrationOut, action: 'OUT' };
      if (editingId) setVibrationHistory(prev => prev.map(item => item.id === editingId ? { ...payload, id: editingId } : item));
      else setVibrationHistory(prev => [{ id: uniqueId, ...payload }, ...prev]);
      setVibrationIn(blankVibrationIn); setVibrationOut(blankVibrationOut);
    }
    setEditingId(null);
  };

  const handleEditInit = (item, dept) => {
    setEditingId(item.id);
    if (dept === 'Accurate') { if (item.action === 'IN') setAccurateIn({ ...item }); else setAccurateOut({ ...item }); }
    else if (dept === 'CPS') { if (item.action === 'IN') setCpsIn({ ...item }); else setCpsOut({ ...item }); }
    else if (dept === 'Rework') { if (item.action === 'IN') setReworkIn({ ...item }); else setReworkOut({ ...item }); }
    else if (dept === 'Vibration') { if (item.action === 'IN') setVibrationIn({ ...item }); else setVibrationOut({ ...item }); }
    setActiveDept(dept === 'Vibration' ? 'Vibration Dismantling' : dept);
  };

  const handleDeleteEntry = (id, dept) => {
    if (!window.confirm("Are you sure you want to completely delete this operational row entry?")) return;
    if (dept === 'Accurate') setAccurateHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'CPS') setCpsHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'Rework') setReworkHistory(prev => prev.filter(i => i.id !== id));
    if (dept === 'Vibration') setVibrationHistory(prev => prev.filter(i => i.id !== id));
  };

  const handleTraceRoute = () => {
    if (!moSearch) return;
    const cleanSearchStr = cleanMoString(moSearch);
    const moData = masterVariants[cleanSearchStr] || [];
    const baseVariant = moData.length > 0 ? moData.map(v => v.type).join(' | ') : "N/A";
    const baseQty = moData.length > 0 ? moData.reduce((sum, v) => sum + Number(v.qty || 0), 0) : 0;

    const combinedLedger = [
      ...accurateHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Accurate Assembly' })),
      ...cpsHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'CPS Station' })),
      ...reworkHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Rework Cell' })),
      ...vibrationHistory.filter(h => cleanMoString(h.mo) === cleanSearchStr).map(h => ({ ...h, dept: 'Vibration Dismantling' }))
    ].sort((a, b) => b.id - a.id);

    setMoSummary({ mo: moSearch, variant: baseVariant, cumulativeProduction: baseQty, ledger: combinedLedger });
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Afterchannel Operational Ledger</h2>
        <p className="sub-tag">Station Execution Tracking System</p>
      </div>

      <div className="sub-view-tabs">
        {['Accurate', 'CPS', 'Rework', 'Vibration Dismantling', 'MO Flow Summary'].map(tab => (
          <button key={tab} className={`tab-btn ${activeDept === tab ? 'active-tab' : ''}`} onClick={() => { setActiveDept(tab); setEditingId(null); }}>
            {tab}
          </button>
        ))}
      </div>

      {/* ACCURATE ASSEMBLY SECTION */}
      {activeDept === 'Accurate' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>Log Inbound Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateIn.mo} onChange={e => setAccurateIn({...accurateIn, mo: e.target.value})} placeholder="e.g. MO100234" /></div>
              
              <div className="control-group">
                <label>Variant Model (Auto-Fill)</label>
                <input 
                  type="text" list="acc-in-variants" value={accurateIn.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(accurateIn.mo).find(v => v.type === val);
                    setAccurateIn({...accurateIn, type: val, qtyIn: match ? match.qty : accurateIn.qtyIn});
                  }} 
                  placeholder="Type to view variants..."
                />
                <datalist id="acc-in-variants">
                  {getVariantsForMo(accurateIn.mo).map((v, i) => <option key={i} value={v.type}>{`Target Qty: ${v.qty}`}</option>)}
                </datalist>
              </div>

              <div className="control-group"><label>In Date</label><input type="date" value={accurateIn.inDate} onChange={e => setAccurateIn({...accurateIn, inDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift In</label><select value={accurateIn.shiftIn} onChange={e => setAccurateIn({...accurateIn, shiftIn: e.target.value})}>{shifts.map(s => <option key={s} value={s}>Shift {s}</option>)}</select></div>
              <div className="control-group"><label>PC Mark Code</label><input type="text" value={accurateIn.pc} onChange={e => setAccurateIn({...accurateIn, pc: e.target.value})} /></div>
              <div className="control-group"><label>Material Source</label><select value={accurateIn.materialInFrom} onChange={e => setAccurateIn({...accurateIn, materialInFrom: e.target.value})}><option value="Channel">Channel</option><option value="Rework">Rework</option></select></div>
              <div className="control-group"><label>Qty Received</label><input type="number" value={accurateIn.qtyIn} onChange={e => setAccurateIn({...accurateIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Accurate', 'IN')}>{editingId ? "Update Record" : "Submit Entry"}</button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Log Outbound Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={accurateOut.mo} onChange={e => setAccurateOut({...accurateOut, mo: e.target.value})} placeholder="e.g. MO100234" /></div>
              
              <div className="control-group">
                <label>Variant Model</label>
                <input 
                  type="text" list="acc-out-variants" value={accurateOut.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(accurateOut.mo).find(v => v.type === val);
                    setAccurateOut({...accurateOut, type: val, qtySent: match ? match.qty : accurateOut.qtySent});
                  }} 
                  placeholder="Type to view variants..."
                />
                <datalist id="acc-out-variants">
                  {getVariantsForMo(accurateOut.mo).map((v, i) => <option key={i} value={v.type}>{`Target Qty: ${v.qty}`}</option>)}
                </datalist>
              </div>

              <div className="control-group"><label>Out Date</label><input type="date" value={accurateOut.outDate} onChange={e => setAccurateOut({...accurateOut, outDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift Out</label><select value={accurateOut.shiftOut} onChange={e => setAccurateOut({...accurateOut, shiftOut: e.target.value})}>{shifts.map(s => <option key={s} value={s}>Shift {s}</option>)}</select></div>
              <div className="control-group"><label>Next Destination</label><select value={accurateOut.nextStation} onChange={e => setAccurateOut({...accurateOut, nextStation: e.target.value})}><option value="Packaging">Packaging</option><option value="FPS">FPS</option><option value="Rework">Rework</option><option value="Scrap">Scrap</option></select></div>
              <div className="control-group"><label>Qty Dispatched</label><input type="number" value={accurateOut.qtySent} onChange={e => setAccurateOut({...accurateOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Accurate', 'OUT')}>{editingId ? "Update Record" : "Submit Entry"}</button>
            </div>
          </div>

          <div className="history-table-section">
            <h3>Accurate Station Transaction History Log</h3>
            <table className="log-table">
              <thead><tr><th>Type</th><th>MO</th><th>Variant</th><th>Date</th><th>Shift</th><th>Source/Dest</th><th>Qty</th><th>Actions</th></tr></thead>
              <tbody>
                {accurateHistory.map((item) => (
                  <tr key={item.id} className={item.action === 'IN' ? 'row-inbound' : 'row-outbound'}>
                    <td><span className={`badge ${item.action.toLowerCase()}`}>{item.action}</span></td>
                    <td><strong>{item.mo}</strong></td><td>{item.type}</td><td>{item.inDate || item.outDate}</td><td>{item.shiftIn || item.shiftOut}</td>
                    <td>{item.materialInFrom || item.nextStation}</td><td>{Number(item.qtyIn || item.qtySent).toLocaleString()}</td>
                    <td>
                      <button className="edit-mini-btn" onClick={() => handleEditInit(item, 'Accurate')}>✏️</button>
                      <button className="delete-mini-btn" onClick={() => handleDeleteEntry(item.id, 'Accurate')}>❌</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* CPS SECTON */}
      {activeDept === 'CPS' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>CPS - Log Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={cpsIn.mo} onChange={e => setCpsIn({...cpsIn, mo: e.target.value})} /></div>
              <div className="control-group">
                <label>Variant Type</label>
                <input 
                  type="text" list="cps-in-variants" value={cpsIn.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(cpsIn.mo).find(v => v.type === val);
                    setCpsIn({...cpsIn, type: val, qtyIn: match ? match.qty : cpsIn.qtyIn});
                  }} 
                />
                <datalist id="cps-in-variants">{getVariantsForMo(cpsIn.mo).map((v, i) => <option key={i} value={v.type} />)}</datalist>
              </div>
              <div className="control-group"><label>Item Profile</label><select value={cpsIn.item} onChange={e => setCpsIn({...cpsIn, item: e.target.value})}><option value="Seal">Seal</option><option value="Shield">Shield</option></select></div>
              <div className="control-group"><label>In Date</label><input type="date" value={cpsIn.inDate} onChange={e => setCpsIn({...cpsIn, inDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift</label><select value={cpsIn.shiftIn} onChange={e => setCpsIn({...cpsIn, shiftIn: e.target.value})}>{shifts.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="control-group"><label>RC No</label><input type="text" value={cpsIn.rcNo} onChange={e => setCpsIn({...cpsIn, rcNo: e.target.value})} /></div>
              <div className="control-group"><label>Source Channel</label><select value={cpsIn.channel} onChange={e => setCpsIn({...cpsIn, channel: e.target.value})}>{channels.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
              <div className="control-group"><label>Quantity</label><input type="number" value={cpsIn.qtyIn} onChange={e => setCpsIn({...cpsIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('CPS', 'IN')}>Submit Entry</button>
            </div>

            <div className="operation-card container-outbound">
              <h3>CPS - Log Dispatch (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={cpsOut.mo} onChange={e => setCpsOut({...cpsOut, mo: e.target.value})} /></div>
              <div className="control-group">
                <label>Variant Type</label>
                <input 
                  type="text" list="cps-out-variants" value={cpsOut.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(cpsOut.mo).find(v => v.type === val);
                    setCpsOut({...cpsOut, type: val, qtySent: match ? match.qty : cpsOut.qtySent});
                  }} 
                />
                <datalist id="cps-out-variants">{getVariantsForMo(cpsOut.mo).map((v, i) => <option key={i} value={v.type} />)}</datalist>
              </div>
              <div className="control-group"><label>Out Date</label><input type="date" value={cpsOut.outDate} onChange={e => setCpsOut({...cpsOut, outDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift Out</label><select value={cpsOut.shiftOut} onChange={e => setCpsOut({...cpsOut, shiftOut: e.target.value})}>{shifts.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="control-group"><label>Next Target</label><select value={cpsOut.nextStation} onChange={e => setCpsOut({...cpsOut, nextStation: e.target.value})}><option value="Packaging">Packaging</option><option value="Rework">Rework</option></select></div>
              <div className="control-group"><label>Dispatch Qty</label><input type="number" value={cpsOut.qtySent} onChange={e => setCpsOut({...cpsOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('CPS', 'OUT')}>Submit Entry</button>
            </div>
          </div>

          <div className="history-table-section">
            <h3>CPS Activity Logs</h3>
            <table className="log-table">
              <thead><tr><th>Type</th><th>MO</th><th>Variant</th><th>Item</th><th>Date</th><th>Channel</th><th>Qty</th><th>Actions</th></tr></thead>
              <tbody>
                {cpsHistory.map((item) => (
                  <tr key={item.id} className={item.action === 'IN' ? 'row-inbound' : 'row-outbound'}>
                    <td><span className={`badge ${item.action.toLowerCase()}`}>{item.action}</span></td>
                    <td><strong>{item.mo}</strong></td><td>{item.type}</td><td>{item.item || '-'}</td><td>{item.inDate || item.outDate}</td><td>{item.channel || '-'}</td><td>{item.qtyIn || item.qtySent}</td>
                    <td>
                      <button className="edit-mini-btn" onClick={() => handleEditInit(item, 'CPS')}>✏️</button>
                      <button className="delete-mini-btn" onClick={() => handleDeleteEntry(item.id, 'CPS')}>❌</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* REWORK SECTION */}
      {activeDept === 'Rework' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>Rework - Log Receipt (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={reworkIn.mo} onChange={e => setReworkIn({...reworkIn, mo: e.target.value})} /></div>
              <div className="control-group">
                <label>Variant Type</label>
                <input 
                  type="text" list="rw-in-variants" value={reworkIn.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(reworkIn.mo).find(v => v.type === val);
                    setReworkIn({...reworkIn, type: val, qtyIn: match ? match.qty : reworkIn.qtyIn});
                  }} 
                />
                <datalist id="rw-in-variants">{getVariantsForMo(reworkIn.mo).map((v, i) => <option key={i} value={v.type} />)}</datalist>
              </div>
              <div className="control-group"><label>In Date</label><input type="date" value={reworkIn.inDate} onChange={e => setReworkIn({...reworkIn, inDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift</label><select value={reworkIn.shiftIn} onChange={e => setReworkIn({...reworkIn, shiftIn: e.target.value})}>{shifts.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="control-group"><label>Channel Source</label><select value={reworkIn.channel} onChange={e => setReworkIn({...reworkIn, channel: e.target.value})}>{channels.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
              <div className="control-group"><label>Activity</label><select value={reworkIn.reworkActivity} onChange={e => setReworkIn({...reworkIn, reworkActivity: e.target.value})}>{reworkActivities.map(a => <option key={a} value={a}>{a}</option>)}</select></div>
              <div className="control-group"><label>Line Segment</label><select value={reworkIn.lineSegment} onChange={e => setReworkIn({...reworkIn, lineSegment: e.target.value})}>{lineTypes.map(l => <option key={l} value={l}>{l}</option>)}</select></div>
              <div className="control-group"><label>Quantity</label><input type="number" value={reworkIn.qtyIn} onChange={e => setReworkIn({...reworkIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Rework', 'IN')}>Log Entry</button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Rework - Log Release (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={reworkOut.mo} onChange={e => setReworkOut({...reworkOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={reworkOut.outDate} onChange={e => setReworkOut({...reworkOut, outDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift Out</label><select value={reworkOut.shiftOut} onChange={e => setReworkOut({...reworkOut, shiftOut: e.target.value})}>{shifts.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="control-group"><label>Target Routing</label><select value={reworkOut.nextStation} onChange={e => setReworkOut({...reworkOut, nextStation: e.target.value})}><option value="Channel">Channel Loop</option><option value="Accurate Assembly">Accurate Assembly</option><option value="Scrap Yard">Scrap Yard</option></select></div>
              <div className="control-group"><label>Operator Code</label><input type="text" value={reworkOut.operator} onChange={e => setReworkOut({...reworkOut, operator: e.target.value})} /></div>
              <div className="control-group"><label>Remarks</label><input type="text" value={reworkOut.remark} onChange={e => setReworkOut({...reworkOut, remark: e.target.value})} /></div>
              <div className="control-group"><label>Released Qty</label><input type="number" value={reworkOut.qtySent} onChange={e => setReworkOut({...reworkOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Rework', 'OUT')}>Log Entry</button>
            </div>
          </div>

          <div className="history-table-section">
            <h3>Rework Cell Ledger Execution History</h3>
            <table className="log-table">
              <thead><tr><th>Type</th><th>MO</th><th>Date</th><th>Activity</th><th>Line</th><th>Qty</th><th>Actions</th></tr></thead>
              <tbody>
                {reworkHistory.map((item) => (
                  <tr key={item.id} className={item.action === 'IN' ? 'row-inbound' : 'row-outbound'}>
                    <td><span className={`badge ${item.action.toLowerCase()}`}>{item.action}</span></td>
                    <td><strong>{item.mo}</strong></td><td>{item.inDate || item.outDate}</td><td>{item.reworkActivity || 'Release Drop'}</td><td>{item.lineSegment || '-'}</td><td>{item.qtyIn || item.qtySent}</td>
                    <td>
                      <button className="edit-mini-btn" onClick={() => handleEditInit(item, 'Rework')}>✏️</button>
                      <button className="delete-mini-btn" onClick={() => handleDeleteEntry(item.id, 'Rework')}>❌</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VIBRATION DISMANTLING SECTION */}
      {activeDept === 'Vibration Dismantling' && (
        <div className="split-layout-container">
          <div className="forms-grid-split">
            <div className="operation-card container-inbound">
              <h3>Vibration - Inbound (IN)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={vibrationIn.mo} onChange={e => setVibrationIn({...vibrationIn, mo: e.target.value})} /></div>
              <div className="control-group">
                <label>Variant Type</label>
                <input 
                  type="text" list="vib-in-variants" value={vibrationIn.type} 
                  onChange={e => {
                    const val = e.target.value;
                    const match = getVariantsForMo(vibrationIn.mo).find(v => v.type === val);
                    setVibrationIn({...vibrationIn, type: val, qtyIn: match ? match.qty : vibrationIn.qtyIn});
                  }} 
                />
                <datalist id="vib-in-variants">{getVariantsForMo(vibrationIn.mo).map((v, i) => <option key={i} value={v.type} />)}</datalist>
              </div>
              <div className="control-group"><label>In Date</label><input type="date" value={vibrationIn.inDate} onChange={e => setVibrationIn({...vibrationIn, inDate: e.target.value})} /></div>
              <div className="control-group"><label>Shift</label><select value={vibrationIn.shiftIn} onChange={e => setVibrationIn({...vibrationIn, shiftIn: e.target.value})}>{shifts.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="control-group"><label>Reason</label><select value={vibrationIn.reason} onChange={e => setVibrationIn({...vibrationIn, reason: e.target.value})}>{vibrationReasons.map(r => <option key={r} value={r}>{r}</option>)}</select></div>
              <div className="control-group"><label>Activity</label><select value={vibrationIn.activity} onChange={e => setVibrationIn({...vibrationIn, activity: e.target.value})}>{dismantlingActivities.map(a => <option key={a} value={a}>{a}</option>)}</select></div>
              <div className="control-group"><label>Qty Count</label><input type="number" value={vibrationIn.qtyIn} onChange={e => setVibrationIn({...vibrationIn, qtyIn: e.target.value})} /></div>
              <button className="submit-btn btn-in" onClick={() => handleLogTransaction('Vibration', 'IN')}>Log Input</button>
            </div>

            <div className="operation-card container-outbound">
              <h3>Vibration - Clearance (OUT)</h3>
              <div className="control-group"><label>MO Number</label><input type="text" value={vibrationOut.mo} onChange={e => setVibrationOut({...vibrationOut, mo: e.target.value})} /></div>
              <div className="control-group"><label>Out Date</label><input type="date" value={vibrationOut.outDate} onChange={e => setVibrationOut({...vibrationOut, outDate: e.target.value})} /></div>
              <div className="control-group"><label>Ring Type</label><select value={vibrationOut.ringType} onChange={e => setVibrationOut({...vibrationOut, ringType: e.target.value})}><option value="IR">Inner Ring (IR)</option><option value="OR">Outer Ring (OR)</option><option value="Both">Both Rings</option></select></div>
              <div className="control-group"><label>Ball Scrap Loss</label><input type="number" value={vibrationOut.ballScrap} onChange={e => setVibrationOut({...vibrationOut, ballScrap: e.target.value})} /></div>
              <div className="control-group"><label>Cage/Seal Scrap</label><input type="number" value={vibrationOut.cageSealScrap} onChange={e => setVibrationOut({...vibrationOut, cageSealScrap: e.target.value})} /></div>
              <div className="control-group"><label>Operator</label><input type="text" value={vibrationOut.operator} onChange={e => setVibrationOut({...vibrationOut, operator: e.target.value})} /></div>
              <div className="control-group"><label>Yield Clearance Qty</label><input type="number" value={vibrationOut.qtySent} onChange={e => setVibrationOut({...vibrationOut, qtySent: e.target.value})} /></div>
              <button className="submit-btn btn-out" onClick={() => handleLogTransaction('Vibration', 'OUT')}>Log Output</button>
            </div>
          </div>

          <div className="history-table-section">
            <h3>Vibration Dismantling Operation Logs</h3>
            <table className="log-table">
              <thead><tr><th>Type</th><th>MO</th><th>Date</th><th>Reason/Ring</th><th>Scrap (B/C)</th><th>Qty Passed</th><th>Actions</th></tr></thead>
              <tbody>
                {vibrationHistory.map((item) => (
                  <tr key={item.id} className={item.action === 'IN' ? 'row-inbound' : 'row-outbound'}>
                    <td><span className={`badge ${item.action.toLowerCase()}`}>{item.action}</span></td>
                    <td><strong>{item.mo}</strong></td><td>{item.inDate || item.outDate}</td>
                    <td>{item.action === 'IN' ? item.reason : `Ring: ${item.ringType}`}</td>
                    <td>{item.action === 'IN' ? '-' : `${item.ballScrap} / ${item.cageSealScrap}`}</td>
                    <td>{item.qtyIn || item.qtySent}</td>
                    <td>
                      <button className="edit-mini-btn" onClick={() => handleEditInit(item, 'Vibration')}>✏️</button>
                      <button className="delete-mini-btn" onClick={() => handleDeleteEntry(item.id, 'Vibration')}>❌</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* OPERATIONAL LIFE ROUTE SUMMARY DASHBOARD */}
      {activeDept === 'MO Flow Summary' && (
        <div className="table-wrapper" style={{ padding: '20px' }}>
          <h3 style={{ borderBottom: '2px solid #cbd5e1', paddingBottom: '10px', color: '#334155' }}>Cross-Station Verification Log</h3>
          <div className="controls-row" style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', marginBottom: '25px' }}>
            <div className="control-group" style={{ margin: 0, width: '280px' }}>
              <label style={{fontWeight: 600}}>Target MO Audit Route</label>
              <input type="text" value={moSearch} onChange={e => setMoSearch(e.target.value)} placeholder="Type complete MO code..." />
            </div>
            <button className="submit-btn" style={{ padding: '10px 24px', borderRadius: '4px', background: '#0284c7' }} onClick={handleTraceRoute}>Trace Local Ledger</button>
          </div>

          {moSummary && (
            <div style={{ marginTop: '20px' }}>
              <div className="excel-master-tracker-card" style={{ background: '#f8fafc', padding: '20px', borderRadius: '6px', marginBottom: '20px', border: '1px solid #cbd5e1' }}>
                <h4 style={{ margin: '0 0 12px 0', color: '#0369a1' }}>Live Master Sheet Definition Links</h4>
                <div style={{ display: 'flex', gap: '40px', flexWrap: 'wrap', fontSize: '14px' }}>
                  <p style={{ margin: 0 }}><strong>MO Identified:</strong> {moSummary.mo.toUpperCase()}</p>
                  <p style={{ margin: 0 }}><strong>Variants (Family Type):</strong> <span className="text-primary" style={{fontWeight: 600}}>{moSummary.variant}</span></p>
                  <p style={{ margin: 0 }}><strong>Total Base Demand Qty:</strong> <span style={{ fontWeight: 'bold', color: '#16a34a' }}>{moSummary.cumulativeProduction.toLocaleString()}</span></p>
                </div>
              </div>

              <table className="log-table">
                <thead>
                  <tr><th>Origin Section</th><th>Action</th><th>Execution Timestamp ID</th><th>Item Variant Details</th><th>Processed Volume</th></tr>
                </thead>
                <tbody>
                  {moSummary.ledger.map((row, idx) => (
                    <tr key={idx} style={{background: row.action === 'IN' ? '#f0fdf4' : '#fff7ed'}}>
                      <td><strong>{row.dept}</strong></td>
                      <td><span className={`badge ${row.action.toLowerCase()}`}>{row.action}</span></td>
                      <td>{new Date(row.id).toLocaleString()}</td>
                      <td>{row.type || 'Standard Link Profile'}</td>
                      <td><strong>{Number(row.qtyIn || row.qtySent).toLocaleString()}</strong></td>
                    </tr>
                  ))}
                  {moSummary.ledger.length === 0 && (
                    <tr><td colSpan="5" style={{textAlign: 'center', padding: '20px', color: '#64748b'}}>No localized matching transactions logged yet for this MO family.</td></tr>
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

// Afterchannel.js
import React, { useState } from 'react';
import './Afterchannel.css';

const Afterchannel = () => {
  const [activeDept, setActiveDept] = useState('Accurate');

  // Shared state for common options
  const shifts = ["1", "2", "3"];
  const lineTypes = ["DGBB", "TRB"];
  const channels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH07", "CH08", "CH11", "CH12", "CH13", "T1", "T2"];
  
  // 1. Accurate State
  const [accurateData, setAccurateData] = useState({
    mo: '', type: '', inDate: '', shiftIn: '1', pc: '', materialInFrom: 'Channel',
    qtyIn: '', nextStation: 'Packaging', qtySent: '', outDate: '', shiftOut: '1'
  });

  // 2. CPS State
  const [cpsData, setCpsData] = useState({
    mo: '', type: '', item: 'Seal', inDate: '', shiftIn: '1', rcNo: '', materialInFrom: 'Channel',
    channel: 'CH01', qtyIn: '', nextStation: 'Packaging', qtySent: '', outDate: '', shiftOut: '1'
  });

  // 3. Rework State
  const [reworkData, setReworkData] = useState({
    mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', materialInFrom: 'Channel',
    qtyIn: '', reworkActivity: 'Visual', nextStation: 'Channel', qtySent: '',
    outDate: '', shiftOut: '1', operator: '', remark: '', lineSegment: 'DGBB'
  });

  // 4. Vibration Dismantling State
  const [vibrationData, setVibrationData] = useState({
    mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', reason: 'D4', materialInFrom: 'Channel',
    qtyIn: '', activity: 'Ball Remove', ballScrap: '', cageSealScrap: '', ringType: 'IR',
    nextStation: 'Channel', qtySent: '', outDate: '', shiftOut: '1', operator: '', remark: '', lineSegment: 'DGBB'
  });

  // History & Summary States
  const [recentEntries, setRecentEntries] = useState([]);
  const [moSearch, setMoSearch] = useState('');
  const [moSummary, setMoSummary] = useState(null);

  // Handlers for input changes
  const handleAccurate = (field, val) => setAccurateData(prev => ({ ...prev, [field]: val }));
  const handleCps = (field, val) => setCpsData(prev => ({ ...prev, [field]: val }));
  const handleRework = (field, val) => setReworkData(prev => ({ ...prev, [field]: val }));
  const handleVibration = (field, val) => setVibrationData(prev => ({ ...prev, [field]: val }));

  const handleSubmit = () => {
    let currentData = {};
    if (activeDept === 'Accurate') currentData = accurateData;
    if (activeDept === 'CPS') currentData = cpsData;
    if (activeDept === 'Rework') currentData = reworkData;
    if (activeDept === 'Vibration Dismantling') currentData = vibrationData;

    // Create entry for the local table
    const newEntry = {
      id: Date.now(),
      dept: activeDept,
      mo: currentData.mo,
      type: currentData.type,
      date: currentData.inDate,
      from: currentData.materialInFrom,
      qtyIn: currentData.qtyIn,
      to: currentData.nextStation,
      qtySent: currentData.qtySent
    };

    setRecentEntries([newEntry, ...recentEntries]);
    alert(`${activeDept} Entry Logged. Ready to connect to backend.`);
  };

  const handleGenerateSummary = () => {
    if (!moSearch) return;
    
    // Simulate initial master pull
    const mockInitialProduction = 1000; 
    const moLedger = recentEntries.filter(entry => entry.mo === moSearch);

    setMoSummary({
      mo: moSearch,
      initialQty: mockInitialProduction,
      ledger: moLedger
    });
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Afterchannel Operations Desk</h2>
        <p style={{color: '#64748b', margin: 0, fontSize: '14px'}}>Track material flow post-channel generation.</p>
      </div>

      {/* Department Navigation Tabs */}
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
          MO FLOW SUMMARY TAB
      ========================================== */}
      {activeDept === 'MO Flow Summary' ? (
        <div className="table-wrapper" style={{padding: '20px'}}>
          <h3 style={{borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>Overall Flow Data by MO</h3>
          <div className="controls-row" style={{marginBottom: '20px'}}>
            <div className="control-group" style={{maxWidth: '250px'}}>
              <label>Target MO Number</label>
              <input type="text" value={moSearch} onChange={e => setMoSearch(e.target.value)} placeholder="Enter MO..." />
            </div>
            <button className="submit-btn" style={{marginTop: '22px'}} onClick={handleGenerateSummary}>Trace Route</button>
          </div>

          {moSummary && (
            <div style={{marginTop: '20px'}}>
              <div style={{background: '#eff6ff', padding: '15px', borderRadius: '6px', border: '1px solid #bfdbfe', marginBottom: '20px'}}>
                <h4 style={{margin: '0 0 10px 0', color: '#1d4ed8'}}>Master Initialization Data</h4>
                <p style={{margin: 0, fontSize: '14px'}}><strong>MO:</strong> {moSummary.mo}</p>
                <p style={{margin: '5px 0 0 0', fontSize: '14px'}}><strong>Total Qty from Excel Master (Cumulative):</strong> <span style={{color: '#059669', fontWeight: 'bold'}}>{moSummary.initialQty}</span></p>
              </div>

              <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '14px'}}>
                <thead>
                  <tr style={{background: '#f1f5f9', textAlign: 'left'}}>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Step</th>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Department</th>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Source (From)</th>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Qty Received</th>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Destination (To)</th>
                    <th style={{padding: '10px', borderBottom: '2px solid #cbd5e1'}}>Qty Dispatched</th>
                  </tr>
                </thead>
                <tbody>
                  {moSummary.ledger.length === 0 ? (
                    <tr><td colSpan="6" style={{textAlign: 'center', padding: '20px', color: '#64748b'}}>No movements recorded for this MO yet.</td></tr>
                  ) : (
                    moSummary.ledger.map((log, idx) => (
                      <tr key={log.id} style={{borderBottom: '1px solid #e2e8f0'}}>
                        <td style={{padding: '10px'}}>{idx + 1}</td>
                        <td style={{padding: '10px', fontWeight: 'bold', color: '#334155'}}>{log.dept}</td>
                        <td style={{padding: '10px'}}>{log.from}</td>
                        <td style={{padding: '10px', color: '#2563eb'}}>{log.qtyIn}</td>
                        <td style={{padding: '10px'}}>{log.to}</td>
                        <td style={{padding: '10px', color: '#059669'}}>{log.qtySent}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* ==========================================
            DATA ENTRY FORMS 
        ========================================== */
        <div className="table-wrapper" style={{padding: '20px', marginBottom: '20px'}}>
          
          {/* 1. ACCURATE DEPARTMENT */}
          {activeDept === 'Accurate' && (
            <div>
              <h3 style={{borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>Accurate Inspection Entry</h3>
              <div className="controls-row">
                <div className="control-group"><label>MO</label><input type="text" value={accurateData.mo} onChange={e=>handleAccurate('mo', e.target.value)}/></div>
                <div className="control-group"><label>Type</label><input type="text" value={accurateData.type} onChange={e=>handleAccurate('type', e.target.value)}/></div>
                <div className="control-group"><label>In Date</label><input type="date" value={accurateData.inDate} onChange={e=>handleAccurate('inDate', e.target.value)}/></div>
                <div className="control-group">
                  <label>Shift In</label>
                  <select value={accurateData.shiftIn} onChange={e=>handleAccurate('shiftIn', e.target.value)}>
                    {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="control-group"><label>PC</label><input type="text" value={accurateData.pc} onChange={e=>handleAccurate('pc', e.target.value)}/></div>
              </div>
              <div className="controls-row" style={{marginTop: '20px'}}>
                <div className="control-group">
                  <label>Material In From</label>
                  <select value={accurateData.materialInFrom} onChange={e=>handleAccurate('materialInFrom', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="Rework">Rework</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty In</label><input type="number" value={accurateData.qtyIn} onChange={e=>handleAccurate('qtyIn', e.target.value)}/></div>
                <div className="control-group">
                  <label>Next Station</label>
                  <select value={accurateData.nextStation} onChange={e=>handleAccurate('nextStation', e.target.value)}>
                    <option value="Packaging">Packaging</option>
                    <option value="FPS">FPS</option>
                    <option value="Rework">Rework</option>
                    <option value="Scrap">Scrap</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty Sent</label><input type="number" value={accurateData.qtySent} onChange={e=>handleAccurate('qtySent', e.target.value)}/></div>
                <div className="control-group"><label>Out Date</label><input type="date" value={accurateData.outDate} onChange={e=>handleAccurate('outDate', e.target.value)}/></div>
                <div className="control-group">
                  <label>Shift Out</label>
                  <select value={accurateData.shiftOut} onChange={e=>handleAccurate('shiftOut', e.target.value)}>
                    {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* 2. CPS DEPARTMENT */}
          {activeDept === 'CPS' && (
            <div>
              <h3 style={{borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>CPS Entry</h3>
              <div className="controls-row">
                <div className="control-group"><label>MO</label><input type="text" value={cpsData.mo} onChange={e=>handleCps('mo', e.target.value)}/></div>
                <div className="control-group"><label>Type</label><input type="text" value={cpsData.type} onChange={e=>handleCps('type', e.target.value)}/></div>
                <div className="control-group">
                  <label>Item</label>
                  <select value={cpsData.item} onChange={e=>handleCps('item', e.target.value)}>
                    <option value="Seal">Seal</option>
                    <option value="Shield">Shield</option>
                    <option value="OM Black">OM Black</option>
                    <option value="IM White">IM White</option>
                  </select>
                </div>
                <div className="control-group"><label>In Date</label><input type="date" value={cpsData.inDate} onChange={e=>handleCps('inDate', e.target.value)}/></div>
                <div className="control-group">
                  <label>Shift In</label>
                  <select value={cpsData.shiftIn} onChange={e=>handleCps('shiftIn', e.target.value)}>
                    {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="control-group"><label>RC No</label><input type="text" value={cpsData.rcNo} onChange={e=>handleCps('rcNo', e.target.value)}/></div>
              </div>
              <div className="controls-row" style={{marginTop: '20px'}}>
                <div className="control-group">
                  <label>Material In From</label>
                  <select value={cpsData.materialInFrom} onChange={e=>handleCps('materialInFrom', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="Rework">Rework</option>
                    <option value="Dismantling">Dismantling</option>
                    <option value="Accurate">Accurate</option>
                  </select>
                </div>
                <div className="control-group">
                  <label>Channel</label>
                  <select value={cpsData.channel} onChange={e=>handleCps('channel', e.target.value)}>
                    {channels.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="control-group"><label>Qty In</label><input type="number" value={cpsData.qtyIn} onChange={e=>handleCps('qtyIn', e.target.value)}/></div>
                <div className="control-group">
                  <label>Next Station</label>
                  <select value={cpsData.nextStation} onChange={e=>handleCps('nextStation', e.target.value)}>
                    <option value="Packaging">Packaging</option>
                    <option value="FPS">FPS</option>
                    <option value="Rework">Rework</option>
                    <option value="Scrap">Scrap</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty Sent</label><input type="number" value={cpsData.qtySent} onChange={e=>handleCps('qtySent', e.target.value)}/></div>
                <div className="control-group"><label>Out Date</label><input type="date" value={cpsData.outDate} onChange={e=>handleCps('outDate', e.target.value)}/></div>
              </div>
            </div>
          )}

          {/* 3. REWORK DEPARTMENT */}
          {activeDept === 'Rework' && (
            <div>
              <div style={{display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>
                <h3 style={{margin: 0}}>Rework Entry</h3>
                <select style={{padding: '5px', borderRadius: '4px', fontWeight: 'bold'}} value={reworkData.lineSegment} onChange={e=>handleRework('lineSegment', e.target.value)}>
                  {lineTypes.map(t => <option key={t} value={t}>{t} Line</option>)}
                </select>
              </div>
              <div className="controls-row" style={{marginTop: '15px'}}>
                <div className="control-group"><label>MO</label><input type="text" value={reworkData.mo} onChange={e=>handleRework('mo', e.target.value)}/></div>
                <div className="control-group"><label>In Date</label><input type="date" value={reworkData.inDate} onChange={e=>handleRework('inDate', e.target.value)}/></div>
                <div className="control-group">
                  <label>Shift In</label>
                  <select value={reworkData.shiftIn} onChange={e=>handleRework('shiftIn', e.target.value)}>
                    {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="control-group">
                  <label>Channel</label>
                  <select value={reworkData.channel} onChange={e=>handleRework('channel', e.target.value)}>
                    {channels.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="control-group"><label>Type</label><input type="text" value={reworkData.type} onChange={e=>handleRework('type', e.target.value)}/></div>
                <div className="control-group">
                  <label>Material In From</label>
                  <select value={reworkData.materialInFrom} onChange={e=>handleRework('materialInFrom', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="Accurate">Accurate</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty In</label><input type="number" value={reworkData.qtyIn} onChange={e=>handleRework('qtyIn', e.target.value)}/></div>
              </div>
              <div className="controls-row" style={{marginTop: '20px'}}>
                <div className="control-group">
                  <label>Rework Activity</label>
                  <select value={reworkData.reworkActivity} onChange={e=>handleRework('reworkActivity', e.target.value)}>
                    <option value="Cartons Removal">Cartons Removal</option>
                    <option value="OD Polish">OD Polish</option>
                    <option value="Shield Removal">Shield Removal</option>
                    <option value="Visual">Visual</option>
                  </select>
                </div>
                <div className="control-group">
                  <label>Next Station</label>
                  <select value={reworkData.nextStation} onChange={e=>handleRework('nextStation', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="Accurate">Accurate</option>
                    <option value="CPS">CPS</option>
                    <option value="Dismantling">Dismantling</option>
                    <option value="Scrap">Scrap</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty Sent</label><input type="number" value={reworkData.qtySent} onChange={e=>handleRework('qtySent', e.target.value)}/></div>
                <div className="control-group"><label>Out Date</label><input type="date" value={reworkData.outDate} onChange={e=>handleRework('outDate', e.target.value)}/></div>
                <div className="control-group"><label>Operator</label><input type="text" value={reworkData.operator} onChange={e=>handleRework('operator', e.target.value)}/></div>
                <div className="control-group"><label>Remark</label><input type="text" value={reworkData.remark} onChange={e=>handleRework('remark', e.target.value)}/></div>
              </div>
            </div>
          )}

          {/* 4. VIBRATION DISMANTLING DEPARTMENT */}
          {activeDept === 'Vibration Dismantling' && (
            <div>
              <div style={{display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>
                <h3 style={{margin: 0}}>Vibration Dismantling Entry</h3>
                <select style={{padding: '5px', borderRadius: '4px', fontWeight: 'bold'}} value={vibrationData.lineSegment} onChange={e=>handleVibration('lineSegment', e.target.value)}>
                  {lineTypes.map(t => <option key={t} value={t}>{t} Line</option>)}
                </select>
              </div>
              <div className="controls-row" style={{marginTop: '15px'}}>
                <div className="control-group"><label>MO</label><input type="text" value={vibrationData.mo} onChange={e=>handleVibration('mo', e.target.value)}/></div>
                <div className="control-group"><label>In Date</label><input type="date" value={vibrationData.inDate} onChange={e=>handleVibration('inDate', e.target.value)}/></div>
                <div className="control-group">
                  <label>Shift In</label>
                  <select value={vibrationData.shiftIn} onChange={e=>handleVibration('shiftIn', e.target.value)}>
                    {shifts.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="control-group">
                  <label>Channel</label>
                  <select value={vibrationData.channel} onChange={e=>handleVibration('channel', e.target.value)}>
                    {channels.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="control-group"><label>Type</label><input type="text" value={vibrationData.type} onChange={e=>handleVibration('type', e.target.value)}/></div>
                <div className="control-group">
                  <label>Reason</label>
                  <select value={vibrationData.reason} onChange={e=>handleVibration('reason', e.target.value)}>
                    <option value="D4">D4</option>
                    <option value="OD Mark">OD Mark</option>
                  </select>
                </div>
                <div className="control-group">
                  <label>Material In From</label>
                  <select value={vibrationData.materialInFrom} onChange={e=>handleVibration('materialInFrom', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="Rework">Rework</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty In</label><input type="number" value={vibrationData.qtyIn} onChange={e=>handleVibration('qtyIn', e.target.value)}/></div>
              </div>
              
              <div className="controls-row" style={{marginTop: '20px'}}>
                <div className="control-group">
                  <label>Activity</label>
                  <select value={vibrationData.activity} onChange={e=>handleVibration('activity', e.target.value)}>
                    <option value="Ball Remove">Ball Remove</option>
                    <option value="Rivet Press">Rivet Press</option>
                  </select>
                </div>
                <div className="control-group"><label>Ball Scrap (Qty)</label><input type="number" value={vibrationData.ballScrap} onChange={e=>handleVibration('ballScrap', e.target.value)}/></div>
                <div className="control-group"><label>Cage/Seal Scrap</label><input type="number" value={vibrationData.cageSealScrap} onChange={e=>handleVibration('cageSealScrap', e.target.value)}/></div>
                <div className="control-group">
                  <label>Ring Type</label>
                  <select value={vibrationData.ringType} onChange={e=>handleVibration('ringType', e.target.value)}>
                    <option value="IR">IR</option>
                    <option value="OR">OR</option>
                  </select>
                </div>
                <div className="control-group">
                  <label>Next Station</label>
                  <select value={vibrationData.nextStation} onChange={e=>handleVibration('nextStation', e.target.value)}>
                    <option value="Channel">Channel</option>
                    <option value="CPS">CPS</option>
                    <option value="Scrap">Scrap</option>
                  </select>
                </div>
                <div className="control-group"><label>Qty Sent</label><input type="number" value={vibrationData.qtySent} onChange={e=>handleVibration('qtySent', e.target.value)}/></div>
                <div className="control-group"><label>Out Date</label><input type="date" value={vibrationData.outDate} onChange={e=>handleVibration('outDate', e.target.value)}/></div>
              </div>
            </div>
          )}

          {/* Universal Action Row */}
          <div className="action-row" style={{marginTop: '30px', borderTop: '1px solid #e2e8f0', paddingTop: '15px'}}>
            <button className="submit-btn" onClick={handleSubmit}>
              Save {activeDept} Entry
            </button>
          </div>
        </div>
      )}

      {/* ==========================================
          RECENT ENTRIES LIVE TABLE
      ========================================== */}
      {activeDept !== 'MO Flow Summary' && (
        <div className="table-wrapper" style={{padding: '20px'}}>
          <h3 style={{margin: '0 0 15px 0', color: '#1e293b'}}>Recent Session Entries</h3>
          <div style={{overflowX: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'center'}}>
              <thead>
                <tr style={{background: '#f1f5f9', color: '#334155'}}>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Dept</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>MO</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Date</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Source (From)</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Qty In</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Destination (To)</th>
                  <th style={{padding: '10px', border: '1px solid #e2e8f0'}}>Qty Sent</th>
                </tr>
              </thead>
              <tbody>
                {recentEntries.length === 0 ? (
                  <tr><td colSpan="7" style={{padding: '20px', color: '#94a3b8'}}>No entries made in this session yet.</td></tr>
                ) : (
                  recentEntries.map(entry => (
                    <tr key={entry.id}>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0', fontWeight: 'bold'}}>{entry.dept}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0'}}>{entry.mo}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0'}}>{entry.date}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0'}}>{entry.from}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0', color: '#2563eb'}}>{entry.qtyIn}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0'}}>{entry.to}</td>
                      <td style={{padding: '8px', border: '1px solid #e2e8f0', color: '#059669'}}>{entry.qtySent}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
};

export default Afterchannel;

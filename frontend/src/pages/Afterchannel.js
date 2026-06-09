// Afterchannel.js
import React, { useState } from 'react';
import './Afterchannel.css'; 

const Afterchannel = () => {
  const [activeDept, setActiveDept] = useState('Accurate');
  
  // Shared Options
  const shifts = ["1", "2", "3"];
  const lineTypes = ["DGBB", "TRB"];
  const channels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH07", "CH08", "CH11", "CH12", "CH13", "T1", "T2"];

  // Form States
  const [accurateData, setAccurateData] = useState({ mo: '', type: '', inDate: '', shiftIn: '1', pc: '', materialInFrom: 'Channel', qtyIn: '', nextStation: 'Packaging', qtySent: '', outDate: '', shiftOut: '1' });
  const [cpsData, setCpsData] = useState({ mo: '', type: '', item: 'Seal', inDate: '', shiftIn: '1', rcNo: '', materialInFrom: 'Channel', channel: 'CH01', qtyIn: '', nextStation: 'Packaging', qtySent: '', outDate: '', shiftOut: '1' });
  const [reworkData, setReworkData] = useState({ mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', materialInFrom: 'Channel', qtyIn: '', reworkActivity: 'Visual', nextStation: 'Channel', qtySent: '', outDate: '', shiftOut: '1', operator: '', remark: '', lineSegment: 'DGBB' });
  const [vibrationData, setVibrationData] = useState({ mo: '', inDate: '', shiftIn: '1', channel: 'CH01', type: '', reason: 'D4', materialInFrom: 'Channel', qtyIn: '', activity: 'Ball Remove', ballScrap: '', cageSealScrap: '', ringType: 'IR', nextStation: 'Channel', qtySent: '', outDate: '', shiftOut: '1', operator: '', remark: '', lineSegment: 'DGBB' });

  // History & Summary States
  const [recentEntries, setRecentEntries] = useState([]);
  const [moSearch, setMoSearch] = useState('');
  const [moSummary, setMoSummary] = useState(null);

  // Handlers
  const handleAccurate = (field, val) => setAccurateData(prev => ({ ...prev, [field]: val }));
  const handleCps = (field, val) => setCpsData(prev => ({ ...prev, [field]: val }));
  const handleRework = (field, val) => setReworkData(prev => ({ ...prev, [field]: val }));
  const handleVibration = (field, val) => setVibrationData(prev => ({ ...prev, [field]: val }));

  const handleSubmit = () => {
    // Determine which dataset is active
    let currentData = {};
    if (activeDept === 'Accurate') currentData = accurateData;
    if (activeDept === 'CPS') currentData = cpsData;
    if (activeDept === 'Rework') currentData = reworkData;
    if (activeDept === 'Vibration Dismantling') currentData = vibrationData;

    // Create a unified history log object
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

    // Update local table (In production, this happens AFTER successful API post)
    setRecentEntries([newEntry, ...recentEntries]);
    
    // TODO: Add your fetch('/api/afterchannel/...') logic here
    alert(`${activeDept} Entry Logged Temporarily. Attach backend for persistence.`);
  };

  const handleGenerateSummary = async () => {
    if (!moSearch) return;
    
    // Simulate fetching the initial Master Excel Data (e.g., 1000 rings)
    // In production, call your python endpoint reading TRB/DGBB_Master here
    const mockInitialProduction = 1000; 

    // Simulate filtering the database (using our local entries for the mockup)
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
        <p style={{color: '#64748b', margin: 0, fontSize: '14px'}}>Track material flow post-channel generation & Trace MO Lifecycles.</p>
      </div>

      {/* Main Tabs */}
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
          MO FLOW SUMMARY VIEW
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
            DATA ENTRY FORMS (Accurate, CPS, etc.)
        ========================================== */
        <div className="table-wrapper" style={{padding: '20px', marginBottom: '20px'}}>
          
          {/* ... [YOUR EXISTING FORM CODE GOES HERE FOR ACCURATE, CPS, REWORK, VIBRATION] ... */}
          {/* Keep the exact form blocks from the previous code I provided here so it doesn't get cluttered */}
          <h3 style={{borderBottom: '2px solid #e2e8f0', paddingBottom: '10px'}}>{activeDept} Entry Form</h3>
          <div className="controls-row">
              <div className="control-group">
                <label>MO</label>
                <input type="text" onChange={e => {
                  if(activeDept==='Accurate') handleAccurate('mo', e.target.value);
                  if(activeDept==='CPS') handleCps('mo', e.target.value);
                  if(activeDept==='Rework') handleRework('mo', e.target.value);
                  if(activeDept==='Vibration Dismantling') handleVibration('mo', e.target.value);
                }} />
              </div>
              <div className="control-group">
                <label>Qty In</label>
                <input type="number" onChange={e => {
                  if(activeDept==='Accurate') handleAccurate('qtyIn', e.target.value);
                  if(activeDept==='CPS') handleCps('qtyIn', e.target.value);
                  if(activeDept==='Rework') handleRework('qtyIn', e.target.value);
                  if(activeDept==='Vibration Dismantling') handleVibration('qtyIn', e.target.value);
                }} />
              </div>
              <div className="control-group">
                <label>Material In From</label>
                <select onChange={e => {
                  if(activeDept==='Accurate') handleAccurate('materialInFrom', e.target.value);
                  if(activeDept==='CPS') handleCps('materialInFrom', e.target.value);
                  if(activeDept==='Rework') handleRework('materialInFrom', e.target.value);
                  if(activeDept==='Vibration Dismantling') handleVibration('materialInFrom', e.target.value);
                }}>
                  <option value="Channel">Channel</option>
                  <option value="Accurate">Accurate</option>
                  <option value="Rework">Rework</option>
                  <option value="Packaging">Packaging</option>
                </select>
              </div>
              <div className="control-group">
                <label>Next Station (To)</label>
                <select onChange={e => {
                  if(activeDept==='Accurate') handleAccurate('nextStation', e.target.value);
                  if(activeDept==='CPS') handleCps('nextStation', e.target.value);
                  if(activeDept==='Rework') handleRework('nextStation', e.target.value);
                  if(activeDept==='Vibration Dismantling') handleVibration('nextStation', e.target.value);
                }}>
                  <option value="Packaging">Packaging</option>
                  <option value="Channel">Channel</option>
                  <option value="Accurate">Accurate</option>
                  <option value="Rework">Rework</option>
                  <option value="Dismantling">Dismantling</option>
                  <option value="Scrap">Scrap</option>
                  <option value="CPS">CPS</option>
                </select>
              </div>
              <div className="control-group">
                <label>Qty Sent</label>
                <input type="number" onChange={e => {
                  if(activeDept==='Accurate') handleAccurate('qtySent', e.target.value);
                  if(activeDept==='CPS') handleCps('qtySent', e.target.value);
                  if(activeDept==='Rework') handleRework('qtySent', e.target.value);
                  if(activeDept==='Vibration Dismantling') handleVibration('qtySent', e.target.value);
                }} />
              </div>
          </div>

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

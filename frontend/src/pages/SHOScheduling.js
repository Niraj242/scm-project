import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

// VERY IMPORTANT: Change this to your actual Python backend URL to fix the 405 error on Vercel.
// Example: const API_BASE = 'https://your-backend-app.onrender.com';
const API_BASE = ''; 

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer'); 
  
  // Tab 1: Buffer State
  const [sector, setSector] = useState('DGBB');
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  const [tableData, setTableData] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  
  // Tab 2 & 4: Schedule State
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);

  // Tab 3: Summary State
  const [summaryDate, setSummaryDate] = useState(new Date().toISOString().split('T')[0]);
  const [summaryData, setSummaryData] = useState([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  // Fixed Machine List for Availability
  const FIXED_MACHINES = [
    "AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )", 
    "SIMPLICITY FURNACE(1238)", "BIRLEC FURNACE   ( 1158 )", "SHOEI FURNACE    ( 1062 )", 
    "AICHELIN UNITHERM ( 2033 )", "BG_1", "BG_2", "BG_3", "DDS_1", "DDS_2", 
    "CL_1", "CL_2", "CELL_1", "CELL_2"
  ];
  
  const [machineAvailability, setMachineAvailability] = useState(
    FIXED_MACHINES.map(m => ({ id: m, machine: m, enabled: true, off_whole_day: false, start_time: '10:00', end_time: '' }))
  );

  // -- CONSTANTS --
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2']
  };

  const DEFAULT_BLOCKED = {
    DGBB: { 
        OD: { CH01: ['IR'], CH02: ['IR', 'OR'], CH04: ['IR', 'OR'], CH05: ['IR'], CH08: ['IR'], CH11: ['IR'] }, 
        FACE: { CH01: ['IR'], CH02: ['IR', 'OR'], CH04: ['IR', 'OR'] } 
    },
    TRB: { 
        OD: { 'T 1': ['IR'], 'T 2': ['IR'], 'T 3': ['IR'], 'T 4': ['IR'], 'T 5': ['IR'], 'T 6': ['IR'], 'T 7': ['IR'], 'T 8': ['IR', 'OR'], 'T 9': ['IR', 'OR'], 'T10': ['IR'] }, 
        FACE: { 'T 8': ['IR', 'OR'], 'T 9': ['IR', 'OR'] } 
    },
    HUB: { OD: {}, FACE: {} }
  };

  const ROWS = [
    { label: 'CH. BUFFER', key: 'ch_buffer_1', section: 'CH', sectionIndex: 0 },
    { label: 'TYPE', key: 'type_1', section: 'CH', sectionIndex: 1 },
    { label: 'CH. BUFFER', key: 'ch_buffer_2', section: 'CH', sectionIndex: 2 },
    { label: 'NEXT TYPE', key: 'next_type_1', section: 'CH', sectionIndex: 3 },
    { label: 'OD BUFFER', key: 'od_buffer_1', section: 'OD', sectionIndex: 0 },
    { label: 'TYPE', key: 'type_2', section: 'OD', sectionIndex: 1 },
    { label: 'OD BUFFER', key: 'od_buffer_2', section: 'OD', sectionIndex: 2 },
    { label: 'NEXT TYPE', key: 'next_type_2', section: 'OD', sectionIndex: 3 },
    { label: 'FACE BUFFER', key: 'face_buffer_1', section: 'FACE', sectionIndex: 0 },
    { label: 'TYPE', key: 'type_3', section: 'FACE', sectionIndex: 1 },
    { label: 'FACE BUFFER', key: 'face_buffer_2', section: 'FACE', sectionIndex: 2 },
    { label: 'TYPE', key: 'type_4', section: 'FACE', sectionIndex: 3 }
  ];

  useEffect(() => {
    const savedData = localStorage.getItem(`sho_db_${sector}_${bufferDate}`);
    if (savedData) {
      setTableData(JSON.parse(savedData).entries || {});
    } else {
      setTableData({});
    }
  }, [sector, bufferDate]);

  const handleInputChange = (rowKey, col, subCol, value) => {
    setTableData(prev => ({ ...prev, [`${rowKey}_${col}_${subCol}`]: value }));
  };

  const saveBufferData = () => {
    setIsSaving(true);
    localStorage.setItem(`sho_db_${sector}_${bufferDate}`, JSON.stringify({ entries: tableData }));
    setTimeout(() => { setIsSaving(false); alert("Buffer Data Saved successfully."); }, 300);
  };

  const updateMachineConstraint = (id, field, value) => {
    setMachineAvailability(prev => prev.map(c => (c.id === id ? { ...c, [field]: value } : c)));
  };

  const fetchSummaryOnly = async () => {
    setIsLoadingSummary(true);
    try {
      const response = await fetch(`${API_BASE}/api/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sector, date: summaryDate, unit_mode: 'Days', entries: {}, unlocked_blocks: [] })
      });
      const result = await response.json();
      if (response.ok && result.status === 'success') {
        setSummaryData(result.data || []);
      } else {
        alert("Error loading summary: " + result.detail);
      }
    } catch (e) {
      alert("Failed to connect to backend. Verify network or check Vercel API routing.");
    }
    setIsLoadingSummary(false);
  };

  const fetchSchedule = async () => {
    setIsLoadingPlan(true);
    const availabilityMap = {};
    machineAvailability.forEach(c => {
      if (c.machine.trim()) {
        availabilityMap[c.machine.trim()] = {
          enabled: c.enabled,
          off_whole_day: c.off_whole_day,
          start_time: c.start_time,
          end_time: c.end_time
        };
      }
    });

    try {
      const response = await fetch(`${API_BASE}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          sector, 
          date: scheduleDate, 
          unit_mode: unitMode, 
          entries: tableData, 
          unlocked_blocks: [],
          machine_availability: availabilityMap 
        })
      });
      const result = await response.json();
      if (response.ok && result.status === 'success') { 
        setScheduleData(result.data); 
        if (result.data.summary) {
          setSummaryData(result.data.summary);
        }
      } else { 
        alert("Error: " + (result.detail || result.message)); 
      }
    } catch (e) { 
      alert("Failed to connect to backend. If on Vercel, check your API_BASE URL or vercel.json rewrites."); 
    }
    setIsLoadingPlan(false);
  };

  const columns = SECTOR_COLUMNS[sector];
  const totalCols = (columns.length * 2) + 1;
  const isCellBlocked = (section, col, subCol) => DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol);

  return (
    <div className="sho-container">
      {/* NAVIGATION TABS */}
      <div className="tab-buttons" style={{ marginBottom: '15px' }}>
        <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Buffer Entry</button>
        <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Production Schedule</button>
        <button className={activeTab === 'availability' ? 'active' : ''} onClick={() => setActiveTab('availability')}>3. Machine Availability</button>
        <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')}>4. Production Summary</button>
      </div>

      {/* TAB 1: BUFFER ENTRY */}
      {activeTab === 'buffer' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Sector:</label>
              <select value={sector} onChange={(e) => setSector(e.target.value)}>
                <option value="DGBB">DGBB</option>
                <option value="TRB">TRB</option>
                <option value="HUB">HUB</option>
              </select>
            </div>
            <div className="control-group">
              <label>Date:</label>
              <input type="date" value={bufferDate} onChange={(e) => setBufferDate(e.target.value)} />
            </div>
            <div className="control-group">
              <label>Entry Unit:</label>
              <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
                <option value="Days">Buffer Days</option>
                <option value="Boxes">Boxes</option>
                <option value="Rings">No. of Rings</option>
              </select>
            </div>
            <button className="btn-save" onClick={saveBufferData} disabled={isSaving}>
              {isSaving ? "Saving..." : "Save Buffer Data"}
            </button>
          </div>

          <div className="table-scroll-container">
            <table className="excel-table">
              <thead>
                <tr>
                  <th colSpan="3" className="text-blue text-left pl-2">SKF INDIA LTD.</th>
                  <th colSpan={totalCols - 6} className="text-blue">CHANNEL BUFFER STATUS<br/>{sector}</th>
                  <th colSpan="3" className="text-blue text-right pr-2">DATE :- {bufferDate.split('-').reverse().join('/')}</th>
                </tr>
                <tr className="header-row">
                  <th className="text-blue border-thick-right border-thick-bottom" style={{minWidth: '110px'}}>CHANNEL</th>
                  {columns.map(col => <th key={col} colSpan="2" className="text-blue column-title border-thick-right border-thick-bottom">{col}</th>)}
                </tr>
                <tr className="subheader-row">
                  <th className="font-bold border-thick-right border-thick-bottom">PART</th>
                  {columns.map(col => (
                    <React.Fragment key={`${col}-sub`}>
                      <th className="font-bold border-thick-bottom">IR</th>
                      <th className="font-bold border-thick-right border-thick-bottom">OR</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.key}>
                    <td className="row-label font-bold border-thick-right">{row.label}</td>
                    {columns.map(col => {
                      const irBlocked = isCellBlocked(row.section, col, 'IR');
                      const orBlocked = isCellBlocked(row.section, col, 'OR');

                      return (
                        <React.Fragment key={`${row.key}-${col}`}>
                          {irBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="solid-blocked-cell" style={{backgroundColor: '#b3b3b3'}}></td> : null
                          ) : (
                            <td className="input-cell"><input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/></td>
                          )}
                          {orBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="solid-blocked-cell border-thick-right" style={{backgroundColor: '#b3b3b3'}}></td> : null
                          ) : (
                            <td className="input-cell border-thick-right"><input type="text" value={tableData[`${row.key}_${col}_OR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'OR', e.target.value)}/></td>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: PRODUCTION SCHEDULE */}
      {activeTab === 'schedule' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Schedule Target Date:</label>
              <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
            </div>
            <button className="btn-save" style={{backgroundColor: '#28a745', borderColor: '#1e7e34'}} onClick={fetchSchedule} disabled={isLoadingPlan}>
              {isLoadingPlan ? "Running Scheduler (May take 1-2 mins to download sheets)..." : "Generate Production Schedule"}
            </button>
          </div>

          {scheduleData ? (
            <div className="image-layout-container" style={{ flex: 1, overflowY: 'auto', padding: '10px', backgroundColor: 'white' }}>
              <h2 style={{ color: '#004085', margin: '0 0 15px 0' }}>Schedule for {scheduleDate}</h2>
              <div style={{ display: 'flex', gap: '20px' }}>
                
                <div style={{ flex: 1 }}>
                  <h3 style={{ backgroundColor: '#0056b3', color: 'white', padding: '8px', margin: 0 }}>Face Grinding</h3>
                  {scheduleData.face_grinding?.map((m, idx) => (
                    <table key={idx} className="img-table" style={{ marginBottom: '15px' }}>
                      <thead>
                        <tr><th colSpan="4" style={{ backgroundColor: '#d1ecf1', textAlign: 'left', padding: '5px' }}>{m.machine}</th></tr>
                        <tr style={{ backgroundColor: '#eef8ff' }}><th>Part</th><th>Qty</th><th>Std Box</th><th>Timing</th></tr>
                      </thead>
                      <tbody>
                        {m.rows.map((r, i) => (
                          <tr key={i}><td>{r.part}</td><td style={{textAlign:'center'}}>{r.qty}</td><td style={{textAlign:'center'}}>{r.std_box}</td><td style={{textAlign:'center'}}>{r.timing}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  ))}
                </div>

                <div style={{ flex: 1 }}>
                  <h3 style={{ backgroundColor: '#28a745', color: 'white', padding: '8px', margin: 0 }}>OD Grinding</h3>
                  {scheduleData.od_grinding?.map((m, idx) => (
                    <table key={idx} className="img-table" style={{ marginBottom: '15px' }}>
                      <thead>
                        <tr><th colSpan="4" style={{ backgroundColor: '#d1ecf1', textAlign: 'left', padding: '5px' }}>{m.machine}</th></tr>
                        <tr style={{ backgroundColor: '#eef8ff' }}><th>Part</th><th>Qty</th><th>Std Box</th><th>Timing</th></tr>
                      </thead>
                      <tbody>
                        {m.rows.map((r, i) => (
                          <tr key={i}><td>{r.part}</td><td style={{textAlign:'center'}}>{r.qty}</td><td style={{textAlign:'center'}}>{r.std_box}</td><td style={{textAlign:'center'}}>{r.timing}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  ))}
                </div>

                <div style={{ flex: 1 }}>
                  <h3 style={{ backgroundColor: '#dc3545', color: 'white', padding: '8px', margin: 0 }}>Heat Treatment</h3>
                  {scheduleData.heat_treatment?.map((m, idx) => (
                    <table key={idx} className="img-table" style={{ marginBottom: '15px' }}>
                      <thead>
                        <tr><th colSpan="4" style={{ backgroundColor: '#f8d7da', textAlign: 'left', padding: '5px' }}>{m.furnace} ({m.capacity})</th></tr>
                        <tr style={{ backgroundColor: '#f5c6cb' }}><th>Part</th><th>Qty</th><th>Rate</th><th>Timing</th></tr>
                      </thead>
                      <tbody>
                        {m.rows.map((r, i) => (
                          <tr key={i}><td>{r.part}</td><td style={{textAlign:'center'}}>{r.qty}</td><td style={{textAlign:'center'}}>{r.rate}</td><td style={{textAlign:'center'}}>{r.timing}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  ))}
                </div>

              </div>
            </div>
          ) : (
            <div style={{ padding: '30px', textAlign: 'center', color: '#666', backgroundColor: 'white', flex: 1 }}>
              <p>No schedule generated. Click "Generate Production Schedule" to compute.</p>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: MACHINE AVAILABILITY */}
      {activeTab === 'availability' && (
        <div style={{ backgroundColor: 'white', padding: '20px', flex: 1, overflowY: 'auto' }}>
          <h2 style={{ color: '#0056b3', marginTop: 0 }}>Machine Availability Defaults</h2>
          <p style={{ color: '#555', marginBottom: '20px' }}>Adjust machine status before running the schedule. Changes here will be applied when you click "Generate".</p>
          
          <table className="img-table" style={{ width: '100%', maxWidth: '900px' }}>
            <thead>
              <tr style={{ backgroundColor: '#eef8ff' }}>
                <th style={{ textAlign: 'left', padding: '10px' }}>Fixed Machine Name</th>
                <th>Enabled Status</th>
                <th>Whole Day Off</th>
                <th>Shift Start Time</th>
              </tr>
            </thead>
            <tbody>
              {machineAvailability.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 'bold', padding: '10px' }}>{c.machine}</td>
                  <td style={{ textAlign: 'center' }}>
                    <select value={c.enabled ? "true" : "false"} onChange={(e) => updateMachineConstraint(c.id, 'enabled', e.target.value === "true")} style={{ padding: '4px' }}>
                      <option value="true">Available</option>
                      <option value="false">Breakdown / Stopped</option>
                    </select>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <input type="checkbox" checked={c.off_whole_day} onChange={(e) => updateMachineConstraint(c.id, 'off_whole_day', e.target.checked)} />
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <input type="text" value={c.start_time} onChange={(e) => updateMachineConstraint(c.id, 'start_time', e.target.value)} style={{ width: '80px', textAlign: 'center' }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 4: PRODUCTION SUMMARY */}
      {activeTab === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Requirement Target Date:</label>
              <input type="date" value={summaryDate} onChange={(e) => setSummaryDate(e.target.value)} />
            </div>
            <button className="btn-save" onClick={fetchSummaryOnly} disabled={isLoadingSummary}>
              {isLoadingSummary ? "Loading Zeroset Plan..." : "Load Requirement Summary"}
            </button>
          </div>

          <div style={{ backgroundColor: 'white', padding: '20px', flex: 1, overflowY: 'auto' }}>
            <h2 style={{ color: '#0056b3', marginTop: 0 }}>Requirement & Production Matrix</h2>
            <table className="img-table" style={{ width: '100%' }}>
              <thead>
                <tr style={{ backgroundColor: '#eef8ff' }}>
                  <th style={{ padding: '10px', textAlign: 'left' }}>Bearing Type</th>
                  <th>Channel</th>
                  <th>Monthly Requirement</th>
                  <th>Today's Requirement</th>
                  <th>Today's Scheduled Prod</th>
                  <th>MTD Produced</th>
                  <th>Balance Left</th>
                </tr>
              </thead>
              <tbody>
                {summaryData.length === 0 ? (
                  <tr><td colSpan="7" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>Click "Load Requirement Summary" to fetch the Master ZEROSET plan.</td></tr>
                ) : (
                  summaryData.map((s, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 'bold', padding: '8px' }}>{s.type}</td>
                      <td style={{ textAlign: 'center' }}>{s.channel}</td>
                      <td style={{ textAlign: 'center' }}>{s.monthly_req}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold', color: '#0056b3' }}>{s.today_req}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold', color: s.today_prod > 0 ? 'green' : 'gray' }}>{s.today_prod || 0}</td>
                      <td style={{ textAlign: 'center' }}>{s.mtd_prod}</td>
                      <td style={{ textAlign: 'center' }}>{s.balance}</td>
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

export default SHOScheduling;

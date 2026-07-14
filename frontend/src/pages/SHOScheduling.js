import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

// Ensure this matches your deployment URL
const API_BASE = 'https://scm-backend-pshv.onrender.com';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer'); 
  
  // Tab 1: Buffer State
  const [sector, setSector] = useState('DGBB');
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  const [tableData, setTableData] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  
  // Tab 3: Schedule State
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);
  const [isSavingPlan, setIsSavingPlan] = useState(false);

  // Tab 4: Summary State
  const [summaryDate, setSummaryDate] = useState(new Date().toISOString().split('T')[0]);
  const [summaryData, setSummaryData] = useState([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  // Tab 2: Breakdown Entry State
  const [breakdownDate, setBreakdownDate] = useState(new Date().toISOString().split('T')[0]);
  const [machineAvailability, setMachineAvailability] = useState([]);
  const [isLoadingMachines, setIsLoadingMachines] = useState(false);
  const [isSavingBreakdowns, setIsSavingBreakdowns] = useState(false);

  // Tab 5: Required Data Availability State
  const [dataAvailability, setDataAvailability] = useState([]);
  const [isLoadingDataAvailability, setIsLoadingDataAvailability] = useState(false);

  // -- CONSTANTS --
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  const DEFAULT_BLOCKED = {
    DGBB: { 
        HT: { CH07: ['IR', 'OR'] },
        OD: { 
          CH01: ['IR'], CH02: ['IR', 'OR'], CH04: ['IR', 'OR'], 
          CH05: ['IR'], CH07: ['IR', 'OR'], CH08: ['IR'], CH11: ['IR'] 
        }, 
        FACE: { 
          CH01: ['IR'], CH02: ['IR', 'OR'], CH04: ['IR', 'OR'], CH07: ['IR', 'OR'] 
        } 
    },
    TRB: { 
        HT: {},
        OD: { 
          'T 1': ['IR'], 'T 2': ['IR'], 'T 3': ['IR'], 'T 4': ['IR'], 
          'T 5': ['IR'], 'T 6': ['IR'], 'T 7': ['IR'], 'T 8': ['IR', 'OR'], 
          'T 9': ['IR'], 'T10': ['IR'] 
        }, 
        FACE: { 'T 8': ['IR', 'OR'], 'T 9': ['IR'] } 
    },
    HUB: { 
        HT: {},
        OD: { 'HUB 1.2': ['IR'], 'HUB 1.3': ['IR'], 'HUB 1.4': ['IR'] }, 
        FACE: {} 
    }
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
    { label: 'TYPE', key: 'type_4', section: 'FACE', sectionIndex: 3 },
    { label: 'HT. BUFFER', key: 'ht_buffer_1', section: 'HT', sectionIndex: 0 },
    { label: 'TYPE', key: 'type_5', section: 'HT', sectionIndex: 1 },
    { label: 'HT. BUFFER', key: 'ht_buffer_2', section: 'HT', sectionIndex: 2 },
    { label: 'TYPE', key: 'type_6', section: 'HT', sectionIndex: 3 },
    { label: '', key: 'spacer', section: 'NONE', sectionIndex: 0 },
    { label: 'RUNNING', key: 'running', section: 'RUN', sectionIndex: 0 },
    { label: 'NEXT TYPE', key: 'next_type_3', section: 'RUN', sectionIndex: 1 },
    { label: 'BUFFER IN DAYS', key: 'buffer_in_days', section: 'RUN', sectionIndex: 2 }
  ];

  // Load Initial Buffer State
  useEffect(() => {
    const storageKey = `sho_db_${sector}_${bufferDate}`;
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
      setTableData(JSON.parse(savedData).entries || {});
    } else {
      setTableData({});
    }
  }, [sector, bufferDate]);

  useEffect(() => {
    const fetchSavedPlanForDate = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/get_plan?date=${scheduleDate}`);
        const result = await response.json();
        if (response.ok && result.status === 'success' && result.data) {
          setScheduleData(result.data);
        } else {
          setScheduleData(null);
        }
      } catch (err) {
        setScheduleData(null);
      }
    };
    fetchSavedPlanForDate();
  }, [scheduleDate]);

  // Fallback function to generate master list if backend fails to send machines
  const generateFallbackMachines = (currentSector) => {
    const channels = SECTOR_COLUMNS[currentSector] || [];
    const fallbacks = [];
    
    // Channels
    channels.forEach(ch => fallbacks.push({ id: ch, machine: `Channel ${ch}`, status: 'Available', start_time: '', end_time: '' }));
    
    // Standard Furnaces
    const furnaces = ['AICHELIN 1', 'AICHELIN 2', 'AICHELIN 3', 'AICHELIN 4', 'SBB FURNACE', 'IPSEN'];
    furnaces.forEach(f => fallbacks.push({ id: f, machine: f, status: 'Available', start_time: '', end_time: '' }));
    
    // Standard Face / OD (Generic fallbacks)
    const grinders = ['544 Face', 'Face Grinder 1', 'OD Grinder 1', 'OD Grinder 2'];
    grinders.forEach(g => fallbacks.push({ id: g, machine: g, status: 'Available', start_time: '', end_time: '' }));
    
    return fallbacks;
  };

  // Dynamically Fetch Resources based on Breakdown Date AND Sector
  useEffect(() => {
    const fetchMachines = async () => {
      setIsLoadingMachines(true);
      try {
        // Passed sector as well just in case backend filters resources by sector
        const response = await fetch(`${API_BASE}/api/machines?date=${breakdownDate}&sector=${sector}`);
        const result = await response.json();
        if (response.ok && result.status === 'success' && result.data && result.data.length > 0) {
          const loadedMachines = result.data.map(m => {
            if (typeof m === 'string') {
              return { id: m, machine: m, status: 'Available', start_time: '', end_time: '' };
            }
            return { id: m.machine, ...m, status: m.status || 'Available' };
          });
          setMachineAvailability(loadedMachines);
        } else {
          // Guaranteed visibility: If backend returns empty, load the fallback list
          setMachineAvailability(generateFallbackMachines(sector));
        }
      } catch (err) {
        // Guaranteed visibility: If network fails, load the fallback list
        setMachineAvailability(generateFallbackMachines(sector));
      }
      setIsLoadingMachines(false);
    };
    fetchMachines();
  }, [breakdownDate, sector]);

  const handleInputChange = (rowKey, col, subCol, value) => setTableData(prev => ({ ...prev, [`${rowKey}_${col}_${subCol}`]: value }));

  const saveBufferData = () => {
    setIsSaving(true);
    localStorage.setItem(`sho_db_${sector}_${bufferDate}`, JSON.stringify({ entries: tableData }));
    setTimeout(() => { setIsSaving(false); alert("Buffer Data Saved successfully."); }, 300);
  };

  const updateMachineConstraint = (id, field, value) => {
    setMachineAvailability(prev => prev.map(c => (c.id === id ? { ...c, [field]: value } : c)));
  };

  const resetMachineConstraint = (id) => {
    setMachineAvailability(prev => prev.map(c => (c.id === id ? { ...c, status: 'Available', start_time: '', end_time: '' } : c)));
  };

  const handleSaveBreakdowns = async () => {
    setIsSavingBreakdowns(true);
    try {
      const response = await fetch(`${API_BASE}/api/save_breakdowns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: breakdownDate, breakdowns: machineAvailability })
      });
      const result = await response.json();
      if (result.status === 'success') alert('Breakdowns saved successfully for ' + breakdownDate);
      else alert('Error saving breakdowns: ' + result.detail);
    } catch (error) {
      alert('Error connecting to server.');
    }
    setIsSavingBreakdowns(false);
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
      alert("Failed to connect to backend.");
    }
    setIsLoadingSummary(false);
  };

  const fetchDataAvailability = async () => {
    setIsLoadingDataAvailability(true);
    try {
      // FIX 1: Passed sector and date to fix the 422 Unprocessable Content Error
      const response = await fetch(`${API_BASE}/api/data_availability?sector=${sector}&date=${summaryDate}`);
      const result = await response.json();
      if (response.ok && result.status === 'success') {
        setDataAvailability(result.data || []);
      } else {
        // FIX 2: Correctly format the FastAPI [object Object] error array to string so it's readable
        const errorMsg = typeof result.detail === 'object' ? JSON.stringify(result.detail, null, 2) : result.detail;
        alert("Error loading data availability from backend:\n" + errorMsg);
      }
    } catch (e) {
      alert("Failed to connect to backend.");
    }
    setIsLoadingDataAvailability(false);
  };

  const handleSavePlan = async () => {
    if (!scheduleData) return;
    setIsSavingPlan(true);
    
    const planToSave = {
      face_grinding: scheduleData.face_grinding || [],
      od_grinding: scheduleData.od_grinding || [],
      heat_treatment: scheduleData.heat_treatment || [],
      unscheduled: scheduleData.unscheduled || [] 
    };

    try {
      const response = await fetch(`${API_BASE}/api/save_plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: scheduleDate, plan: planToSave })
      });
      const result = await response.json();
      if (result.status === 'success') alert('Production Plan saved successfully for ' + scheduleDate);
      else alert('Error saving plan: ' + result.detail);
    } catch (error) {
      alert('Error connecting to server.');
    }
    setIsSavingPlan(false);
  };

  const fetchSchedule = async () => {
    setIsLoadingPlan(true);
    const availabilityMap = {};
    
    machineAvailability.forEach(c => {
      if (c.machine.trim()) {
        availabilityMap[c.machine.trim()] = {
          enabled: c.status === 'Available',
          bd_date: breakdownDate,
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
        alert("Server failed to generate schedule: " + (result.detail || result.message)); 
      }
    } catch (e) { 
      alert(`Network error: Failed to connect to backend.`); 
    }
    setIsLoadingPlan(false);
  };

  const columns = SECTOR_COLUMNS[sector];
  const totalCols = (columns.length * 2) + 1;
  const isCellBlocked = (section, col, subCol) => DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol);

  const htData = scheduleData?.heat_treatment || [];
  const midPoint = Math.max(1, Math.ceil(htData.length / 2));
  const htColumn1 = htData.slice(0, midPoint);
  const htColumn2 = htData.slice(midPoint);

  return (
    <div className="sho-container">
      {/* 5 NAVIGATION TABS */}
      <div className="tab-buttons" style={{ marginBottom: '15px' }}>
        <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Buffer Entry</button>
        <button className={activeTab === 'availability' ? 'active' : ''} onClick={() => setActiveTab('availability')}>2. Breakdown Entry</button>
        <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>3. Production Schedule</button>
        <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')}>4. Production Summary</button>
        <button className={activeTab === 'data_availability' ? 'active' : ''} onClick={() => setActiveTab('data_availability')}>5. Required Data Availability</button>
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
                  <tr key={row.key} className={row.key === 'spacer' ? 'spacer-row border-thick-bottom' : ''}>
                    <td className="row-label font-bold border-thick-right">{row.label}</td>
                    {row.key !== 'spacer' ? columns.map(col => {
                      const irBlocked = isCellBlocked(row.section, col, 'IR');
                      const orBlocked = isCellBlocked(row.section, col, 'OR');

                      return (
                        <React.Fragment key={`${row.key}-${col}`}>
                          {irBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="solid-blocked-cell" style={{backgroundColor: '#b3b3b3'}}></td> : null
                          ) : (
                            <td className="input-cell"><input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/></td>
                          ) }
                          {orBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="solid-blocked-cell border-thick-right" style={{backgroundColor: '#b3b3b3'}}></td> : null
                          ) : (
                            <td className="input-cell border-thick-right"><input type="text" value={tableData[`${row.key}_${col}_OR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'OR', e.target.value)}/></td>
                          )}
                        </React.Fragment>
                      );
                    }) : columns.map(col => (
                      <React.Fragment key={`spacer-${col}`}>
                        <td className="spacer-cell border-thick-bottom"></td>
                        <td className="spacer-cell border-thick-right border-thick-bottom"></td>
                      </React.Fragment>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: BREAKDOWN ENTRY */}
      {activeTab === 'availability' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Breakdown Date:</label>
              <input type="date" value={breakdownDate} onChange={(e) => setBreakdownDate(e.target.value)} />
            </div>
            <button className="btn-save" onClick={handleSaveBreakdowns} disabled={isSavingBreakdowns}>
              {isSavingBreakdowns ? "Saving..." : "Save Breakdown Entries"}
            </button>
          </div>

          <div style={{ backgroundColor: 'white', padding: '20px', flex: 1, overflowY: 'auto' }}>
            <h2 style={{ color: '#0056b3', marginTop: 0 }}>Breakdown Entry Log</h2>
            <p style={{ color: '#555', marginBottom: '20px' }}>
              Select a date above. Apply full breakdowns or partial hours for Furnaces, Face Machines, OD Machines, and Channels. 
              Unsaved entries default to Available.
            </p>
            
            {isLoadingMachines ? (
               <div style={{ padding: '20px', color: '#666', fontWeight: 'bold' }}>Fetching resources for selected date...</div>
            ) : (
              <table className="img-table" style={{ width: '100%', maxWidth: '950px' }}>
                <thead>
                  <tr style={{ backgroundColor: '#eef8ff' }}>
                    <th style={{ textAlign: 'left', padding: '10px' }}>Resource Name</th>
                    <th>Status</th>
                    <th>Breakdown Start Time</th>
                    <th>Breakdown End Time</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {machineAvailability.map((c) => (
                    <tr key={c.id}>
                      <td style={{ fontWeight: 'bold', padding: '10px' }}>{c.machine}</td>
                      <td style={{ textAlign: 'center' }}>
                        <select 
                          value={c.status} 
                          onChange={(e) => updateMachineConstraint(c.id, 'status', e.target.value)} 
                          style={{ padding: '4px', width: '150px' }}
                        >
                          <option value="Available">Available</option>
                          <option value="Complete Breakdown">Complete Breakdown</option>
                        </select>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <input 
                          type="time" 
                          value={c.start_time || ''} 
                          onChange={(e) => updateMachineConstraint(c.id, 'start_time', e.target.value)} 
                          style={{ padding: '4px' }} 
                          disabled={c.status === 'Complete Breakdown'} 
                        />
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <input 
                          type="time" 
                          value={c.end_time || ''} 
                          onChange={(e) => updateMachineConstraint(c.id, 'end_time', e.target.value)} 
                          style={{ padding: '4px' }} 
                          disabled={c.status === 'Complete Breakdown'} 
                        />
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <button onClick={() => resetMachineConstraint(c.id)} style={{ padding: '4px 8px', cursor: 'pointer', backgroundColor: '#e9ecef', border: '1px solid #ccc' }}>Reset</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: PRODUCTION SCHEDULE */}
      {activeTab === 'schedule' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          <div className="controls-panel" style={{ backgroundColor: '#eef8ff' }}>
            <div className="control-group">
              <label>Select Target Date:</label>
              <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
            </div>
            <button className="btn-save" style={{backgroundColor: '#28a745', borderColor: '#1e7e34'}} onClick={fetchSchedule} disabled={isLoadingPlan}>
              {isLoadingPlan ? "Running Rapid Scheduler (Downloading Sheets)..." : "Generate Production Schedule"}
            </button>
            {scheduleData && (
              <button className="btn-save" style={{backgroundColor: '#17a2b8', borderColor: '#117a8b'}} onClick={handleSavePlan} disabled={isSavingPlan}>
                {isSavingPlan ? 'Saving Plan...' : 'Save Production Plan'}
              </button>
            )}
          </div>
          
          {scheduleData ? (
            <div className="image-layout-container" style={{ flex: 1, overflowY: 'auto' }}>
              <div className="schedule-master-header">
                <div className="header-title">Face & OD Grinding Schedule</div>
                <div className="header-date">Date :- {scheduleDate.split('-').reverse().join('/')}</div>
              </div>

              <div className="schedule-grid-wrapper" style={{ display: 'flex', minWidth: '1300px' }}>
                
                {/* 1. FACE GRINDING */}
                <div className="schedule-column" style={{ flex: 1, position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                  <table className="img-table sticky-header-table">
                    <thead>
                      <tr className="sticky-row-1"><th colSpan="6" className="col-main-title">Face Grinding</th></tr>
                      <tr className="sub-header sticky-row-2">
                        <th rowSpan="2" className="empty-corner">PART</th>
                        <th rowSpan="2">QTY (Rings)</th>
                        <th rowSpan="2">BOX/Q</th>
                        <th rowSpan="2">TIMING (Hrs)</th>
                        <th colSpan="2">Shift Priority</th>
                      </tr>
                      <tr className="sub-header sticky-row-3"><th>2nd</th><th>3rd</th></tr>
                    </thead>
                    <tbody>
                      {(!scheduleData.face_grinding || scheduleData.face_grinding.length === 0) && (
                        <tr><td colSpan="6" className="center-text" style={{padding: "15px"}}>No parts scheduled.</td></tr>
                      )}
                      {scheduleData.face_grinding?.map((m, idx) => (
                        <React.Fragment key={idx}>
                          <tr className="machine-name-row"><td colSpan="6">{m.machine}</td></tr>
                          {m.rows.map((r, i) => (
                            <tr key={i}>
                              <td className="part-name">{r.part}</td>
                              <td className="center-text" style={{fontWeight: 'bold', color: '#0056b3'}}>{r.qty}</td>
                              <td className="center-text font-bold">{r.std_box}</td>
                              <td className="center-text text-gray-700" style={{fontSize: '0.85em', whiteSpace: 'nowrap'}}>{r.timing}</td>
                              <td className="center-text">{r.p_2nd}</td>
                              <td className="center-text">{r.p_3rd}</td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* 2. OD GRINDING */}
                <div className="schedule-column" style={{ flex: 1, position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                  <table className="img-table sticky-header-table">
                    <thead>
                      <tr className="sticky-row-1"><th colSpan="6" className="col-main-title">OD Grinding</th></tr>
                      <tr className="sub-header sticky-row-2">
                        <th rowSpan="2" className="empty-corner">PART</th>
                        <th rowSpan="2">QTY (Rings)</th>
                        <th rowSpan="2">BOX/Q</th>
                        <th rowSpan="2">TIMING (Hrs)</th>
                        <th colSpan="2">Shift Priority</th>
                      </tr>
                      <tr className="sub-header sticky-row-3"><th>2nd</th><th>3rd</th></tr>
                    </thead>
                    <tbody>
                      {(!scheduleData.od_grinding || scheduleData.od_grinding.length === 0) && (
                        <tr><td colSpan="6" className="center-text" style={{padding: "15px"}}>No parts scheduled.</td></tr>
                      )}
                      {scheduleData.od_grinding?.map((m, idx) => (
                        <React.Fragment key={idx}>
                          <tr className="machine-name-row"><td colSpan="6">{m.machine}</td></tr>
                          {m.rows.map((r, i) => (
                            <tr key={i}>
                              <td className="part-name">{r.part}</td>
                              <td className="center-text" style={{fontWeight: 'bold', color: '#0056b3'}}>{r.qty}</td>
                              <td className="center-text font-bold">{r.std_box}</td>
                              <td className="center-text text-gray-700" style={{fontSize: '0.85em', whiteSpace: 'nowrap'}}>{r.timing}</td>
                              <td className="center-text">{r.p_2nd}</td>
                              <td className="center-text">{r.p_3rd}</td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* 3. HEAT TREATMENT */}
                <div className="schedule-column ht-column" style={{ flex: 1.6, position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                  <table className="img-table sticky-header-table">
                    <thead>
                      <tr className="sticky-row-1">
                        <th colSpan="5" className="col-main-title ht-title">HEAT TREATMENT</th>
                        <th colSpan="5" className="col-main-title ht-title">DATE - {scheduleDate.split('-').reverse().join('/')}</th>
                      </tr>
                    </thead>
                    <tbody className="ht-flex-body">
                      <tr>
                        <td colSpan="5" className="nested-td">
                          <table className="inner-ht-table">
                            <tbody>
                              {htColumn1.map((f, idx) => (
                                <React.Fragment key={idx}>
                                  <tr className="machine-name-row">
                                    <td>{f.furnace}</td><td>QTY</td><td>Timing</td><td>Cha</td><td>{f.capacity}</td>
                                  </tr>
                                  {f.rows.map((r, i) => (
                                    <tr key={i}>
                                      <td className={`part-name ${r.alert ? 'text-red' : ''}`}>{r.part}</td>
                                      <td className="center-text">{r.qty}</td>
                                      <td className="center-text text-gray-700" style={{fontSize: '0.85em', whiteSpace: 'nowrap'}}>{r.timing}</td>
                                      <td className="center-text">{r.cha}</td>
                                      <td className="center-text">{r.rate}</td>
                                    </tr>
                                  ))}
                                </React.Fragment>
                              ))}
                            </tbody>
                          </table>
                        </td>
                        <td colSpan="5" className="nested-td">
                          <table className="inner-ht-table">
                            <tbody>
                              {htColumn2.map((f, idx) => (
                                <React.Fragment key={idx}>
                                  <tr className="machine-name-row">
                                    <td>{f.furnace}</td><td>QTY</td><td>Timing</td><td>Cha</td><td>{f.capacity}</td>
                                  </tr>
                                  {f.rows.map((r, i) => (
                                    <tr key={i}>
                                      <td className={`part-name ${r.alert ? 'text-red' : ''}`}>{r.part}</td>
                                      <td className="center-text">{r.qty}</td>
                                      <td className="center-text text-gray-700" style={{fontSize: '0.85em', whiteSpace: 'nowrap'}}>{r.timing}</td>
                                      <td className="center-text">{r.cha}</td>
                                      <td className="center-text">{r.rate}</td>
                                    </tr>
                                  ))}
                                </React.Fragment>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* UNSCHEDULED ALERTS */}
              {scheduleData.unscheduled && scheduleData.unscheduled.length > 0 && (
                <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fff5f5', border: '1px solid #ffcccc', borderRadius: '5px' }}>
                    <h3 style={{ color: '#cc0000', marginTop: 0, marginBottom: '10px' }}>⚠️ Unscheduled Parts (Pending / Moving to Next Day)</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', backgroundColor: '#fff5f5' }}>
                        <thead>
                            <tr style={{ backgroundColor: '#ffe5e5' }}>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Stage</th>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Part Type</th>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Missed Boxes / Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scheduleData.unscheduled.map((item, idx) => (
                                <tr key={idx}>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc', fontWeight: 'bold' }}>{item.stage}</td>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc' }}>{item.part}</td>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc', color: '#cc0000' }}>
                                      {item.missed_boxes}
                                      {item.status && (
                                        <span style={{ color: '#b30000', marginLeft: '8px', fontWeight: 'bold' }}>
                                          ({item.status})
                                        </span>
                                      )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: '30px', textAlign: 'center', color: '#666', backgroundColor: 'white', flex: 1 }}>
              <p>No schedule generated for this date yet. Click "Generate Production Schedule".</p>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: PRODUCTION SUMMARY */}
      {activeTab === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Requirement Date:</label>
              <input type="date" value={summaryDate} onChange={(e) => setSummaryDate(e.target.value)} />
            </div>
            <button className="btn-save" onClick={fetchSummaryOnly} disabled={isLoadingSummary}>
              {isLoadingSummary ? "Downloading Zeroset Plan..." : "Load Requirement Summary"}
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
                  <th>Difference</th>
                  <th>MTD Produced</th>
                  <th>Balance Left</th>
                  <th>Remaining %</th>
                </tr>
              </thead>
              <tbody>
                {summaryData.length === 0 ? (
                  <tr><td colSpan="9" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>Click "Load Requirement Summary" to fetch the Master ZEROSET plan for the selected date.</td></tr>
                ) : (
                  summaryData.map((s, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 'bold', padding: '8px' }}>{s.type}</td>
                      <td style={{ textAlign: 'center' }}>{s.channel}</td>
                      <td style={{ textAlign: 'center' }}>{s.monthly_req}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold', color: '#0056b3' }}>{s.today_req}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold', color: s.today_prod > 0 ? 'green' : 'gray' }}>{s.today_prod || 0}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold', color: (s.difference ?? 0) < 0 ? '#dc3545' : '#28a745' }}>
                        {s.difference !== undefined ? (s.difference > 0 ? `+${s.difference}` : s.difference) : '0'}
                      </td>
                      <td style={{ textAlign: 'center' }}>{s.mtd_prod}</td>
                      <td style={{ textAlign: 'center' }}>{s.balance}</td>
                      <td style={{ textAlign: 'center', color: '#555', fontSize: '0.9em' }}>{s.remaining_pct != null ? `${s.remaining_pct}%` : '0%'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 5: REQUIRED DATA AVAILABILITY */}
      {activeTab === 'data_availability' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <button className="btn-save" onClick={fetchDataAvailability} disabled={isLoadingDataAvailability}>
              {isLoadingDataAvailability ? "Fetching Master Data..." : "Load Data Availability"}
            </button>
          </div>

          <div style={{ backgroundColor: 'white', padding: '20px', flex: 1, overflowY: 'auto' }}>
            <h2 style={{ color: '#0056b3', marginTop: 0 }}>Required Data Availability</h2>
            <p style={{ color: '#555', marginBottom: '20px' }}>
              Reporting view mapping all requested Bearing Types against master production parameters.
            </p>
            <table className="img-table" style={{ width: '100%' }}>
              <thead>
                <tr style={{ backgroundColor: '#eef8ff' }}>
                  <th style={{ padding: '10px', textAlign: 'left' }}>Channel</th>
                  <th>Bearing Type</th>
                  <th>Part (IR / OR)</th>
                  <th>Weight per Ring</th>
                  <th>Primary Furnace</th>
                  <th>Alternative Furnace 1</th>
                  <th>Alternative Furnace 2</th>
                  <th>Compatible Face Machine</th>
                  <th>Compatible OD Machine</th>
                  <th>Ring per Box</th>
                </tr>
              </thead>
              <tbody>
                {dataAvailability.length === 0 ? (
                  <tr>
                    <td colSpan="10" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                      Click "Load Data Availability" to fetch data for all required channels.
                    </td>
                  </tr>
                ) : (
                  dataAvailability.map((row, index) => (
                    <tr key={index}>
                      <td style={{ fontWeight: 'bold', padding: '8px' }}>{row.channel}</td>
                      <td style={{ textAlign: 'center' }}>{row.bearing_type}</td>
                      <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{row.part}</td>
                      <td style={{ textAlign: 'center', color: row.weight === 'Missing Weight' ? 'red' : 'black' }}>
                        {row.weight}
                      </td>
                      <td style={{ textAlign: 'center', color: row.primary_furnace === 'No Compatible Furnace' ? 'red' : 'black' }}>
                        {row.primary_furnace}
                      </td>
                      <td style={{ textAlign: 'center' }}>{row.alt_furnace_1 || ''}</td>
                      <td style={{ textAlign: 'center' }}>{row.alt_furnace_2 || ''}</td>
                      <td style={{ textAlign: 'center', color: row.compatible_face === 'No Compatible Face Machine' ? 'red' : 'black' }}>
                        {row.compatible_face}
                      </td>
                      <td style={{ textAlign: 'center', color: row.compatible_od === 'No Compatible OD Machine' ? 'red' : 'black' }}>
                        {row.compatible_od}
                      </td>
                      <td style={{ textAlign: 'center', color: row.ring_per_box === 'Missing Data' ? 'red' : 'black' }}>
                        {row.ring_per_box}
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
  );
};

export default SHOScheduling;

import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer'); 
  const [sector, setSector] = useState('DGBB');
  
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  
  const [tableData, setTableData] = useState({});
  const [unlockedBlocks, setUnlockedBlocks] = useState([]); 
  const [isSaving, setIsSaving] = useState(false);
  
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);

  // -- CONSTANTS --
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  const DEFAULT_BLOCKED = {
    DGBB: { OD: { CH01: ['IR'], CH03: ['IR', 'OR'], SABB: ['OR'], CH07: ['IR', 'OR'], CH11: ['IR', 'OR'] }, FACE: { CH02: ['IR', 'OR'], CH04: ['IR', 'OR'], SABB: ['IR', 'OR'], CH07: ['IR', 'OR'], CH11: ['IR', 'OR'] } },
    TRB: { OD: { 'T 3': ['IR', 'OR'], 'T 5': ['IR', 'OR'], 'T 6': ['IR', 'OR'], 'T 9': ['IR', 'OR'], 'T10': ['IR', 'OR'] }, FACE: { 'T 8': ['IR', 'OR'], 'T 9': ['IR', 'OR'], 'T10': ['IR', 'OR'] } },
    HUB: { OD: { 'HUB 1.1': ['IR', 'OR'], 'T HUB 1.1': ['IR', 'OR'] }, FACE: {} }
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

  useEffect(() => {
    const storageKey = `sho_db_${sector}_${bufferDate}`;
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
      const parsed = JSON.parse(savedData);
      setTableData(parsed.entries || {});
      setUnlockedBlocks(parsed.unlocked || []);
    } else {
      setTableData({});
      setUnlockedBlocks([]);
    }
  }, [sector, bufferDate]);

  const handleInputChange = (rowKey, col, subCol, value) => setTableData(prev => ({ ...prev, [`${rowKey}_${col}_${subCol}`]: value }));
  const unlockBlock = (section, col, subCol) => {
    const blockKey = `${sector}_${section}_${col}_${subCol}`;
    if (!unlockedBlocks.includes(blockKey)) setUnlockedBlocks([...unlockedBlocks, blockKey]);
  };

  const saveBufferData = () => {
    setIsSaving(true);
    localStorage.setItem(`sho_db_${sector}_${bufferDate}`, JSON.stringify({ entries: tableData, unlocked: unlockedBlocks }));
    setTimeout(() => { setIsSaving(false); alert("Buffer Data Saved successfully."); }, 300);
  };

  const fetchSchedule = async () => {
    setIsLoadingPlan(true);
    const API = 'https://scm-backend-pshv.onrender.com';
    try {
      const response = await fetch(`${API}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sector, date: scheduleDate, unit_mode: unitMode, entries: tableData, unlocked_blocks: unlockedBlocks })
      });
      const result = await response.json();
      
      console.log("=== BACKEND DIAGNOSTICS ===");
      if (result.debug_logs) {
          result.debug_logs.forEach(log => console.log(log));
      }

      if (response.ok && result.status === 'success') { 
        setScheduleData(result.data); 
      } else { 
        alert("Error: " + (result.detail || result.message)); 
      }
    } catch (e) { 
      alert("Failed to connect to backend. Check your network or API URL."); 
    } finally { 
      setIsLoadingPlan(false); 
    }
  };

  const columns = SECTOR_COLUMNS[sector];
  const totalCols = (columns.length * 2) + 1;
  const isCellBlocked = (section, col, subCol) => DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol) && !unlockedBlocks.includes(`${sector}_${section}_${col}_${subCol}`);

  const htData = scheduleData?.heat_treatment || [];
  const midPoint = Math.max(1, Math.ceil(htData.length / 2));
  const htColumn1 = htData.slice(0, midPoint);
  const htColumn2 = htData.slice(midPoint);

  return (
    <div className="sho-container">
      <div className="tab-buttons">
        <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Buffer Entry</button>
        <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Production Schedule</button>
      </div>

      {activeTab === 'buffer' && (
        <>
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
                            row.sectionIndex === 0 ? <td rowSpan={4} className="disabled-block" onDoubleClick={() => unlockBlock(row.section, col, 'IR')}></td> : null
                          ) : (
                            <td className="input-cell"><input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/></td>
                          )}
                          {orBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="disabled-block border-thick-right" onDoubleClick={() => unlockBlock(row.section, col, 'OR')}></td> : null
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
        </>
      )}

      {activeTab === 'schedule' && (
        <>
          <div className="controls-panel" style={{ backgroundColor: '#eef8ff' }}>
            <div className="control-group">
              <label>Select Date to Schedule:</label>
              <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
            </div>
            <button className="btn-save" style={{backgroundColor: '#28a745', borderColor: '#1e7e34'}} onClick={fetchSchedule} disabled={isLoadingPlan}>
              {isLoadingPlan ? "Fetching Excel Files & Calculating..." : "Generate Production Schedule"}
            </button>
          </div>
          
          {scheduleData && (
            <div className="image-layout-container">
              <div className="schedule-master-header">
                <div className="header-title">Face & OD Grinding Schedule</div>
                <div className="header-date">Date :- {scheduleDate.split('-').reverse().join('/')}</div>
              </div>

              <div className="schedule-grid-wrapper">
                
                {/* 1. FACE GRINDING */}
                <div className="schedule-column">
                  <table className="img-table">
                    <thead>
                      <tr><th colSpan="4" className="col-main-title">Face Grinding</th></tr>
                      <tr className="sub-header">
                        <th rowSpan="2" className="empty-corner"></th>
                        <th rowSpan="2">STD BOX</th>
                        <th colSpan="2">Shift Priority</th>
                      </tr>
                      <tr className="sub-header"><th>2nd</th><th>3rd</th></tr>
                    </thead>
                    <tbody>
                      {(!scheduleData.face_grinding || scheduleData.face_grinding.length === 0) && (
                        <tr><td colSpan="4" className="center-text" style={{padding: "15px"}}>No parts scheduled. Check Backend.</td></tr>
                      )}
                      {scheduleData.face_grinding?.map((m, idx) => (
                        <React.Fragment key={idx}>
                          <tr className="machine-name-row"><td colSpan="4">{m.machine}</td></tr>
                          {m.rows.map((r, i) => (
                            <tr key={i}>
                              <td className={`part-name ${r.alert ? 'text-red' : ''}`}>{r.part}</td>
                              <td className="center-text">{r.std_box}</td>
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
                <div className="schedule-column">
                  <table className="img-table">
                    <thead>
                      <tr><th colSpan="4" className="col-main-title">OD Grinding</th></tr>
                      <tr className="sub-header">
                        <th rowSpan="2" className="empty-corner"></th>
                        <th rowSpan="2">STD BOX</th>
                        <th colSpan="2">Shift Priority</th>
                      </tr>
                      <tr className="sub-header"><th>2nd</th><th>3rd</th></tr>
                    </thead>
                    <tbody>
                      {(!scheduleData.od_grinding || scheduleData.od_grinding.length === 0) && (
                        <tr><td colSpan="4" className="center-text" style={{padding: "15px"}}>No parts scheduled. Check Backend.</td></tr>
                      )}
                      {scheduleData.od_grinding?.map((m, idx) => (
                        <React.Fragment key={idx}>
                          <tr className="machine-name-row"><td colSpan="4">{m.machine}</td></tr>
                          {m.rows.map((r, i) => (
                            <tr key={i}>
                              <td className={`part-name ${r.alert ? 'text-red' : ''}`}>
                                {r.p_label && <span className="p-badge">{r.p_label}</span>} {r.part}
                              </td>
                              <td className="center-text">{r.std_box}</td>
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
                <div className="schedule-column ht-column">
                  <table className="img-table">
                    <thead>
                      <tr>
                        <th colSpan="4" className="col-main-title ht-title">HEAT TREATMENT</th>
                        <th colSpan="4" className="col-main-title ht-title">DATE - {scheduleDate.split('-').reverse().join('/')}</th>
                      </tr>
                    </thead>
                    <tbody className="ht-flex-body">
                      <tr>
                        {/* Furnace Column 1 */}
                        <td colSpan="4" className="nested-td">
                          <table className="inner-ht-table">
                            <tbody>
                              {htColumn1.length === 0 && (
                                <tr><td colSpan="4" className="center-text" style={{padding: "15px"}}>No HT scheduled.</td></tr>
                              )}
                              {htColumn1.map((f, idx) => (
                                <React.Fragment key={idx}>
                                  <tr className="machine-name-row">
                                    <td>{f.furnace}</td><td>QTY</td><td>Cha</td><td>TOTAL KG</td>
                                  </tr>
                                  {f.rows.map((r, i) => (
                                    <tr key={i}>
                                      <td className={`part-name ${r.alert ? 'text-red' : ''}`}>{r.part}</td>
                                      <td className="center-text">{r.qty}</td>
                                      <td className="center-text">{r.cha}</td>
                                      <td className="center-text font-bold">{r.rate}</td>
                                    </tr>
                                  ))}
                                </React.Fragment>
                              ))}
                            </tbody>
                          </table>
                        </td>
                        {/* Furnace Column 2 */}
                        <td colSpan="4" className="nested-td">
                          <table className="inner-ht-table">
                            <tbody>
                              {htColumn2.map((f, idx) => (
                                <React.Fragment key={idx}>
                                  <tr className="machine-name-row">
                                    <td>{f.furnace}</td><td>QTY</td><td>Cha</td><td>TOTAL KG</td>
                                  </tr>
                                  {f.rows.map((r, i) => (
                                    <tr key={i}>
                                      <td className={`part-name ${r.alert ? 'text-red' : ''}`}>{r.part}</td>
                                      <td className="center-text">{r.qty}</td>
                                      <td className="center-text">{r.cha}</td>
                                      <td className="center-text font-bold">{r.rate}</td>
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
              
              {/* UNSCHEDULED ALERTS COMPONENT */}
              {scheduleData.unscheduled && scheduleData.unscheduled.length > 0 && (
                <div style={{ marginTop: '30px', borderTop: '2px dashed #ff4444', paddingTop: '20px' }}>
                    <h3 style={{ color: '#ff4444', marginBottom: '10px' }}>⚠️ Unscheduled Parts (Capacity/Missing Data)</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', backgroundColor: '#fff5f5' }}>
                        <thead>
                            <tr style={{ backgroundColor: '#ffe5e5' }}>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Stage</th>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Part</th>
                                <th style={{ padding: '8px', border: '1px solid #ffcccc' }}>Missed Boxes / Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scheduleData.unscheduled.map((item, idx) => (
                                <tr key={idx}>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc', fontWeight: 'bold' }}>{item.stage}</td>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc' }}>{item.part}</td>
                                    <td style={{ padding: '8px', border: '1px solid #ffcccc', color: '#cc0000' }}>{item.missed_boxes}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default SHOScheduling;

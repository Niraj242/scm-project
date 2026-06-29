import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  // Navigation State
  const [activeTab, setActiveTab] = useState('buffer'); // 'buffer' or 'schedule'
  
  // Buffer Entry States
  const [sector, setSector] = useState('DGBB');
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  const [tableData, setTableData] = useState({});
  const [unlockedBlocks, setUnlockedBlocks] = useState([]); 
  const [isSaving, setIsSaving] = useState(false);

  // Schedule View States
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingSchedule, setIsLoadingSchedule] = useState(false);

  // --- Constants (Keeping your exact setup) ---
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

  // Load local storage for buffer
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

  const handleSaveBuffer = () => {
    setIsSaving(true);
    const payload = { entries: tableData, unlocked: unlockedBlocks };
    localStorage.setItem(`sho_db_${sector}_${bufferDate}`, JSON.stringify(payload));
    setTimeout(() => {
        setIsSaving(false);
        alert("Buffer Data Saved locally.");
    }, 500);
  };

  const fetchSchedule = async () => {
    setIsLoadingSchedule(true);
    const API = 'https://scm-backend-pshv.onrender.com';
    try {
      const response = await fetch(`${API}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sector: sector, date: scheduleDate, entries: tableData })
      });
      const result = await response.json();
      if (response.ok) {
        setScheduleData(result.data);
      } else {
        alert("Server Error: " + (result.detail || result.message));
      }
    } catch (error) {
      console.error("Backend connection failed:", error);
      alert(`Failed to fetch schedule from backend.`);
    } finally {
      setIsLoadingSchedule(false);
    }
  };

  const columns = SECTOR_COLUMNS[sector];
  const totalCols = (columns.length * 2) + 1;
  const isCellBlocked = (section, col, subCol) => DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol) && !unlockedBlocks.includes(`${sector}_${section}_${col}_${subCol}`);

  return (
    <div className="sho-container">
      {/* Navigation Tabs */}
      <div className="tab-navigation">
        <button className={activeTab === 'buffer' ? 'active-tab' : ''} onClick={() => setActiveTab('buffer')}>1. Buffer Status Entry</button>
        <button className={activeTab === 'schedule' ? 'active-tab' : ''} onClick={() => setActiveTab('schedule')}>2. Production Schedule</button>
      </div>

      {/* VIEW 1: BUFFER ENTRY */}
      {activeTab === 'buffer' && (
        <div className="view-container">
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
                <label>Buffer Date:</label>
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
                <button className="btn-save" onClick={handleSaveBuffer} disabled={isSaving}>{isSaving ? "Saving..." : "Save Buffer Data"}</button>
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
                        return (
                            <React.Fragment key={`${row.key}-${col}`}>
                            {isCellBlocked(row.section, col, 'IR') ? (
                                row.sectionIndex === 0 ? <td rowSpan={4} className="disabled-block" onDoubleClick={() => unlockBlock(row.section, col, 'IR')}></td> : null
                            ) : (
                                <td className="input-cell"><input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/></td>
                            )}
                            {isCellBlocked(row.section, col, 'OR') ? (
                                row.sectionIndex === 0 ? <td rowSpan={4} className="disabled-block border-thick-right" onDoubleClick={() => unlockBlock(row.section, col, 'OR')}></td> : null
                            ) : (
                                <td className="input-cell border-thick-right"><input type="text" value={tableData[`${row.key}_${col}_OR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'OR', e.target.value)}/></td>
                            )}
                            </React.Fragment>
                        );
                        }) : columns.map(col => (
                        <React.Fragment key={`spacer-${col}`}>
                            <td className="spacer-cell border-thick-bottom"></td><td className="spacer-cell border-thick-right border-thick-bottom"></td>
                        </React.Fragment>
                        ))}
                    </tr>
                    ))}
                </tbody>
                </table>
            </div>
        </div>
      )}

      {/* VIEW 2: PRODUCTION SCHEDULE */}
      {activeTab === 'schedule' && (
        <div className="view-container schedule-view">
            <div className="controls-panel">
                <div className="control-group">
                    <label>Generate Plan For:</label>
                    <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
                </div>
                <button className="btn-fetch" onClick={fetchSchedule} disabled={isLoadingSchedule}>
                    {isLoadingSchedule ? "Calculating Routing & Demand..." : "Generate Production Schedule"}
                </button>
            </div>

            {scheduleData && (
                <div className="schedule-output-container">
                    <h2 className="text-blue text-center mb-2">Calculated Plan - {scheduleDate.split('-').reverse().join('/')}</h2>
                    <div className="schedule-grid">
                        
                        {/* 1. Face Grinding */}
                        <div className="schedule-col">
                            <table className="excel-table full-width">
                                <thead>
                                    <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">Face Grinding</th></tr>
                                    <tr><th className="border-thick-bottom">Machine</th><th className="border-thick-bottom">STD BOX</th><th className="border-thick-bottom">Pass 2</th><th className="border-thick-bottom">Pass 3</th></tr>
                                </thead>
                                <tbody>
                                    {scheduleData.face_grinding.length === 0 && <tr><td colSpan="4">No machines scheduled</td></tr>}
                                    {scheduleData.face_grinding.map((machineGroup, idx) => (
                                        <React.Fragment key={`face-${idx}`}>
                                            <tr className="machine-header"><th colSpan="4" className="text-left pl-2 text-blue border-thick-bottom">{machineGroup.machine}</th></tr>
                                            {machineGroup.rows.map((row, rIdx) => (
                                                <tr key={rIdx}>
                                                    <td className="text-left pl-2 font-bold">{row.part}</td>
                                                    <td>{row.std_box}</td><td>{row.p_2nd}</td><td>{row.p_3rd}</td>
                                                </tr>
                                            ))}
                                        </React.Fragment>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* 2. OD Grinding */}
                        <div className="schedule-col">
                            <table className="excel-table full-width">
                                <thead>
                                    <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">OD Grinding</th></tr>
                                    <tr><th className="border-thick-bottom">Machine</th><th className="border-thick-bottom">STD BOX</th><th className="border-thick-bottom">Pass 2</th><th className="border-thick-bottom">Pass 3</th></tr>
                                </thead>
                                <tbody>
                                    {scheduleData.od_grinding.length === 0 && <tr><td colSpan="4">No machines scheduled</td></tr>}
                                    {scheduleData.od_grinding.map((machineGroup, idx) => (
                                        <React.Fragment key={`od-${idx}`}>
                                            <tr className="machine-header"><th colSpan="4" className="text-left pl-2 text-blue border-thick-bottom">{machineGroup.machine}</th></tr>
                                            {machineGroup.rows.map((row, rIdx) => (
                                                <tr key={rIdx}>
                                                    <td className="text-left pl-2 font-bold">{row.part}</td>
                                                    <td>{row.std_box}</td><td>{row.p_2nd}</td><td>{row.p_3rd}</td>
                                                </tr>
                                            ))}
                                        </React.Fragment>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* 3. Heat Treatment */}
                        <div className="schedule-col">
                            <table className="excel-table full-width">
                                <thead>
                                    <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">HEAT TREATMENT</th></tr>
                                    <tr><th className="border-thick-bottom">Furnace</th><th className="border-thick-bottom">BOXES (Batched)</th><th className="border-thick-bottom">Cha</th><th className="border-thick-bottom">Rate</th></tr>
                                </thead>
                                <tbody>
                                    {scheduleData.heat_treatment.length === 0 && <tr><td colSpan="4">No furnaces scheduled</td></tr>}
                                    {scheduleData.heat_treatment.map((furnaceGroup, idx) => (
                                        <React.Fragment key={`ht-${idx}`}>
                                            <tr className="machine-header">
                                                <th colSpan="2" className="text-left pl-2 text-blue border-thick-bottom">{furnaceGroup.furnace}</th>
                                                <th colSpan="2" className="text-right pr-2 text-blue border-thick-bottom">Cap: {furnaceGroup.capacity}</th>
                                            </tr>
                                            {furnaceGroup.rows.map((row, rIdx) => (
                                                <tr key={rIdx}>
                                                    <td className="text-left pl-2 font-bold">{row.part}</td>
                                                    <td>{row.qty}</td><td>{row.cha}</td><td>{row.rate}</td>
                                                </tr>
                                            ))}
                                        </React.Fragment>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                    </div>
                </div>
            )}
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;

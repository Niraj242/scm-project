import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [sector, setSector] = useState('DGBB');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  
  const [tableData, setTableData] = useState({});
  const [unlockedBlocks, setUnlockedBlocks] = useState([]); 
  const [isSaving, setIsSaving] = useState(false);
  const [scheduleData, setScheduleData] = useState(null); // New state for backend output

  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  const DEFAULT_BLOCKED = {
    DGBB: { 
      OD: { CH01: ['IR'], CH03: ['IR', 'OR'], SABB: ['OR'], CH07: ['IR', 'OR'], CH11: ['IR', 'OR'] }, 
      FACE: { CH02: ['IR', 'OR'], CH04: ['IR', 'OR'], SABB: ['IR', 'OR'], CH07: ['IR', 'OR'], CH11: ['IR', 'OR'] } 
    },
    TRB: { 
      OD: { 'T 3': ['IR', 'OR'], 'T 5': ['IR', 'OR'], 'T 6': ['IR', 'OR'], 'T 9': ['IR', 'OR'], 'T10': ['IR', 'OR'] }, 
      FACE: { 'T 8': ['IR', 'OR'], 'T 9': ['IR', 'OR'], 'T10': ['IR', 'OR'] } 
    },
    HUB: { 
      OD: { 'HUB 1.1': ['IR', 'OR'], 'T HUB 1.1': ['IR', 'OR'] }, 
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

  useEffect(() => {
    const storageKey = `sho_db_${sector}_${selectedDate}`;
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
      const parsed = JSON.parse(savedData);
      setTableData(parsed.entries || {});
      setUnlockedBlocks(parsed.unlocked || []);
    } else {
      setTableData({});
      setUnlockedBlocks([]);
    }
  }, [sector, selectedDate]);

  const handleInputChange = (rowKey, col, subCol, value) => {
    setTableData(prev => ({ ...prev, [`${rowKey}_${col}_${subCol}`]: value }));
  };

  const handleSaveAndSchedule = async () => {
    setIsSaving(true);
    
    const payload = { entries: tableData, unlocked: unlockedBlocks };
    localStorage.setItem(`sho_db_${sector}_${selectedDate}`, JSON.stringify(payload));
    
    const API = 'https://scm-backend-pshv.onrender.com';
    
    try {
      const response = await fetch(`${API}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sector: sector,
          date: selectedDate,
          unit_mode: unitMode,
          entries: tableData,
          unlocked_blocks: unlockedBlocks
        })
      });

      const result = await response.json();
      if (response.ok) {
        alert("Success! Backend calculated the plan.");
        // Set the structured output from backend to render the schedule table
        setScheduleData(result.data);
      } else {
        alert("Error from server: " + (result.message || "Unknown error"));
      }
    } catch (error) {
      console.error("Failed to connect to backend:", error);
      alert(`Failed to reach the backend at ${API}. Make sure your service is live.`);
    } finally {
      setIsSaving(false);
    }
  };

  const unlockBlock = (section, col, subCol) => {
    const blockKey = `${sector}_${section}_${col}_${subCol}`;
    if (!unlockedBlocks.includes(blockKey)) {
      setUnlockedBlocks([...unlockedBlocks, blockKey]);
    }
  };

  const columns = SECTOR_COLUMNS[sector];
  const totalCols = (columns.length * 2) + 1;

  const isCellBlocked = (section, col, subCol) => {
    const defaultBlock = DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol);
    const isUnlocked = unlockedBlocks.includes(`${sector}_${section}_${col}_${subCol}`);
    return defaultBlock && !isUnlocked;
  };

  return (
    <div className="sho-container">
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
          <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} />
        </div>
        <div className="control-group">
          <label>Entry Unit:</label>
          <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
            <option value="Days">Buffer Days</option>
            <option value="Boxes">Boxes</option>
            <option value="Rings">No. of Rings</option>
          </select>
        </div>
        <button className="btn-save" onClick={handleSaveAndSchedule} disabled={isSaving}>
          {isSaving ? "Calculating..." : "Save & Generate Schedule"}
        </button>
        <div className="hint-text">💡 <em>Hint: Double-click a gray blocked cell to enable typing in it.</em></div>
      </div>

      <div className="table-scroll-container">
        <table className="excel-table">
          <thead>
            <tr>
              <th colSpan="3" className="text-blue text-left pl-2">SKF INDIA LTD.</th>
              <th colSpan={totalCols - 6} className="text-blue">
                CHANNEL BUFFER STATUS (VERSION - 6)<br/>
                {sector === 'DGBB' ? 'DBBB' : sector}
              </th>
              <th colSpan="3" className="text-blue text-right pr-2">
                DATE :- {selectedDate.split('-').reverse().join('/')}
              </th>
            </tr>
            {sector === 'DGBB' && (
              <tr>
                <th colSpan="3" className="text-blue border-thick-bottom">BUFFER IN DAYS FOR 100% EFF.</th>
                <th colSpan={14} className="text-blue font-xl border-thick-bottom">DBBB</th>
                <th colSpan="2" className="text-blue border-thick-bottom border-thick-right">SHARED OPERATION</th>
              </tr>
            )}
            {sector === 'TRB' && (
              <tr>
                <th colSpan="3" className="text-blue border-thick-bottom">BUFFER IN DAYS FOR 100% EFF.</th>
                <th colSpan={16} className="text-blue font-xl border-thick-bottom">TRB</th>
                <th colSpan="2" className="text-blue font-xl border-thick-bottom border-thick-right">SPLIT THU T10</th>
              </tr>
            )}
            {sector === 'HUB' && (
              <tr>
                <th colSpan="1" className="border-thick-bottom border-thick-right"></th>
                <th colSpan="8" className="text-blue font-xl border-thick-bottom border-thick-right">HUB</th>
                <th colSpan="6" className="text-blue font-xl border-thick-bottom border-thick-right">THUB</th>
              </tr>
            )}
            <tr className="header-row">
              <th className="text-blue border-thick-right border-thick-bottom" style={{minWidth: '110px'}}>CHANNEL</th>
              {columns.map(col => (
                <th key={col} colSpan="2" className="text-blue column-title border-thick-right border-thick-bottom">{col}</th>
              ))}
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
                        row.sectionIndex === 0 ? (
                          <td rowSpan={4} className="disabled-block" onDoubleClick={() => unlockBlock(row.section, col, 'IR')}></td>
                        ) : null
                      ) : (
                        <td className="input-cell">
                          <input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/>
                        </td>
                      )}
                      {orBlocked ? (
                        row.sectionIndex === 0 ? (
                          <td rowSpan={4} className="disabled-block border-thick-right" onDoubleClick={() => unlockBlock(row.section, col, 'OR')}></td>
                        ) : null
                      ) : (
                        <td className="input-cell border-thick-right">
                          <input type="text" value={tableData[`${row.key}_${col}_OR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'OR', e.target.value)}/>
                        </td>
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

      {/* SCHEDULE OUTPUT SECTION - Renders only if scheduleData is present */}
      {scheduleData && (
        <div className="schedule-output-container">
            <h2 className="text-blue text-center mb-2">Production Schedule - {selectedDate.split('-').reverse().join('/')}</h2>
            <div className="schedule-grid">
                
                {/* Face Grinding */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">Face Grinding</th></tr>
                            <tr>
                                <th className="border-thick-bottom">Machine</th>
                                <th className="border-thick-bottom">STD BOX</th>
                                <th className="border-thick-bottom">2nd</th>
                                <th className="border-thick-bottom">3rd</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scheduleData.face_grinding.map((machineGroup, idx) => (
                                <React.Fragment key={`face-${idx}`}>
                                    <tr className="machine-header">
                                        <th colSpan="4" className="text-left pl-2 text-blue border-thick-bottom">{machineGroup.machine}</th>
                                    </tr>
                                    {machineGroup.rows.map((row, rIdx) => (
                                        <tr key={rIdx}>
                                            <td className={`text-left pl-2 ${row.is_alert || (row.status && row.status.includes('BREAKDOWN')) ? 'text-red font-bold' : ''}`}>
                                                {row.status ? row.status : row.part}
                                            </td>
                                            <td>{row.std_box}</td>
                                            <td>{row.p_2nd}</td>
                                            <td>{row.p_3rd}</td>
                                        </tr>
                                    ))}
                                </React.Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* OD Grinding */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">OD Grinding</th></tr>
                            <tr>
                                <th className="border-thick-bottom">Machine</th>
                                <th className="border-thick-bottom">STD BOX</th>
                                <th className="border-thick-bottom">2nd</th>
                                <th className="border-thick-bottom">3rd</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scheduleData.od_grinding.map((machineGroup, idx) => (
                                <React.Fragment key={`od-${idx}`}>
                                    <tr className="machine-header">
                                        <th colSpan="4" className="text-left pl-2 text-blue border-thick-bottom">{machineGroup.machine}</th>
                                    </tr>
                                    {machineGroup.rows.map((row, rIdx) => (
                                        <tr key={rIdx}>
                                            <td className={`text-left pl-2 ${row.is_alert ? 'text-red font-bold' : ''}`}>{row.part}</td>
                                            <td>{row.std_box}</td>
                                            <td>{row.p_2nd}</td>
                                            <td>{row.p_3rd}</td>
                                        </tr>
                                    ))}
                                </React.Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Heat Treatment */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl border-thick-bottom">HEAT TREATMENT</th></tr>
                            <tr>
                                <th className="border-thick-bottom">Furnace</th>
                                <th className="border-thick-bottom">QTY</th>
                                <th className="border-thick-bottom">Cha</th>
                                <th className="border-thick-bottom">Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scheduleData.heat_treatment.map((furnaceGroup, idx) => (
                                <React.Fragment key={`ht-${idx}`}>
                                    <tr className="machine-header">
                                        <th className="text-left pl-2 text-blue border-thick-bottom">{furnaceGroup.furnace}</th>
                                        <th colSpan="3" className="text-right pr-2 text-blue border-thick-bottom">Cap: {furnaceGroup.capacity} kg/hr</th>
                                    </tr>
                                    {furnaceGroup.rows.map((row, rIdx) => (
                                        <tr key={rIdx}>
                                            <td className={`text-left pl-2 ${row.is_alert ? 'text-red font-bold' : ''}`}>{row.part}</td>
                                            <td>{row.qty}</td>
                                            <td>{row.cha}</td>
                                            <td>{row.rate}</td>
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
  );
};

export default SHOScheduling;

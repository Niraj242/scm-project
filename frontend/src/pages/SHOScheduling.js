import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [sector, setSector] = useState('DGBB');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  
  const [tableData, setTableData] = useState({});
  const [unlockedBlocks, setUnlockedBlocks] = useState([]); 
  const [isSaving, setIsSaving] = useState(false);
  
  // NEW: State to hold the backend schedule result
  const [scheduleData, setScheduleData] = useState(null);

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

  // ROWS omitted for brevity, keep the exact same ones you provided in your code.
  const ROWS = [
    { label: 'CH. BUFFER', key: 'ch_buffer_1', section: 'CH', sectionIndex: 0 },
    { label: 'TYPE', key: 'type_1', section: 'CH', sectionIndex: 1 },
    { label: 'CH. BUFFER', key: 'ch_buffer_2', section: 'CH', sectionIndex: 2 },
    { label: 'NEXT TYPE', key: 'next_type_1', section: 'CH', sectionIndex: 3 },
    { label: 'OD BUFFER', key: 'od_buffer_1', section: 'OD', sectionIndex: 0 },
    // ... Include all other rows here from your original file ...
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
        setScheduleData(result.data); // Capture generated schedule
      } else {
        alert("Error from server: " + (result.message || "Unknown error"));
      }
    } catch (error) {
      console.error("Failed to connect to backend:", error);
      alert(`Failed to reach the backend at ${API}.`);
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
      {/* Existing Controls Panel */}
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
      </div>

      {/* Existing Entry Table - Omitted interior mapping for brevity, leave exactly as you provided */}
      <div className="table-scroll-container mb-4">
        <table className="excel-table">
            {/* KEEP YOUR EXISTING TABLE HEADER AND BODY HERE EXACTLY AS IT WAS */}
            <thead>
                <tr><th colSpan={totalCols} className="text-blue">Buffer Status Entry</th></tr>
            </thead>
            <tbody>
                 {ROWS.map((row) => ( <tr key={row.key}><td className="row-label">{row.label}</td><td>...</td></tr> ))}
            </tbody>
        </table>
      </div>

      {/* NEW: Render the production schedule if data exists */}
      {scheduleData && (
        <div className="schedule-output-container">
            <h2 className="text-blue text-center mb-2">Production Schedule - {selectedDate.split('-').reverse().join('/')}</h2>
            <div className="schedule-grid">
                
                {/* Face Grinding Column */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl">Face Grinding</th></tr>
                            <tr><th>Machine</th><th>STD BOX</th><th>2nd</th><th>3rd</th></tr>
                        </thead>
                        <tbody>
                            {scheduleData.face_grinding.map((machineGroup, idx) => (
                                <React.Fragment key={`face-${idx}`}>
                                    <tr className="machine-header"><th colSpan="4" className="text-left pl-2 text-blue">{machineGroup.machine}</th></tr>
                                    {machineGroup.rows.map((row, rIdx) => (
                                        <tr key={rIdx}>
                                            <td className={`text-left pl-2 ${row.is_alert || row.status.includes('BREAKDOWN') ? 'text-red font-bold' : ''}`}>
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

                {/* OD Grinding Column */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl">OD Grinding</th></tr>
                            <tr><th>Machine</th><th>STD BOX</th><th>2nd</th><th>3rd</th></tr>
                        </thead>
                        <tbody>
                            {scheduleData.od_grinding.map((machineGroup, idx) => (
                                <React.Fragment key={`od-${idx}`}>
                                    <tr className="machine-header"><th colSpan="4" className="text-left pl-2 text-blue">{machineGroup.machine}</th></tr>
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

                {/* Heat Treatment Column */}
                <div className="schedule-col">
                    <table className="excel-table full-width">
                        <thead>
                            <tr><th colSpan="4" className="text-blue font-xl">HEAT TREATMENT</th></tr>
                            <tr><th>Furnace</th><th>QTY</th><th>Cha</th><th>Rate</th></tr>
                        </thead>
                        <tbody>
                            {scheduleData.heat_treatment.map((furnaceGroup, idx) => (
                                <React.Fragment key={`ht-${idx}`}>
                                    <tr className="machine-header">
                                        <th className="text-left pl-2 text-blue">{furnaceGroup.furnace}</th>
                                        <th colSpan="3" className="text-right pr-2 text-blue">Cap: {furnaceGroup.capacity} kg/hr</th>
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

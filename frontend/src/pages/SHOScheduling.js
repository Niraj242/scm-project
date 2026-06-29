import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  // Navigation Routing States
  const [activeTab, setActiveTab] = useState('buffer'); // 'buffer' or 'schedule'
  
  // View State Variables - Buffer Entry Status
  const [sector, setSector] = useState('DGBB');
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  const [tableData, setTableData] = useState({});
  const [unlockedBlocks, setUnlockedBlocks] = useState([]); 
  const [isSaving, setIsSaving] = useState(false);

  // View State Variables - Standalone Production Scheduler Tab
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);

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

  const handleInputChange = (rowKey, col, subCol, value) => {
    setTableData(prev => ({ ...prev, [`${rowKey}_${col}_${subCol}`]: value }));
  };

  const handleSaveBufferOnly = () => {
    setIsSaving(true);
    const payload = { entries: tableData, unlocked: unlockedBlocks };
    localStorage.setItem(`sho_db_${sector}_${bufferDate}`, JSON.stringify(payload));
    setTimeout(() => {
      setIsSaving(false);
      alert("Shop Floor Buffer Data Saved Locally.");
    }, 300);
  };

  // Dedicated API workflow for generating calculations in the separate tab
  const handleExecuteEngineSchedule = async () => {
    setIsGeneratingPlan(true);
    const API = 'https://scm-backend-pshv.onrender.com';
    
    try {
      const response = await fetch(`${API}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sector: sector,
          date: scheduleDate,
          unit_mode: unitMode,
          entries: tableData,
          unlocked_blocks: unlockedBlocks
        })
      });

      const result = await response.json();
      if (response.ok) {
        setScheduleData(result.data);
      } else {
        alert("Automation engine warning: " + (result.detail || "Calculation error"));
      }
    } catch (error) {
      console.error("Connection link severed:", error);
      alert(`Unable to access production server at: ${API}`);
    } finally {
      setIsGeneratingPlan(false);
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
    return DEFAULT_BLOCKED[sector]?.[section]?.[col]?.includes(subCol) && !unlockedBlocks.includes(`${sector}_${section}_${col}_${subCol}`);
  };

  return (
    <div className="sho-container">
      
      {/* Master Layout Navigation Controls */}
      <div className="tab-header-row">
        <button className={`nav-tab-btn ${activeTab === 'buffer' ? 'tab-active' : ''}`} onClick={() => setActiveTab('buffer')}>
          📊 1. Shop Buffer Status Entry
        </button>
        <button className={`nav-tab-btn ${activeTab === 'schedule' ? 'tab-active' : ''}`} onClick={() => setActiveTab('schedule')}>
          ⚙️ 2. Production Schedule Tab View
        </button>
      </div>

      {/* VIEW PANEL 1: BUFFER STATUS MANAGEMENT */}
      {activeTab === 'buffer' && (
        <div className="view-panel-wrapper">
          <div className="controls-panel">
            <div className="control-group">
              <label>Sector Segment:</label>
              <select value={sector} onChange={(e) => setSector(e.target.value)}>
                <option value="DGBB">DGBB</option>
                <option value="TRB">TRB</option>
                <option value="HUB">HUB</option>
              </select>
            </div>
            <div className="control-group">
              <label>Target Date:</label>
              <input type="date" value={bufferDate} onChange={(e) => setBufferDate(e.target.value)} />
            </div>
            <div className="control-group">
              <label>Entry Unit Metric:</label>
              <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
                <option value="Days">Buffer Days</option>
                <option value="Boxes">Boxes</option>
                <option value="Rings">No. of Rings</option>
              </select>
            </div>
            <button className="btn-save" onClick={handleSaveBufferOnly} disabled={isSaving}>
              {isSaving ? "Persisting..." : "Save Shop Buffer Matrix"}
            </button>
          </div>

          <div className="table-scroll-container">
            <table className="excel-table">
              <thead>
                <tr>
                  <th colSpan="3" className="text-blue text-left pl-2">SKF INDIA LTD.</th>
                  <th colSpan={totalCols - 6} className="text-blue">
                    CHANNEL BUFFER STATUS ASSESSMENT GRID<br/>{sector === 'DGBB' ? 'DBBB' : sector}
                  </th>
                  <th colSpan="3" className="text-blue text-right pr-2">
                    DATE GRID :- {bufferDate.split('-').reverse().join('/')}
                  </th>
                </tr>
                <tr className="header-row">
                  <th className="text-blue border-thick-right border-thick-bottom" style={{minWidth: '110px'}}>CHANNEL</th>
                  {columns.map(col => (
                    <th key={col} colSpan="2" className="text-blue column-title border-thick-right border-thick-bottom">{col}</th>
                  ))}
                </tr>
                <tr className="subheader-row">
                  <th className="font-bold border-thick-right border-thick-bottom">PART VARIANT</th>
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
                            <td className="input-cell">
                              <input type="text" value={tableData[`${row.key}_${col}_IR`] || ''} onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}/>
                            </td>
                          )}
                          {orBlocked ? (
                            row.sectionIndex === 0 ? <td rowSpan={4} className="disabled-block border-thick-right" onDoubleClick={() => unlockBlock(row.section, col, 'OR')}></td> : null
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
        </div>
      )}

      {/* VIEW PANEL 2: STANDALONE PRODUCTION DISPATCH MASTER SCHEDULE */}
      {activeTab === 'schedule' && (
        <div className="view-panel-wrapper schedule-view-panel">
          <div className="controls-panel">
            <div className="control-group">
              <label>Select Execution Schedule Date:</label>
              <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
            </div>
            <button className="btn-generate-plan" onClick={handleExecuteEngineSchedule} disabled={isGeneratingPlan}>
              {isGeneratingPlan ? "Parsing Calculations & Constraints..." : "⚡ Generate Shop Production Schedule"}
            </button>
          </div>

          {scheduleData ? (
            <div className="schedule-layout-output">
              <h2 className="schedule-main-title">SHOP-FLOOR LIVE PRODUCTION ROUTING AND SEQUENCING BATCH MAP</h2>
              
              <div className="process-flow-grid">
                
                {/* FLOW SECTION 1: HEAT TREATMENT FURNACES */}
                <div className="process-card-column">
                  <div className="process-header-banner banner-ht">🔥 1. Heat Treatment Furnaces (2-Day Batched)</div>
                  <table className="schedule-excel-grid">
                    <thead>
                      <tr>
                        <th>Assigned Furnace</th>
                        <th>Type Family / Part</th>
                        <th>Boxes Count</th>
                        <th>Routing Batch Context</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scheduleData.heat_treatment.length === 0 && <tr><td colSpan="4" className="empty-alert">No components scheduled for Furnace processing</td></tr>}
                      {scheduleData.heat_treatment.map((furnaceBlock, fIdx) => (
                        <React.Fragment key={`f-block-${fIdx}`}>
                          <tr className="resource-identifier-row"><td colSpan="4">{furnaceBlock.furnace}</td></tr>
                          {furnaceBlock.rows.map((row, rIdx) => (
                            <tr key={`f-row-${rIdx}`}>
                              <td className="resource-sub-label">Active Matrix</td>
                              <td className="font-bold text-left text-dark-blue">{row.part}</td>
                              <td className="font-bold text-center text-green">{row.qty} Boxes</td>
                              <td><span className={`badge ${row.batch_type.includes('2-Day') ? 'badge-orange' : 'badge-blue'}`}>{row.batch_type}</span></td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* FLOW SECTION 2: FACE GRINDING PROCESS */}
                <div className="process-card-column">
                  <div className="process-header-banner banner-face">🔲 2. Face Grinding Line (Post-HT Operations)</div>
                  <table className="schedule-excel-grid">
                    <thead>
                      <tr>
                        <th>Machine Asset</th>
                        <th>Type Family / Part</th>
                        <th>Required Boxes</th>
                        <th>Execution Sequence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scheduleData.face_grinding.length === 0 && <tr><td colSpan="4" className="empty-alert">No components assigned to Face Grinding lines</td></tr>}
                      {scheduleData.face_grinding.map((mBlock, mIdx) => (
                        <React.Fragment key={`face-m-${mIdx}`}>
                          <tr className="resource-identifier-row"><td colSpan="4">{mBlock.machine}</td></tr>
                          {mBlock.rows.map((row, rIdx) => (
                            <tr key={`face-r-${rIdx}`}>
                              <td className="resource-sub-label">Active Line</td>
                              <td className="font-bold text-left text-dark-blue">{row.part}</td>
                              <td className="font-bold text-center">{row.std_box} Boxes</td>
                              <td><span className="badge badge-purple">{row.sequence}</span></td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* FLOW SECTION 3: OD GRINDING LINE SEQUENCING */}
                <div className="process-card-column">
                  <div className="process-header-banner banner-od">🌀 3. OD Grinding Line (Strict Post-Face Constraint)</div>
                  <table className="schedule-excel-grid">
                    <thead>
                      <tr>
                        <th>Machine Asset</th>
                        <th>Type Family / Part</th>
                        <th>Required Boxes</th>
                        <th>Interlocking Dependency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scheduleData.od_grinding.length === 0 && <tr><td colSpan="4" className="empty-alert">No components assigned to OD Grinding lines</td></tr>}
                      {scheduleData.od_grinding.map((mBlock, mIdx) => (
                        <React.Fragment key={`od-m-${mIdx}`}>
                          <tr className="resource-identifier-row"><td colSpan="4">{mBlock.machine}</td></tr>
                          {mBlock.rows.map((row, rIdx) => (
                            <tr key={`od-r-${rIdx}`}>
                              <td className="resource-sub-label">Active Line</td>
                              <td className="font-bold text-left text-dark-blue">{row.part}</td>
                              <td className="font-bold text-center">{row.std_box} Boxes</td>
                              <td><span className="badge badge-red-border">⚠️ {row.status}</span></td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

              </div>
            </div>
          ) : (
            <div className="schedule-placeholder-prompt">
              <div className="prompt-art">⚙️</div>
              <h3>Production Schedule Visualizer Isolated Panel</h3>
              <p>Select your manufacturing target planning date using the control panel above and click <strong>Generate Shop Production Schedule</strong> to invoke the live matrix configuration algorithm.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;

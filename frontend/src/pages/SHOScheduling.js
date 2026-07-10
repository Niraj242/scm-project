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
  const [unlockedBlocks, setUnlockedBlocks] = useState([]);
  
  // Tab 3: Schedule State
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);
  const [isSavingPlan, setIsSavingPlan] = useState(false);

  // Tab 4: Summary State
  const [summaryDate, setSummaryDate] = useState(new Date().toISOString().split('T')[0]);
  const [summaryData, setSummaryData] = useState([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  // Tab 2: Machine Availability State
  const [machineAvailability, setMachineAvailability] = useState({});
  const [machinesList, setMachinesList] = useState([]);
  const [isLoadingMachines, setIsLoadingMachines] = useState(false);

  // -- CONSTANTS --
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  const DEFAULT_BLOCKED = {
    'T 4': { 'IR': ['OD'], 'OR': [] },
    'T 5': { 'IR': ['FACE', 'OD'], 'OR': ['FACE', 'OD'] },
    'T 6': { 'IR': ['FACE', 'OD'], 'OR': ['FACE', 'OD'] }
  };

  // -- EFFECTS --
  useEffect(() => {
    if (activeTab === 'availability' && machinesList.length === 0) {
      fetchMachines();
    }
    if (activeTab === 'summary' && summaryData.length === 0) {
      fetchSummary();
    }
  }, [activeTab]);

  // -- API CALLS --
  const fetchMachines = async () => {
    setIsLoadingMachines(true);
    try {
      const response = await fetch(`${API_BASE}/api/machines`);
      const result = await response.json();
      if (result.status === 'success') {
        setMachinesList(result.data || []);
      }
    } catch (error) {
      console.error('Error fetching machines:', error);
    }
    setIsLoadingMachines(false);
  };

  const fetchSummary = async () => {
    setIsLoadingSummary(true);
    try {
      const payload = {
        sector,
        date: summaryDate,
        unit_mode: unitMode,
        entries: tableData,
        unlocked_blocks: unlockedBlocks,
        machine_availability: machineAvailability
      };
      
      const response = await fetch(`${API_BASE}/api/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        setSummaryData(result.data || []);
      } else {
        alert('Failed to generate summary: ' + result.detail);
      }
    } catch (error) {
      console.error('Error fetching summary:', error);
      alert('Error fetching summary. Check console.');
    }
    setIsLoadingSummary(false);
  };

  const generatePlan = async () => {
    setIsLoadingPlan(true);
    try {
      const payload = {
        sector,
        date: scheduleDate,
        unit_mode: unitMode,
        entries: tableData,
        unlocked_blocks: unlockedBlocks,
        machine_availability: machineAvailability
      };
      
      const response = await fetch(`${API_BASE}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        setScheduleData(result.data);
      } else {
        alert('Failed to generate plan: ' + result.detail);
      }
    } catch (error) {
      console.error('Error generating plan:', error);
      alert('Error connecting to backend.');
    }
    setIsLoadingPlan(false);
  };

  const savePlan = async () => {
    if (!scheduleData) return;
    setIsSavingPlan(true);
    try {
      const payload = {
        date: scheduleDate,
        plan: scheduleData
      };
      
      const response = await fetch(`${API_BASE}/api/save_plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        alert('Daily plan saved successfully!');
        if (activeTab === 'summary') fetchSummary(); // Refresh summary if needed
      } else {
        alert('Failed to save plan: ' + result.detail);
      }
    } catch (error) {
      console.error('Error saving plan:', error);
      alert('Error saving plan. Check console.');
    }
    setIsSavingPlan(false);
  };

  // -- HANDLERS --
  const handleBufferChange = (col, stage, side, val) => {
    const key = `${col}_${stage}_${side}`;
    setTableData(prev => ({
      ...prev,
      [key]: { disp: col, stage, side, val: val }
    }));
  };

  const handleAvailabilityChange = (machine, val) => {
    setMachineAvailability(prev => ({
      ...prev,
      [machine]: parseFloat(val) || 0
    }));
  };

  const getCellValue = (col, stage, side) => {
    const key = `${col}_${stage}_${side}`;
    return tableData[key] ? tableData[key].val : '';
  };

  const isCellBlocked = (col, stage, side) => {
    const defaultBlocked = DEFAULT_BLOCKED[col]?.[side]?.includes(stage);
    if (defaultBlocked) {
      const blockKey = `${col}_${stage}_${side}`;
      if (unlockedBlocks.includes(blockKey)) return false;
      return true;
    }
    return false;
  };

  const handleCellClick = (col, stage, side) => {
    const blockKey = `${col}_${stage}_${side}`;
    if (DEFAULT_BLOCKED[col]?.[side]?.includes(stage)) {
      setUnlockedBlocks(prev => 
        prev.includes(blockKey) ? prev.filter(k => k !== blockKey) : [...prev, blockKey]
      );
    }
  };

  // -- RENDERERS --
  const renderBufferGrid = () => {
    const cols = SECTOR_COLUMNS[sector] || [];
    return (
      <div className="table-scroll-container">
        <table className="excel-table">
          <thead>
            <tr>
              <th className="row-label border-thick-right border-thick-bottom" rowSpan={2} style={{ minWidth: '120px' }}>Channels</th>
              {cols.map(col => (
                <th key={col} colSpan={2} className="border-thick-right text-blue font-bold">{col}</th>
              ))}
            </tr>
            <tr>
              {cols.map(col => (
                <React.Fragment key={`${col}-headers`}>
                  <th className="font-bold">IR</th>
                  <th className="border-thick-right font-bold">OR</th>
                </React.Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {['FACE', 'OD', 'HT', 'CH'].map((stage, stageIndex) => (
              <React.Fragment key={stage}>
                <tr>
                  <td className="row-label border-thick-right font-bold text-left pl-2">
                    {stage === 'HT' ? 'HT' : stage === 'CH' ? 'CHANNEL' : `${stage} GRD`}
                  </td>
                  {cols.map(col => (
                    <React.Fragment key={`${col}-${stage}`}>
                      <td className={`input-cell ${isCellBlocked(col, stage, 'IR') ? 'disabled-block' : ''}`}
                          onDoubleClick={() => handleCellClick(col, stage, 'IR')}>
                        {!isCellBlocked(col, stage, 'IR') && (
                          <input type="text"
                                 value={getCellValue(col, stage, 'IR')}
                                 onChange={(e) => handleBufferChange(col, stage, 'IR', e.target.value)} />
                        )}
                      </td>
                      <td className={`input-cell border-thick-right ${isCellBlocked(col, stage, 'OR') ? 'disabled-block' : ''}`}
                          onDoubleClick={() => handleCellClick(col, stage, 'OR')}>
                        {!isCellBlocked(col, stage, 'OR') && (
                          <input type="text"
                                 value={getCellValue(col, stage, 'OR')}
                                 onChange={(e) => handleBufferChange(col, stage, 'OR', e.target.value)} />
                        )}
                      </td>
                    </React.Fragment>
                  ))}
                </tr>
                {stageIndex < 3 && <tr className="spacer-row"><td colSpan={cols.length * 2 + 1}></td></tr>}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderScheduleGrid = (title, dataKey, machineKey) => {
    if (!scheduleData || !scheduleData[dataKey] || scheduleData[dataKey].length === 0) return null;
    return (
      <div className="schedule-column">
        <div className="col-main-title border-thick-bottom border-thick-right font-bold">{title}</div>
        <table className="img-table sticky-header-table">
          <thead>
            <tr className="sticky-row-1">
              {machineKey === 'furnace' ? (
                <>
                  <th style={{ width: '40%' }}>Furnace</th>
                  <th style={{ width: '20%' }}>Part/Fam</th>
                  <th style={{ width: '15%' }}>Qty</th>
                  <th style={{ width: '25%' }}>Timing</th>
                </>
              ) : (
                <>
                  <th style={{ width: '25%' }}>Machine</th>
                  <th style={{ width: '20%' }}>Part/Fam</th>
                  <th style={{ width: '20%' }}>Channel</th>
                  <th style={{ width: '15%' }}>Qty</th>
                  <th style={{ width: '20%' }}>Timing</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {scheduleData[dataKey].map((m_data, m_idx) => {
              if (!m_data.rows || m_data.rows.length === 0) return null;
              return m_data.rows.map((row, r_idx) => (
                <tr key={`${m_idx}-${r_idx}`}>
                  {r_idx === 0 && (
                    <td rowSpan={m_data.rows.length} className="machine-name-row font-bold text-blue">
                      {m_data[machineKey]}
                      {m_data.capacity && <div style={{ fontSize: '10px', color: '#666', marginTop: '4px' }}>{m_data.capacity}</div>}
                    </td>
                  )}
                  <td className="part-name">{row.part}</td>
                  {machineKey !== 'furnace' && <td className="center-text">{row.channel}</td>}
                  <td className="center-text text-blue">
                    {row.qty}
                    <div style={{ fontSize: '10px', color: '#666' }}>{row.rate}</div>
                  </td>
                  <td className="center-text">{row.timing}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="sho-container">
      <div className="tab-buttons">
        <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Initial Buffers</button>
        <button className={activeTab === 'availability' ? 'active' : ''} onClick={() => setActiveTab('availability')}>2. Machine Availability</button>
        <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>3. Master Plan</button>
        <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')}>4. Requirement Summary</button>
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
              <label>Input Unit:</label>
              <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
                <option value="Days">Days</option>
                <option value="Boxes">Boxes</option>
                <option value="Rings">Rings</option>
              </select>
            </div>
            <button className="btn-save" onClick={() => setActiveTab('schedule')}>Next: Generate Plan ➔</button>
          </div>
          {renderBufferGrid()}
        </>
      )}

      {activeTab === 'availability' && (
        <div style={{ background: 'white', padding: '20px', borderRadius: '4px', border: '1px solid #aaa', flexGrow: 1, overflow: 'auto' }}>
          <h2 style={{ color: '#004085', marginTop: 0 }}>Log Machine Unavailability (Hours)</h2>
          <p style={{ color: '#555', fontSize: '14px', marginBottom: '20px' }}>Enter the number of hours a machine is NOT available today (e.g., maintenance, breakdowns). Leave blank if fully available.</p>
          
          {isLoadingMachines ? (
            <div style={{ padding: '20px', fontWeight: 'bold' }}>Loading Master Machines...</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '15px' }}>
              {machinesList.map((machine) => (
                <div key={machine} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px', border: '1px solid #ccc', borderRadius: '4px', backgroundColor: '#f8f9fa' }}>
                  <span style={{ fontWeight: 'bold', fontSize: '14px', color: '#333' }}>{machine}</span>
                  <input 
                    type="number" 
                    min="0" max="24" step="0.5"
                    placeholder="Hrs Blocked"
                    style={{ width: '100px', padding: '6px', border: '1px solid #0056b3', borderRadius: '3px', textAlign: 'center' }}
                    value={machineAvailability[machine] === 0 ? '' : (machineAvailability[machine] || '')}
                    onChange={(e) => handleAvailabilityChange(machine, e.target.value)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Plan Date:</label>
              <input type="date" value={summaryDate} onChange={(e) => setSummaryDate(e.target.value)} />
            </div>
            <button className="btn-save" onClick={fetchSummary} disabled={isLoadingSummary}>
              {isLoadingSummary ? 'Loading...' : 'Refresh Summary'}
            </button>
          </div>
          
          <div className="table-scroll-container" style={{ flexGrow: 1, background: 'white', padding: '15px' }}>
            <table className="excel-table" style={{ width: '100%', minWidth: '900px' }}>
              <thead>
                <tr style={{ backgroundColor: '#eef8ff', borderBottom: '2px solid #0056b3' }}>
                  <th style={{ padding: '10px', color: '#004085' }}>Part Type</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Channel</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Monthly Req.</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Today's Req.</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Today's Prod.</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Difference (+/-)</th>
                  <th style={{ padding: '10px', color: '#004085' }}>MTD Prod.</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Balance</th>
                  <th style={{ padding: '10px', color: '#004085' }}>Rem. %</th>
                </tr>
              </thead>
              <tbody>
                {summaryData.length === 0 ? (
                  <tr><td colSpan="9" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>Click "Refresh Requirement Summary" to fetch the Master ZEROSET plan for the selected date.</td></tr>
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

      {activeTab === 'schedule' && (
        <>
          <div className="controls-panel" style={{ justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', gap: '15px' }}>
              <div className="control-group">
                <label>Plan Date:</label>
                <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
              </div>
              <button className="btn-save" style={{ marginLeft: '0' }} onClick={generatePlan} disabled={isLoadingPlan}>
                {isLoadingPlan ? 'Generating...' : 'Generate Master Plan'}
              </button>
            </div>
            
            <button className="btn-save" style={{ backgroundColor: '#28a745', borderColor: '#1e7e34' }} onClick={savePlan} disabled={!scheduleData || isSavingPlan}>
                {isSavingPlan ? 'Saving...' : '💾 Save Daily Plan'}
            </button>
          </div>

          {scheduleData && (
            <div className="table-scroll-container image-layout-container">
              <div className="schedule-master-header">
                <div>SHO DAILY MASTER PRODUCTION PLAN</div>
                <div>DATE: {scheduleDate.split('-').reverse().join('-')}</div>
              </div>

              <div className="schedule-grid-wrapper">
                {renderScheduleGrid('FACE GRINDING', 'face_grinding', 'machine')}
                {renderScheduleGrid('OD GRINDING', 'od_grinding', 'machine')}
                {renderScheduleGrid('HEAT TREATMENT', 'heat_treatment', 'furnace')}
              </div>

              {scheduleData.unscheduled && scheduleData.unscheduled.length > 0 && (
                <div style={{ padding: '15px', borderTop: '3px solid #0056b3' }}>
                    <h3 style={{ color: '#cc0000', marginTop: 0, marginBottom: '10px' }}>⚠️ Unscheduled Parts (Capacity/Missing Data)</h3>
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

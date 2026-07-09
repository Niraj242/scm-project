import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer'); 
  const [sector, setSector] = useState('DGBB');
  
  const [bufferDate, setBufferDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  
  const [tableData, setTableData] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  
  const [scheduleDate, setScheduleDate] = useState(new Date().toISOString().split('T')[0]);
  const [scheduleData, setScheduleData] = useState(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);
  const [isSavingPlan, setIsSavingPlan] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [machineConstraints, setMachineConstraints] = useState([]);

  // -- CONSTANTS --
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2']
  };

  const BUFFER_ROWS = [
    { label: 'Type', key: 'type_1' },
    { label: 'CH Buffer', key: 'ch_buffer_1' },
    { label: 'Next Type', key: 'next_type_1' },
    { label: 'CH Buffer 2', key: 'ch_buffer_2' },
    { label: 'Type', key: 'type_2' },
    { label: 'OD Buffer 1', key: 'od_buffer_1' },
    { label: 'Next Type', key: 'next_type_2' },
    { label: 'OD Buffer 2', key: 'od_buffer_2' },
    { label: 'Type', key: 'type_3' },
    { label: 'Face Buffer 1', key: 'face_buffer_1' },
    { label: 'Type', key: 'type_4' },
    { label: 'Face Buffer 2', key: 'face_buffer_2' },
  ];

  // -- HANDLERS --
  const handleInputChange = (key, value) => {
    setTableData(prev => ({ ...prev, [key]: value }));
  };

  const addMachineConstraint = () => {
    setMachineConstraints(prev => [
      ...prev,
      { id: Date.now(), machine: '', enabled: true, off_whole_day: false, start_time: '', end_time: '' }
    ]);
  };

  const updateMachineConstraint = (id, field, value) => {
    setMachineConstraints(prev => prev.map(c => (c.id === id ? { ...c, [field]: value } : c)));
  };

  const removeMachineConstraint = (id) => {
    setMachineConstraints(prev => prev.filter(c => c.id !== id));
  };

  const handleGeneratePlan = async () => {
    setIsLoadingPlan(true);
    setScheduleData(null);

    const machine_availability = {};
    machineConstraints.forEach(c => {
      if (c.machine.trim()) {
        machine_availability[c.machine.trim()] = {
          enabled: c.enabled,
          off_whole_day: c.off_whole_day,
          start_time: c.start_time,
          end_time: c.end_time
        };
      }
    });

    const payload = {
      sector,
      date: scheduleDate,
      unit_mode: unitMode,
      entries: tableData,
      unlocked_blocks: [],
      machine_availability
    };

    try {
      const response = await fetch('/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (data.status === 'success') {
        setScheduleData(data.data);
      } else {
        alert('Error generating plan: ' + data.detail);
      }
    } catch (error) {
      alert('Error connecting to server.');
      console.error(error);
    }
    setIsLoadingPlan(false);
  };

  const handleSavePlan = async () => {
    if (!scheduleData) return;
    setIsSavingPlan(true);
    
    const planToSave = {
      face: scheduleData.face_grinding || [],
      od: scheduleData.od_grinding || [],
      ht: scheduleData.heat_treatment || []
    };

    const payload = {
      date: scheduleDate,
      plan: planToSave
    };

    try {
      const response = await fetch('/api/save_plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (result.status === 'success') {
        alert('Production Plan saved successfully. Future schedules will continue from these timings.');
      } else {
        alert('Error saving plan: ' + result.detail);
      }
    } catch (error) {
      alert('Error connecting to server.');
      console.error(error);
    }
    setIsSavingPlan(false);
  };

  const renderBufferGrid = () => {
    const columns = SECTOR_COLUMNS[sector] || [];
    return (
      <div className="grid-wrapper" style={{ overflowX: 'auto', marginTop: '10px' }}>
        <table className="img-table" style={{ minWidth: '1200px' }}>
          <thead>
            <tr>
              <th rowSpan={2} style={{ width: '120px', backgroundColor: '#eef8ff' }}>Buffer Name</th>
              {columns.map(col => (
                <th colSpan={2} key={col} style={{ backgroundColor: '#eef8ff', textAlign: 'center' }}>{col}</th>
              ))}
            </tr>
            <tr>
              {columns.map(col => (
                <React.Fragment key={`${col}-sub`}>
                  <th style={{ backgroundColor: '#f9f9f9', width: '80px' }}>IR</th>
                  <th style={{ backgroundColor: '#f9f9f9', width: '80px' }}>OR</th>
                </React.Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {BUFFER_ROWS.map(row => (
              <tr key={row.key}>
                <td style={{ fontWeight: 'bold', backgroundColor: '#f9f9f9' }}>{row.label}</td>
                {columns.map(col => (
                  <React.Fragment key={`${row.key}-${col}`}>
                    <td>
                      <input 
                        type={row.key.includes('type') ? "text" : "number"} 
                        value={tableData[`${row.key}_${col}_IR`] || ''}
                        onChange={(e) => handleInputChange(`${row.key}_${col}_IR`, e.target.value)}
                        style={{ width: '100%', boxSizing: 'border-box', padding: '4px' }}
                      />
                    </td>
                    <td>
                      <input 
                        type={row.key.includes('type') ? "text" : "number"} 
                        value={tableData[`${row.key}_${col}_OR`] || ''}
                        onChange={(e) => handleInputChange(`${row.key}_${col}_OR`, e.target.value)}
                        style={{ width: '100%', boxSizing: 'border-box', padding: '4px' }}
                      />
                    </td>
                  </React.Fragment>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderScheduleMachineBlock = (machineData, type) => {
    const idKey = type === 'HT' ? 'furnace' : 'machine';
    return (
      <table className="img-table" style={{ marginBottom: '20px' }}>
        <thead>
          <tr className="machine-name-row">
            <td colSpan={4} style={{ fontWeight: 'bold', padding: '8px' }}>
              {machineData[idKey]} {type === 'HT' ? `(${machineData.capacity})` : ''}
            </td>
          </tr>
          <tr className="sub-header">
            <th>Type</th>
            <th>{type === 'HT' ? 'Rate' : 'Std Box'}</th>
            <th>Timing</th>
            {type !== 'HT' && <th>Prog</th>}
          </tr>
        </thead>
        <tbody>
          {(!machineData.rows || machineData.rows.length === 0) ? (
            <tr>
              <td colSpan={4} style={{ textAlign: 'center', fontStyle: 'italic', color: '#888' }}>No jobs scheduled</td>
            </tr>
          ) : (
            machineData.rows.map((row, idx) => (
              <tr key={idx}>
                <td>{row.part}</td>
                <td>{type === 'HT' ? row.rate : row.std_box}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{row.timing}</td>
                {type !== 'HT' && <td>{row.p_label || ''}</td>}
              </tr>
            ))
          )}
        </tbody>
      </table>
    );
  };

  return (
    <div className="sho-container">
      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
        <button 
          onClick={() => setActiveTab('buffer')} 
          style={{ padding: '10px 20px', fontWeight: 'bold', cursor: 'pointer', backgroundColor: activeTab === 'buffer' ? '#0056b3' : '#ccc', color: activeTab === 'buffer' ? 'white' : 'black', border: 'none', borderRadius: '4px' }}
        >
          Buffer Entry
        </button>
        <button 
          onClick={() => setActiveTab('schedule')} 
          style={{ padding: '10px 20px', fontWeight: 'bold', cursor: 'pointer', backgroundColor: activeTab === 'schedule' ? '#0056b3' : '#ccc', color: activeTab === 'schedule' ? 'white' : 'black', border: 'none', borderRadius: '4px' }}
        >
          Production Schedule
        </button>
        <button 
          onClick={() => setActiveTab('summary')} 
          style={{ padding: '10px 20px', fontWeight: 'bold', cursor: 'pointer', backgroundColor: activeTab === 'summary' ? '#0056b3' : '#ccc', color: activeTab === 'summary' ? 'white' : 'black', border: 'none', borderRadius: '4px' }}
        >
          Production Summary
        </button>
      </div>

      {activeTab === 'buffer' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
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
              <label>Unit Mode:</label>
              <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
                <option value="Days">Days</option>
                <option value="Boxes">Boxes</option>
                <option value="Pieces">Pieces</option>
              </select>
            </div>
          </div>
          {renderBufferGrid()}
        </div>
      )}

      {activeTab === 'schedule' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
          <div className="controls-panel">
            <div className="control-group">
              <label>Date:</label>
              <input type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} />
            </div>
            <button className="btn-save" onClick={() => setShowSettings(!showSettings)} style={{ backgroundColor: '#17a2b8', borderColor: '#117a8b', marginRight: '10px' }}>
              {showSettings ? 'Hide Machine Settings' : 'Machine Availability Settings'}
            </button>
            <button className="btn-save" onClick={handleGeneratePlan} disabled={isLoadingPlan}>
              {isLoadingPlan ? 'Generating...' : 'Generate Plan'}
            </button>
            {scheduleData && (
              <button className="btn-save" onClick={handleSavePlan} disabled={isSavingPlan} style={{ marginLeft: 'auto', backgroundColor: '#28a745', borderColor: '#1e7e34' }}>
                {isSavingPlan ? 'Saving Plan...' : 'Save Production Plan'}
              </button>
            )}
          </div>

          {showSettings && (
            <div style={{ backgroundColor: 'white', padding: '15px', border: '1px solid #aaa', marginBottom: '15px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
              <h3 style={{ margin: '0 0 10px 0', color: '#004085' }}>Machine Availability Configuration</h3>
              <p style={{ fontSize: '12px', color: '#666', marginBottom: '10px' }}>Specify machines or furnaces to block them during specific times or disable entirely. (e.g., ID: "AICHELIN.(896)" or "BG_1")</p>
              
              <table className="img-table" style={{ width: 'auto', marginBottom: '10px' }}>
                <thead>
                  <tr className="sub-header">
                    <th>Machine ID</th>
                    <th>Enabled</th>
                    <th>Whole Day OFF</th>
                    <th>Start Time (HH:MM)</th>
                    <th>End Time (HH:MM)</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {machineConstraints.length === 0 ? (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '10px' }}>No blocks configured.</td></tr>
                  ) : (
                    machineConstraints.map((c) => (
                      <tr key={c.id}>
                        <td><input type="text" value={c.machine} onChange={(e) => updateMachineConstraint(c.id, 'machine', e.target.value)} placeholder="Machine Name" /></td>
                        <td style={{ textAlign: 'center' }}><input type="checkbox" checked={c.enabled} onChange={(e) => updateMachineConstraint(c.id, 'enabled', e.target.checked)} /></td>
                        <td style={{ textAlign: 'center' }}><input type="checkbox" checked={c.off_whole_day} onChange={(e) => updateMachineConstraint(c.id, 'off_whole_day', e.target.checked)} /></td>
                        <td><input type="text" value={c.start_time} onChange={(e) => updateMachineConstraint(c.id, 'start_time', e.target.value)} placeholder="10:00" disabled={!c.enabled || c.off_whole_day} /></td>
                        <td><input type="text" value={c.end_time} onChange={(e) => updateMachineConstraint(c.id, 'end_time', e.target.value)} placeholder="18:30" disabled={!c.enabled || c.off_whole_day} /></td>
                        <td style={{ textAlign: 'center' }}><button onClick={() => removeMachineConstraint(c.id)} style={{ color: 'red', cursor: 'pointer', border: 'none', background: 'none', fontWeight: 'bold' }}>X</button></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              <button onClick={addMachineConstraint} style={{ padding: '5px 10px', cursor: 'pointer' }}>+ Add Machine Block</button>
            </div>
          )}

          {scheduleData && (
            <div style={{ backgroundColor: 'white', padding: '15px', border: '1px solid #aaa', flex: 1, overflowY: 'auto' }}>
              <div className="schedule-grid-wrapper">
                <div className="schedule-column">
                  <div className="col-main-title">Face Grinding</div>
                  <div style={{ padding: '10px' }}>
                    {scheduleData.face_grinding && scheduleData.face_grinding.map((m, i) => (
                      <React.Fragment key={i}>
                        {renderScheduleMachineBlock(m, 'FACE')}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
                <div className="schedule-column">
                  <div className="col-main-title">OD Grinding</div>
                  <div style={{ padding: '10px' }}>
                    {scheduleData.od_grinding && scheduleData.od_grinding.map((m, i) => (
                      <React.Fragment key={i}>
                        {renderScheduleMachineBlock(m, 'OD')}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
                <div className="schedule-column">
                  <div className="col-main-title ht-title">Heat Treatment (Furnaces)</div>
                  <div style={{ padding: '10px' }}>
                    {scheduleData.heat_treatment && scheduleData.heat_treatment.map((m, i) => (
                      <React.Fragment key={i}>
                        {renderScheduleMachineBlock(m, 'HT')}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>

              {scheduleData.unscheduled && scheduleData.unscheduled.length > 0 && (
                <div style={{ marginTop: '20px', padding: '15px', border: '2px solid #ffcccc', backgroundColor: '#fff5f5' }}>
                    <h3 style={{ color: '#cc0000', margin: '0 0 10px 0' }}>Unscheduled Parts (Capacity/Missing Data)</h3>
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
        </div>
      )}

      {activeTab === 'summary' && (
        <div style={{ flex: 1, backgroundColor: 'white', padding: '20px', border: '1px solid #aaa', overflowY: 'auto' }}>
          <h2 style={{ color: '#004085', marginTop: 0 }}>Production Summary Dashboard</h2>
          {!scheduleData || !scheduleData.summary ? (
            <p style={{ color: '#666' }}>Please generate a schedule plan to view the production summary.</p>
          ) : (
            <table className="img-table" style={{ width: '100%', fontSize: '14px', textAlign: 'center' }}>
              <thead>
                <tr className="sub-header">
                  <th style={{ padding: '10px' }}>Type</th>
                  <th style={{ padding: '10px' }}>Channel</th>
                  <th style={{ padding: '10px' }}>Monthly Requirement</th>
                  <th style={{ padding: '10px' }}>Today's Requirement</th>
                  <th style={{ padding: '10px' }}>Today's Production</th>
                  <th style={{ padding: '10px' }}>Month-to-Date Production</th>
                  <th style={{ padding: '10px' }}>Balance</th>
                  <th style={{ padding: '10px' }}>Remaining %</th>
                  <th style={{ padding: '10px' }}>Difference</th>
                </tr>
              </thead>
              <tbody>
                {scheduleData.summary.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ padding: '15px', color: '#888' }}>No summary data available.</td>
                  </tr>
                ) : (
                  scheduleData.summary.map((row, idx) => (
                    <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? '#fff' : '#f9f9f9' }}>
                      <td style={{ fontWeight: 'bold', textAlign: 'left', paddingLeft: '10px' }}>{row.type}</td>
                      <td>{row.channel}</td>
                      <td>{row.monthly_req}</td>
                      <td>{row.today_req}</td>
                      <td style={{ color: '#0056b3', fontWeight: 'bold' }}>{row.today_prod}</td>
                      <td>{row.mtd_prod}</td>
                      <td>{row.balance}</td>
                      <td>
                        <span style={{ 
                          color: row.remaining_pct > 50 ? '#d39e00' : (row.remaining_pct > 0 ? '#28a745' : '#17a2b8'),
                          fontWeight: 'bold'
                        }}>
                          {row.remaining_pct}%
                        </span>
                      </td>
                      <td style={{ 
                        color: row.difference < 0 ? '#dc3545' : (row.difference > 0 ? '#28a745' : '#6c757d'), 
                        fontWeight: 'bold' 
                      }}>
                        {row.difference > 0 ? `+${row.difference}` : row.difference}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;

import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('2026-04-01'); // Standard Calendar Format
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [debugLogs, setDebugLogs] = useState([]);
  const [errorMessage, setErrorMessage] = useState(null);

  // Core Industrial State Vectors
  const [tempChangeFurnaces, setTempChangeFurnaces] = useState({
    "AICHELIN.(896)": false,
    "CASTLINK FURNACE( 1018 )": false,
    "ROLLER FURNACE ( 148 )": false,
    "SIMPLICITY FURNACE(1238)": false
  });
  
  const [overrideForm, setOverrideForm] = useState({
    machine_id: 'DDS (544)',
    priority_type: 'P1'
  });

  const handleFurnaceToggle = (furnaceKey) => {
    setTempChangeFurnaces(prev => ({ ...prev, [furnaceKey]: !prev[furnaceKey] }));
  };

  const computeMasterSchedule = async () => {
    setLoading(true); 
    setErrorMessage(null); 
    setScheduleData(null); 
    setDebugLogs([]);

    const constraintPayload = {
      target_date: targetDate,
      temp_change_furnaces: Object.keys(tempChangeFurnaces).filter(k => tempChangeFurnaces[k]),
      overrides: [
        {
          machine_id: overrideForm.machine_id,
          priority_type: overrideForm.priority_type
        }
      ]
    };

    try {
      const res = await fetch(`https://scm-backend-pshv.onrender.com/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(constraintPayload)
      });
      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
        setDebugLogs(json.logs || []);
      } else {
        setErrorMessage(json.detail || "Error connecting to execution engine.");
      }
    } catch (err) {
      setErrorMessage(`Network connection failure: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO Shop Floor Matrix Engine</h1>
          <p className="subtitle">Dynamic STD/HR Rate Calibration & Multi-Channel Sync</p>
        </div>
        <div className="action-block">
          <label>Plan Production Date:</label>
          <input 
            type="date" 
            value={targetDate} 
            onChange={(e) => setTargetDate(e.target.value)} 
            className="calendar-picker"
          />
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Analyzing Sheet Matrices...' : 'Compile Master Matrix'}
          </button>
        </div>
      </header>

      {/* OPERATIONS OVERRIDE CONTROL BOX */}
      <div className="overrides-panel">
        <div className="override-section">
          <h3>Furnace Heat Modification Triggers</h3>
          <div className="furnace-toggles">
            {Object.keys(tempChangeFurnaces).map((fName) => (
              <button 
                key={fName}
                type="button"
                className={`toggle-chip ${tempChangeFurnaces[fName] ? 'active' : ''}`}
                onClick={() => handleFurnaceToggle(fName)}
              >
                {fName.split('(')[0]} {tempChangeFurnaces[fName] ? '🔥 Temp Drop' : '🌤️ Stable'}
              </button>
            ))}
          </div>
        </div>

        <div className="override-section">
          <h3>Line Priority Override Bypass</h3>
          <div className="form-row">
            <select 
              value={overrideForm.machine_id} 
              onChange={(e) => setOverrideForm(prev => ({ ...prev, machine_id: e.target.value }))}
            >
              <option value="DDS (544)">DDS (544)</option>
              <option value="CL-46 Cell 1 ( 0661 + 1125 )">CL-46 Cell 1</option>
              <option value="CASTLINK FURNACE( 1018 )">Castlink Furnace</option>
            </select>
            <select 
              value={overrideForm.priority_type} 
              onChange={(e) => setOverrideForm(prev => ({ ...prev, priority_type: e.target.value }))}
            >
              <option value="P1">P1 (Immediate Run)</option>
              <option value="P2">P2 (Sequence After)</option>
              <option value="HOLD">HOLD Asset</option>
            </select>
          </div>
        </div>
      </div>

      {errorMessage && <div className="error-banner"><b>Pipeline Alert:</b> {errorMessage}</div>}

      {/* RE-ENGINEERED COMPILER LOG */}
      {debugLogs.length > 0 && (
        <div className="debug-panel">
          <h3>Data Sourcing Verification Log</h3>
          <ul>{debugLogs.map((log, i) => <li key={i}>⚙️ {log}</li>)}</ul>
        </div>
      )}

      {scheduleData && (
        <div className="shopfloor-layout-grid">
          {/* ZONE 1: FACE GRINDING */}
          <div className="process-zone-column">
            <h2 className="zone-header face-color">Face Grinding Matrix</h2>
            {Object.keys(scheduleData.face).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip face-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Component</th><th>Target Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.face[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Spindle Idle (No Demand)</td></tr>
                    ) : (
                      scheduleData.face[machine].map((j, idx) => (
                        <tr key={idx}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* ZONE 2: OD GRINDING */}
          <div className="process-zone-column">
            <h2 className="zone-header od-color">OD Grinding Matrix</h2>
            {Object.keys(scheduleData.od).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip od-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Component</th><th>Target Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.od[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Line Idle (No Demand)</td></tr>
                    ) : (
                      scheduleData.od[machine].map((j, idx) => (
                        <tr key={idx}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* ZONE 3: HEAT TREATMENT FURNACES */}
          <div className="process-zone-column">
            <h2 className="zone-header ht-color">Thermal Furnaces</h2>
            {Object.keys(scheduleData.ht).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip ht-strip"><span>{machine}</span></div>
                <table className="zone-data-table">
                  <thead><tr><th>Target Code</th><th>Net Qty</th><th>Load</th><th>Exit</th></tr></thead>
                  <tbody>
                    {scheduleData.ht[machine].length === 0 ? (
                      <tr><td colSpan="4" className="no-load-row">Furnace Cooled / Empty</td></tr>
                    ) : (
                      scheduleData.ht[machine].map((j, idx) => (
                        <tr key={idx}>
                          <td className="bold-txt">{j.job}</td>
                          <td className="center-txt qty-txt">{j.qty.toLocaleString()}</td>
                          <td className="center-txt text-muted">{j.start}h</td>
                          <td className="center-txt bold-txt">{j.end}h</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;

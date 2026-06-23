import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Overrides Configuration States
  const [tempChangeFurnaces, setTempChangeFurnaces] = useState({
    "AICHELIN.(896)": false, "CASTLINK FURNACE( 1018 )": false, "ROLLER FURNACE ( 148 )": false
  });
  
  const [overrides, setOverrides] = useState({ machine_id: 'DDS (544)', priority_type: '', before_job: '', after_job: '' });

  const handleFurnaceToggle = (furnace) => {
    setTempChangeFurnaces(prev => ({ ...prev, [furnace]: !prev[furnace] }));
  };

  const handleInputChange = (e) => {
    setOverrides({ ...overrides, [e.target.name]: e.target.value });
  };

  const computeMasterSchedule = async () => {
    setLoading(true); setErrorMessage(null); setScheduleData(null);

    const activeTempFurnaces = Object.keys(tempChangeFurnaces).filter(k => tempChangeFurnaces[k]);
    const constraintPayload = {
      target_date: targetDate,
      temp_change_furnaces: activeTempFurnaces,
      overrides: overrides.priority_type || overrides.before_job ? [{
        machine_id: overrides.machine_id,
        priority_type: overrides.priority_type || null,
        sequence_rules: overrides.before_job ? [{ before_job: overrides.before_job, after_job: overrides.after_job }] : []
      }] : []
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
      } else {
        setErrorMessage(json.detail || "Error connecting to execution engine.");
      }
    } catch (err) {
      setErrorMessage(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO Shop Floor Execution Matrix Dashboard</h1>
          <p className="subtitle">Buffer-to-Furnace Logic Engine (HT, Face, OD Routing)</p>
        </div>
        <div className="action-block">
          <label>Plan Date:</label>
          <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Executing Plan...' : 'Compile Master Matrix'}
          </button>
        </div>
      </header>

      {/* OVERRIDES & CONTROLS PANEL */}
      <div className="overrides-panel">
        <div className="override-section">
          <h3>Quenching Temp Change (+1.5hr Delay Override)</h3>
          <div className="furnace-toggles">
            {Object.keys(tempChangeFurnaces).map(f => (
              <label key={f} className={`toggle-chip ${tempChangeFurnaces[f] ? 'active' : ''}`}>
                <input type="checkbox" checked={tempChangeFurnaces[f]} onChange={() => handleFurnaceToggle(f)} /> {f.split('(')[0]}
              </label>
            ))}
          </div>
        </div>
        <div className="override-section">
          <h3>Manual Priority Routing</h3>
          <div className="form-row">
            <select name="machine_id" value={overrides.machine_id} onChange={handleInputChange}>
              <option value="DDS (544)">Face - DDS (544)</option>
              <option value="CL-46 Cell 2 ( 0945 + 0839 )">OD - Cell 2</option>
            </select>
            <input type="text" name="priority_type" placeholder="Force Top Priority Type (e.g. 6310)" onChange={handleInputChange} />
            <input type="text" name="before_job" placeholder="Force Job A..." onChange={handleInputChange} />
            <input type="text" name="after_job" placeholder="...Before Job B" onChange={handleInputChange} />
          </div>
        </div>
      </div>

      {errorMessage && <div className="error-banner">▲ <b>Backend Pipeline Alert:</b> {errorMessage}</div>}

      {scheduleData && (
        <div className="shopfloor-layout-grid">
          {/* ZONE 1: FACE GRINDING */}
          <div className="process-zone-column">
            <h2 className="zone-header face-color">Face Grinding Process</h2>
            {Object.keys(scheduleData.face).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip face-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Run</th><th>Shift</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.face[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Idle (No Demand)</td></tr>
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
            <h2 className="zone-header od-color">OD Grinding Process</h2>
            {Object.keys(scheduleData.od).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip od-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Run</th><th>Shift</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.od[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Idle (No Demand)</td></tr>
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

          {/* ZONE 3: HEAT TREATMENT */}
          <div className="process-zone-column">
            <h2 className="zone-header ht-color">Heat Treatment Furnaces</h2>
            {Object.keys(scheduleData.ht).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip ht-strip"><span>{machine}</span></div>
                <table className="zone-data-table">
                  <thead><tr><th>Target Type</th><th>Net Qty</th><th>Start</th><th>Exit</th></tr></thead>
                  <tbody>
                    {scheduleData.ht[machine].length === 0 ? (
                      <tr><td colSpan="4" className="no-load-row">Furnace Cool</td></tr>
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

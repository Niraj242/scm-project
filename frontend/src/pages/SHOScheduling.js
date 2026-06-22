import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  
  const [tempChangeFurnaces, setTempChangeFurnaces] = useState({
    "AICHELIN_896": false,
    "CASTLINK_1018": false,
    "ROLLER_148": false,
    "SIMPLICITY_1238": false
  });

  const [overrides, setOverrides] = useState({
    machine_id: 'DDS (544)',
    priority_type: '',
    start_window: '',
    before_job: '',
    after_job: ''
  });

  const handleFurnaceToggle = (furnace) => {
    setTempChangeFurnaces(prev => ({ ...prev, [furnace]: !prev[furnace] }));
  };

  const handleInputChange = (e) => {
    setOverrides({ ...overrides, [e.target.name]: e.target.value });
  };

  const triggerScheduleGeneration = async () => {
    setLoading(true);
    const activeTempFurnaces = Object.keys(tempChangeFurnaces).filter(k => tempChangeFurnaces[k]);
    
    const constraintPayload = {
      target_date: targetDate,
      temp_change_furnaces: activeTempFurnaces,
      overrides: overrides.priority_type || overrides.before_job ? [{
        machine_id: overrides.machine_id,
        priority_type: overrides.priority_type || null,
        start_window: overrides.start_window || null,
        sequence_rules: overrides.before_job ? [{
          before_job: overrides.before_job,
          after_job: overrides.after_job
        }] : []
      }] : []
    };

    try {
      const res = await fetch(`${process.env.REACT_APP_API_BASE_URL}/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(constraintPayload)
      });
      const json = await res.json();
      if (json.status === "success") {
        setScheduleData(json.data);
      }
    } catch (err) {
      console.error("Error communicating with the optimization engine:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-dashboard">
      <header className="sho-main-header">
        <div>
          <h1>SHO Shopfloor Scheduling Console</h1>
          <p className="subtitle">Reverse-Engineered Capacity Optimization Engine</p>
        </div>
        <div className="date-picker-box">
          <label>Target Production Run Window:</label>
          <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </div>
      </header>

      <div className="sho-grid">
        {/* Input Parameters panel */}
        <div className="control-panel-card">
          <h2>1. Process Changeover Factors</h2>
          <p className="section-desc">Toggle furnaces requiring unique tempering rules (+1.5 Hrs Setup Adjustment):</p>
          
          <div className="furnace-selection-grid">
            {Object.keys(tempChangeFurnaces).map(f => (
              <label key={f} className={`furnace-chip ${tempChangeFurnaces[f] ? 'active' : ''}`}>
                <input type="checkbox" checked={tempChangeFurnaces[f]} onChange={() => handleFurnaceToggle(f)} />
                {f.replace('_', ' ')}
              </label>
            ))}
          </div>

          <hr className="divider" />

          <h2>2. Operational Overrides & Sequencing</h2>
          <div className="form-group">
            <label>Target Equipment:</label>
            <select name="machine_id" value={overrides.machine_id} onChange={handleInputChange}>
              <option value="DDS (544)">Face Grinding - DDS (544)</option>
              <option value="CL-46 (1125+661)">OD Grinding - CL-46 (1125+661)</option>
            </select>
          </div>

          <div className="form-group">
            <label>Force Priority Item Family:</label>
            <input type="text" name="priority_type" placeholder="e.g. 6310" onChange={handleInputChange} />
          </div>

          <div className="form-dual-row">
            <div className="form-group">
              <label>Sequence Rule: Job A</label>
              <input type="text" name="before_job" placeholder="e.g. 32212" onChange={handleInputChange} />
            </div>
            <div className="form-group">
              <label>Must Run Before: Job B</label>
              <input type="text" name="after_job" placeholder="e.g. 32215" onChange={handleInputChange} />
            </div>
          </div>

          <button className="execute-btn" onClick={triggerScheduleGeneration} disabled={loading}>
            {loading ? 'Recalculating Linear Timelines...' : 'Compute Production Sequences'}
          </button>
        </div>

        {/* Outputs Grid Visualization View */}
        <div className="results-display-panel">
          <h2>Active Compiled Floor Run-Sheet Output</h2>
          
          {!scheduleData && <div className="empty-state">Configure environment dependencies to resolve matrix parameters.</div>}

          {scheduleData && (
            <div className="schedule-tables-wrapper">
              <h3>Heat Treatment Department (Furnace Allocation)</h3>
              <table className="output-data-table">
                <thead>
                  <tr><th>Channel Origin</th><th>Family Target</th><th>Target Weight Volume</th><th>Assigned Unit</th><th>Load Entry (Hr)</th><th>Unload Exit (Hr)</th></tr>
                </thead>
                <tbody>
                  {scheduleData.heat_treatment.map((r, i) => (
                    <tr key={i}><td>{r.channel}</td><td><b>{r.family}</b></td><td>{r.quantity} pcs</td><td>{r.furnace}</td><td>{r.start}</td><td>{r.end}</td></tr>
                  ))}
                </tbody>
              </table>

              <h3>FOD Grinding Department (Face & OD Routing)</h3>
              <table className="output-data-table grinding-table">
                <thead>
                  <tr><th>Assigned Station</th><th>Operation Stage</th><th>Line Origin</th><th>Component Core</th><th>Start Timestamp</th><th>Completion Timeout</th></tr>
                </thead>
                <tbody>
                  {scheduleData.grinding.map((r, i) => (
                    <tr key={i}><td>{r.machine}</td><td><span className={`badge ${r.process.toLowerCase().replace(' ', '-')}`}>{r.process}</span></td><td>{r.channel}</td><td><b>{r.family}</b></td><td>{r.start} Hr</td><td>{r.end} Hr</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SHOScheduling;

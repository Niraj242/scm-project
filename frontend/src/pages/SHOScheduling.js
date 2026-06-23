import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null); 
  
  const [tempChangeFurnaces, setTempChangeFurnaces] = useState({
    "AICHELIN": false,
    "CASTLINK": false,
    "ROLLER": false,
    "SIMPLICITY": false
  });

  const [overrides, setOverrides] = useState({
    machine_id: 'DDS (544)',
    priority_type: '',
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
    setErrorMessage(null); 
    setScheduleData(null); 

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
      // ⚠️ USING YOUR EXACT RENDER URL TO PREVENT VERCEL 405 ERRORS
      const API = 'https://scm-backend-pshv.onrender.com';
      
      const res = await fetch(`${API}/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(constraintPayload)
      });
      
      // Safeguard: Check if the backend sent an HTML error page instead of JSON
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        const textError = await res.text();
        throw new Error(`Server returned non-JSON response. This usually means the endpoint doesn't exist on the live server yet. Status: ${res.status}`);
      }

      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
      } else {
        setErrorMessage(json.detail || "Unknown error occurred on the backend during processing.");
      }
    } catch (err) {
      console.error("Fetch Error:", err);
      setErrorMessage(`Connection Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-dashboard">
      <header className="sho-main-header">
        <div>
          <h1>SHO Shopfloor Scheduling Console</h1>
          <p className="subtitle">Full Logic Engine (HT, Face, OD & Batching Constraints)</p>
        </div>
        <div className="date-picker-box">
          <label>Target Production Window:</label>
          <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </div>
      </header>

      <div className="sho-grid">
        {/* Input Parameters panel */}
        <div className="control-panel-card">
          <h2>1. Process Changeover Factors</h2>
          <p className="section-desc">Toggle furnaces requiring Quenching Temp change (+1.5 Hrs Setup Adjustment):</p>
          
          <div className="furnace-selection-grid">
            {Object.keys(tempChangeFurnaces).map(f => (
              <label key={f} className={`furnace-chip ${tempChangeFurnaces[f] ? 'active' : ''}`}>
                <input type="checkbox" checked={tempChangeFurnaces[f]} onChange={() => handleFurnaceToggle(f)} />
                {f}
              </label>
            ))}
          </div>

          <hr className="divider" />

          <h2>2. Manual Overrides & Priorities</h2>
          <div className="form-group">
            <label>Target Equipment:</label>
            <select name="machine_id" value={overrides.machine_id} onChange={handleInputChange}>
              <option value="DDS (544)">Face Grinding - DDS (544)</option>
              <option value="CL-46 (1125+661)">OD Grinding - CL-46 (1125+661)</option>
            </select>
          </div>

          <div className="form-group">
            <label>Force Priority Type:</label>
            <input type="text" name="priority_type" placeholder="e.g. 6310" value={overrides.priority_type} onChange={handleInputChange} />
          </div>

          <div className="form-dual-row">
            <div className="form-group">
              <label>Run Job A:</label>
              <input type="text" name="before_job" placeholder="e.g. 32212" value={overrides.before_job} onChange={handleInputChange} />
            </div>
            <div className="form-group">
              <label>Before Job B:</label>
              <input type="text" name="after_job" placeholder="e.g. 32215" value={overrides.after_job} onChange={handleInputChange} />
            </div>
          </div>

          <button className="execute-btn" onClick={triggerScheduleGeneration} disabled={loading}>
            {loading ? 'Executing Scheduling Engine...' : 'Compute Production Sequences'}
          </button>

          {/* Error Display Box */}
          {errorMessage && (
            <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fee2e2', color: '#991b1b', borderRadius: '8px', border: '1px solid #f87171', fontSize: '13px', lineHeight: '1.5' }}>
              <strong>Error:</strong> {errorMessage}
            </div>
          )}
        </div>

        {/* Outputs Grid Visualization View */}
        <div className="results-display-panel">
          <h2>Active Compiled Floor Run-Sheet Output</h2>
          
          {!scheduleData && !errorMessage && <div className="empty-state">Ready to compute. Awaiting input...</div>}

          {scheduleData && (
            <div className="schedule-tables-wrapper">
              <h3>Heat Treatment Department (Furnace Allocation)</h3>
              <table className="output-data-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Family</th>
                    <th>Target Qty</th>
                    <th>Assigned Furnace</th>
                    <th>Load Entry (Hr)</th>
                    <th>Unload Exit (Hr)</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduleData.heat_treatment.map((r, i) => (
                    <tr key={i}>
                      <td>{r.channel}</td>
                      <td><b>{r.family}</b></td>
                      <td>{r.quantity.toLocaleString()} pcs</td>
                      <td><span className="badge furnace-badge">{r.furnace}</span></td>
                      <td>{r.start.toFixed(2)}</td>
                      <td>{r.end.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3>FOD Grinding Department (Dynamic Routing)</h3>
              <table className="output-data-table grinding-table">
                <thead>
                  <tr>
                    <th>Assigned Station</th>
                    <th>Operation Stage</th>
                    <th>Channel Origin</th>
                    <th>Component</th>
                    <th>Start Timestamp</th>
                    <th>Completion Timeout</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduleData.grinding.map((r, i) => (
                    <tr key={i}>
                      <td>{r.machine}</td>
                      <td><span className={`badge ${r.process.toLowerCase().replace(' ', '-')}`}>{r.process}</span></td>
                      <td>{r.channel}</td>
                      <td><b>{r.family}</b></td>
                      <td>{r.start.toFixed(2)} Hr</td>
                      <td>{r.end.toFixed(2)} Hr</td>
                    </tr>
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

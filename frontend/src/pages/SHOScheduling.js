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
      const API = 'https://scm-backend-pshv.onrender.com';
      
      const res = await fetch(`${API}/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(constraintPayload)
      });
      
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        const textError = await res.text();
        throw new Error(`Server returned non-JSON response. Status: ${res.status}`);
      }

      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        // Zip the data into a matrix format suitable for the Excel layout
        setScheduleData(buildMatrix(json.data));
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

  // This function structures the flat lists into a side-by-side row matrix
  const buildMatrix = (data) => {
    const faceJobs = data.grinding.filter(g => g.process === 'Face Grinding');
    const odJobs = data.grinding.filter(g => g.process === 'OD Grinding');
    
    const aichelinJobs = data.heat_treatment.filter(h => h.furnace.includes('AICHELIN'));
    const castlinkJobs = data.heat_treatment.filter(h => h.furnace.includes('CASTLINK'));
    const rollerJobs = data.heat_treatment.filter(h => h.furnace.includes('ROLLER'));

    // Find the longest column to know how many rows the master table needs
    const maxRows = Math.max(faceJobs.length, odJobs.length, aichelinJobs.length, castlinkJobs.length, rollerJobs.length);
    
    const rows = [];
    for (let i = 0; i < maxRows; i++) {
      rows.push({
        face: faceJobs[i] || null,
        od: odJobs[i] || null,
        aichelin: aichelinJobs[i] || null,
        castlink: castlinkJobs[i] || null,
        roller: rollerJobs[i] || null
      });
    }
    return rows;
  };

  return (
    <div className="sho-dashboard">
      <header className="sho-main-header">
        <div>
          <h1>SHO Shopfloor Scheduling Console</h1>
          <p className="subtitle">Master Matrix Layout</p>
        </div>
      </header>

      <div className="sho-grid-top">
        <div className="control-panel-card compact">
          <div className="date-picker-box inline-form">
            <label>Date:</label>
            <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </div>

          <div className="inline-form">
            <label>Temp Change (+1.5h):</label>
            <div className="furnace-selection-grid compact-grid">
              {Object.keys(tempChangeFurnaces).map(f => (
                <label key={f} className={`furnace-chip ${tempChangeFurnaces[f] ? 'active' : ''}`}>
                  <input type="checkbox" checked={tempChangeFurnaces[f]} onChange={() => handleFurnaceToggle(f)} />
                  {f}
                </label>
              ))}
            </div>
          </div>

          <button className="execute-btn small-btn" onClick={triggerScheduleGeneration} disabled={loading}>
            {loading ? 'Computing...' : 'Generate Matrix'}
          </button>
        </div>
        
        {errorMessage && (
          <div className="error-box">
            <strong>Error:</strong> {errorMessage}
          </div>
        )}
      </div>

      <div className="results-display-panel">
        {!scheduleData && !errorMessage && <div className="empty-state">Matrix ready to compute...</div>}

        {scheduleData && (
          <div className="excel-matrix-wrapper">
            <table className="excel-matrix-table">
              <thead>
                {/* Header Row 1: Main Categories */}
                <tr className="main-header-row">
                  <th colSpan="3">Face Grinding</th>
                  <th colSpan="3">OD Grinding</th>
                  <th colSpan="9">HEAT TREATMENT (DATE: {targetDate})</th>
                </tr>
                
                {/* Header Row 2: Equipment / Priority */}
                <tr className="sub-header-row">
                  <th>DDS (544)</th>
                  <th>Shift</th>
                  <th>Pri.</th>
                  <th>CL-46 Cell</th>
                  <th>Shift</th>
                  <th>Pri.</th>
                  <th>AICHELIN (896)</th>
                  <th>QTY</th>
                  <th>CH</th>
                  <th>CASTLINK (1018)</th>
                  <th>QTY</th>
                  <th>CH</th>
                  <th>ROLLER</th>
                  <th>QTY</th>
                  <th>CH</th>
                </tr>
              </thead>
              <tbody>
                {scheduleData.map((row, index) => (
                  <tr key={index}>
                    {/* Face Grinding */}
                    <td className="job-cell">{row.face ? `${row.face.family}---${row.face.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="shift-cell"></td>
                    <td className="pri-cell"></td>

                    {/* OD Grinding */}
                    <td className="job-cell alt-bg">{row.od ? `${row.od.family}---${row.od.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="shift-cell alt-bg"></td>
                    <td className="pri-cell alt-bg"></td>

                    {/* Aichelin Furnace */}
                    <td className="job-cell ht-bg">{row.aichelin ? `${row.aichelin.family}---${row.aichelin.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="qty-cell ht-bg">{row.aichelin ? row.aichelin.quantity : ''}</td>
                    <td className="ch-cell ht-bg">{row.aichelin ? row.aichelin.channel : ''}</td>

                    {/* Castlink Furnace */}
                    <td className="job-cell ht-bg-alt">{row.castlink ? `${row.castlink.family}---${row.castlink.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="qty-cell ht-bg-alt">{row.castlink ? row.castlink.quantity : ''}</td>
                    <td className="ch-cell ht-bg-alt">{row.castlink ? row.castlink.channel : ''}</td>

                    {/* Roller Furnace */}
                    <td className="job-cell ht-bg">{row.roller ? `${row.roller.family}---${row.roller.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="qty-cell ht-bg">{row.roller ? row.roller.quantity : ''}</td>
                    <td className="ch-cell ht-bg">{row.roller ? row.roller.channel : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default SHOScheduling;

import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('2026-06-25'); 
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [shortageMatrix, setShortageMatrix] = useState([]);
  
  // New: Flexible Buffer Input State
  const [bufferUnit, setBufferUnit] = useState('Boxes'); 
  const [directArrivals, setDirectArrivals] = useState({});

  const handleDirectArrivalChange = (itemKey, value) => {
    setDirectArrivals(prev => ({ ...prev, [itemKey]: parseFloat(value) || 0 }));
  };

  const computeMasterSchedule = async () => {
    setLoading(true);
    
    const formattedArrivals = Object.entries(directArrivals).map(([key, val]) => ({
      item_code: key,
      direct_qty: val
    })).filter(x => x.direct_qty > 0);

    const payload = {
      target_date: targetDate,
      buffer_unit: bufferUnit,
      temp_change_furnaces: [],
      overrides: [],
      direct_arrivals: formattedArrivals
    };

    try {
      const res = await fetch(`https://scm-backend-pshv.onrender.com/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
        setShortageMatrix(json.shortage_matrix);
      }
    } catch (err) {
      console.error("Network Error: ", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO Shop Floor Matrix Engine</h1>
          <p className="subtitle">AI-Driven Multi-Channel Sync & Box Consumption Priority</p>
        </div>
        <div className="action-block">
          <input 
            type="date" 
            value={targetDate} 
            onChange={(e) => setTargetDate(e.target.value)} 
            className="calendar-picker"
          />
          <div className="buffer-selector">
            <label>Input Buffer As: </label>
            <select value={bufferUnit} onChange={(e) => setBufferUnit(e.target.value)}>
              <option value="Boxes">Boxes</option>
              <option value="Rings">Ring Count (Pcs)</option>
              <option value="Days">Days of Buffer</option>
            </select>
          </div>
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Analyzing Consumption...' : 'Compile Master Matrix'}
          </button>
        </div>
      </header>

      {/* MATERIAL SHORTAGE & ORDERING MATRIX */}
      {shortageMatrix.length > 0 && (
        <div className="shortage-panel">
          <h2 className="zone-header">Daily Replenishment & Buffer Priority Matrix</h2>
          <table className="zone-data-table full-width">
            <thead>
              <tr>
                <th>Bearing Ring Type</th>
                <th>Daily Zeroset Req</th>
                <th>Consumption Rate</th>
                <th>Current Avail Store</th>
                <th>Direct to Channel [{bufferUnit}]</th>
                <th>SHO Require-TODAY</th>
                <th>SHO Require-TOMORROW</th>
              </tr>
            </thead>
            <tbody>
              {shortageMatrix.map((row, idx) => (
                <tr key={idx}>
                  <td className="bold-txt">{row.item}</td>
                  <td className="center-txt">{row.req_qty} Rings</td>
                  <td className="center-txt text-muted">{row.daily_box_burn} Boxes/Day</td>
                  <td className="center-txt qty-txt">{row.store_avail}</td>
                  <td className="center-txt">
                    <input 
                      type="number" 
                      placeholder={`Add ${bufferUnit}`} 
                      className="override-input"
                      onChange={(e) => handleDirectArrivalChange(row.item, e.target.value)}
                    />
                  </td>
                  <td className={`center-txt ${row.req_today === 'no material required' ? 'text-muted' : 'prio-tag'}`}>
                    {row.req_today}
                  </td>
                  <td className="center-txt text-muted">{row.req_tomorrow}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* PRODUCTION SCHEDULE GRID */}
      {scheduleData && (
         <div className="shopfloor-layout-grid">
          
          <div className="process-zone-column">
            <h2 className="zone-header face-color">Face Grinding Matrix</h2>
            {Object.keys(scheduleData.face).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip face-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Component</th><th>Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.face[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Spindle Idle</td></tr>
                    ) : (
                      scheduleData.face[machine].map((j, i) => (
                        <tr key={i}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          <div className="process-zone-column">
            <h2 className="zone-header od-color">OD Grinding Matrix</h2>
            {Object.keys(scheduleData.od).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip od-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Component</th><th>Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.od[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Line Idle</td></tr>
                    ) : (
                      scheduleData.od[machine].map((j, i) => (
                        <tr key={i}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

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
                      scheduleData.ht[machine].map((j, i) => (
                        <tr key={i}>
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

// Scrap.js
import React, { useState, useEffect } from 'react';
import './Scrap.css';

const Scrap = () => {
  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
  const today = new Date().toISOString().split('T')[0];

  // Module Sub-Navigation Option (entry = Add Scrap, history = View History)
  const [subView, setSubView] = useState('entry'); 

  // Form Configurations
  const [department, setDepartment] = useState('Heat Treatment');
  const [date, setDate] = useState(today);
  const [shift, setShift] = useState('Shift 1');
  const [category, setCategory] = useState('Industrial');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Table Input Tracker state 
  const [tableData, setTableData] = useState({});
  // History State Tracker
  const [historyData, setHistoryData] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Constants based on your custom shop floor layouts
  const htFurnaces = ['Aichelin Unitherm', 'Roller', 'Birlec', 'Castlink', 'Aichelin', 'Shoei', 'Simplicity', 'Other-'];
  const fodMachines = ['DDS 709+1186', 'DDS 544', 'Gardner1016 + USA 1996', 'Gardner1601', 'S14-1584', 'Gardner BG1-1973', 'SDG-2225', 'SLDP-166', 'TOTAL', 'COL 46 1125+661', 'CL 46-839+945', 'CL-46 1600+1903', 'CL 46 -1904+170', 'CL 46 1585', 'CL 46 2021 AMHD', 'CL 3 BG -660', 'CL-660-2223'];
  const dgbbProcesses = ["1. IR FACE GRINDING", "2. IR GROOVE GRINDING", "3. IR BORE GRINDING", "4. GRD. BURN TEST SC. IR", "5. IR AT BALL FILLING", "6. OR FACE GRINDING", "7. OR OD GRINDING", "8. OR GROOVE GRINDING", "9. OR GROOVE HONING", "10. GRD. BURN TEST SC OR", "11. OR AT BALL FILLING", "12. SEAL", "13. SHILD", "14. A SCRAP BEARING", "15. B SCRAP BEARING", "16. C SCRAP BEARING", "17. C1/CS CLEARANCE SCRAP BEARING", "18. VIBRATION SCRAP BEARING", "19. CAGES SCRAP BEARING", "20. OTHER BALLS (KG)"];
  const dgbbChannels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH05(SABB)", "CH07", "CH08", "CH11", "CH12", "CH13"];

  // Clear data tables when configuration parameters change
  useEffect(() => {
    setTableData({});
  }, [department, category]);

  // Fetch History Logs
  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const response = await fetch(`${API_URL}/api/scrap/history?department=${department}`);
      const result = await response.json();
      if (result.status === 'success') {
        setHistoryData(result.data);
      }
    } catch (error) {
      console.error("Error pulling history logs:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    if (subView === 'history') {
      fetchHistory();
    }
  }, [subView, department]);

  const handleInputChange = (rowKey, colKey, val) => {
    setTableData(prev => ({
      ...prev,
      [`${rowKey}::${colKey}`]: val
    }));
  };

  // Compile entries into a structured list and save to Neon DB
  const handleSubmit = async () => {
    setIsSubmitting(true);
    
    // Convert flat state map into a package list for storage
    const formattedPayload = Object.keys(tableData).map(key => {
      const [row, col] = key.split('::');
      return { item_row: row, configuration_column: col, value: tableData[key] };
    });

    const payload = {
      department,
      date,
      shift,
      category: (department === 'DGBB' || department === 'TRB') ? 'Standard' : category,
      data: formattedPayload
    };

    try {
      const response = await fetch(`${API_URL}/api/scrap/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (response.ok) {
        alert(`Successfully Saved: ${result.message}`);
        setTableData({});
      } else {
        alert(`Error: ${result.detail || 'Failed submission'}`);
      }
    } catch (error) {
      alert("Submission error. Verify your backend is running.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- RENDER FUNCTIONS FOR TABLES ---
  const renderHeatTreatmentTable = () => (
    <div className="table-container">
      <table className="scrap-table">
        <thead>
          <tr>
            <th className="sticky-col">Furnace &darr;</th>
            {[1, 2, 3, 4].map(g => (
              <React.Fragment key={g}>
                <th>G{g} TYPE</th>
                <th>G{g} IR</th>
                <th>G{g} OR</th>
              </React.Fragment>
            ))}
            <th>Remark</th>
          </tr>
        </thead>
        <tbody>
          {htFurnaces.map((furnace, idx) => (
            <tr key={idx}>
              <td className="sticky-col font-bold">{furnace}</td>
              {[1,2,3,4].flatMap(g => [`G${g}_TYPE`, `G${g}_IR`, `G${g}_OR`]).map(col => (
                <td key={col}>
                  <input 
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${furnace}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(furnace, col, e.target.value)}
                  />
                </td>
              ))}
              <td>
                <input 
                  type="text" 
                  className="cell-input" 
                  value={tableData[`${furnace}::Remark`] || ''} 
                  onChange={(e) => handleInputChange(furnace, 'Remark', e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderFaceAndODTable = () => (
    <div className="table-container">
      <table className="scrap-table">
        <thead>
          <tr>
            <th className="sticky-col">MACHINE</th>
            {[1, 2, 3, 4].map(g => (
              <React.Fragment key={g}>
                <th>G{g} TYPE</th>
                <th>G{g} IR</th>
                <th>G{g} OR</th>
                <th>G{g} MO</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {fodMachines.map((machine, idx) => (
            <tr key={idx} className={machine === 'TOTAL' ? 'row-highlight' : ''}>
              <td className="sticky-col font-bold">{machine}</td>
              {[1,2,3,4].flatMap(g => [`G${g}_TYPE`, `G${g}_IR`, `G${g}_OR`, `G${g}_MO`]).map(col => (
                <td key={col}>
                  <input 
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${machine}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(machine, col, e.target.value)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderDGBBTable = () => (
    <div className="table-container">
      <table className="scrap-table dgbb-table">
        <thead>
          <tr>
            <th className="sticky-col" rowSpan="2">PROCESS &darr;</th>
            {dgbbChannels.map(ch => <th key={ch}>{ch}</th>)}
          </tr>
          <tr className="sub-header-row">
            {dgbbChannels.map((ch) => (
              <th key={`sub-${ch}`} className="sub-header">
                <input 
                  type="text" 
                  placeholder="MO. NO." 
                  className="header-input"
                  value={tableData[`HEADER::${ch}_MO`] || ''}
                  onChange={(e) => handleInputChange('HEADER', `${ch}_MO`, e.target.value)}
                />
                <input 
                  type="text" 
                  placeholder="TYPE" 
                  className="header-input"
                  value={tableData[`HEADER::${ch}_TYPE`] || ''}
                  onChange={(e) => handleInputChange('HEADER', `${ch}_TYPE`, e.target.value)}
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dgbbProcesses.map((process, idx) => (
            <tr key={idx}>
              <td className="sticky-col process-cell">{process}</td>
              {dgbbChannels.map((ch) => (
                <td key={ch}>
                  <input 
                    type="number" 
                    className="cell-input" 
                    value={tableData[`${process}::${ch}`] || ''} 
                    onChange={(e) => handleInputChange(process, ch, e.target.value)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="scrap-module">
      {/* Inner Sub-Navigation Bar */}
      <div className="sub-view-tabs">
        <button className={`tab-btn ${subView === 'entry' ? 'active-tab' : ''}`} onClick={() => setSubView('entry')}>
          + Add Scrap Entry
        </button>
        <button className={`tab-btn ${subView === 'history' ? 'active-tab' : ''}`} onClick={() => setSubView('history')}>
          📊 View History Logs
        </button>
      </div>

      <div className="module-header">
        <h2>{department} Scrap Portal</h2>
        <div className="controls-row">
          <div className="control-group">
            <label>Department:</label>
            <select value={department} onChange={(e) => setDepartment(e.target.value)}>
              <option value="Heat Treatment">Heat Treatment</option>
              <option value="Face and OD">Face and OD Grinding</option>
              <option value="DGBB">DGBB</option>
              <option value="TRB">TRB</option>
            </select>
          </div>

          {subView === 'entry' && (department === 'Heat Treatment' || department === 'Face and OD') && (
            <div className="control-group">
              <label>Category:</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="Industrial">Industrial</option>
                <option value="Automotive">Automotive</option>
              </select>
            </div>
          )}

          {subView === 'entry' && (
            <>
              <div className="control-group">
                <label>Date:</label>
                <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </div>
              <div className="control-group">
                <label>Shift:</label>
                <select value={shift} onChange={(e) => setShift(e.target.value)}>
                  <option value="Shift 1">Shift I</option>
                  <option value="Shift 2">Shift II</option>
                  <option value="Shift 3">Shift III</option>
                </select>
              </div>
            </>
          )}
        </div>
      </div>

      {subView === 'entry' ? (
        <div className="table-wrapper">
          <div className="table-title">
            <h3>{department.toUpperCase()} LOGENTRY FORM</h3>
          </div>
          {department === 'Heat Treatment' && renderHeatTreatmentTable()}
          {department === 'Face and OD' && renderFaceAndODTable()}
          {department === 'DGBB' && renderDGBBTable()}
          {department === 'TRB' && <div className="placeholder">TRB Table Format Configuration Pending...</div>}
          
          <div className="action-row">
            <button className="submit-btn" onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? 'Saving Data...' : 'Save Sheet Records'}
            </button>
          </div>
        </div>
      ) : (
        <div className="history-wrapper">
          <h3>Day & Shift Wise Logs History ({department})</h3>
          {loadingHistory ? (
            <p>Loading records from Neon DB...</p>
          ) : historyData.length === 0 ? (
            <p className="placeholder">No historical entries recorded for this department yet.</p>
          ) : (
            <table className="history-summary-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Shift</th>
                  <th>Category</th>
                  <th>Total Rows Recorded</th>
                </tr>
              </thead>
              <tbody>
                {historyData.map((hist) => (
                  <tr key={hist.id}>
                    <td><b>{hist.date}</b></td>
                    <td>{hist.shift}</td>
                    <td>{hist.category}</td>
                    <td>{hist.payload?.length || 0} fields logged</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default Scrap;

// Scrap.js
import React, { useState, useEffect } from 'react';
import './Scrap.css';

const Scrap = () => {
  const API_URL = process.env.REACT_APP_API_URL || 'https://scm-backend-pshv.onrender.com';
  const today = new Date().toISOString().split('T')[0];

  const [subView, setSubView] = useState('entry'); // 'entry' or 'history'
  const [department, setDepartment] = useState('Heat Treatment');
  const [date, setDate] = useState(today);
  const [shift, setShift] = useState('Shift 1');
  const [category, setCategory] = useState('Industrial');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tableData, setTableData] = useState({});
  
  // History UI states
  const [historyData, setHistoryData] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  // Layout Configuration Mappings
  const htFurnaces = ['Aichelin Unitherm', 'Roller', 'Birlec', 'Castlink', 'Aichelin', 'Shoei', 'Simplicity', 'Other-'];
  const htCols = ['G1_TYPE', 'G1_IR', 'G1_OR', 'G2_TYPE', 'G2_IR', 'G2_OR', 'G3_TYPE', 'G3_IR', 'G3_OR', 'G4_TYPE', 'G4_IR', 'G4_OR', 'Remark'];

  const fodMachines = ['DDS 709+1186', 'DDS 544', 'Gardner1016 + USA 1996', 'Gardner1601', 'S14-1584', 'Gardner BG1-1973', 'SDG-2225', 'SLDP-166', 'TOTAL', 'COL 46 1125+661', 'CL 46-839+945', 'CL-46 1600+1903', 'CL 46 -1904+170', 'CL 46 1585', 'CL 46 2021 AMHD', 'CL 3 BG -660', 'CL-660-2223'];
  const fodCols = ['G1_TYPE', 'G1_IR', 'G1_OR', 'G1_MO', 'G2_TYPE', 'G2_IR', 'G2_OR', 'G2_MO', 'G3_TYPE', 'G3_IR', 'G3_OR', 'G3_MO', 'G4_TYPE', 'G4_IR', 'G4_OR', 'G4_MO'];

  const dgbbProcesses = ["1. IR FACE GRINDING", "2. IR GROOVE GRINDING", "3. IR BORE GRINDING", "4. GRD. BURN TEST SC. IR", "5. IR AT BALL FILLING", "6. OR FACE GRINDING", "7. OR OD GRINDING", "8. OR GROOVE GRINDING", "9. OR GROOVE HONING", "10. GRD. BURN TEST SC OR", "11. OR AT BALL FILLING", "12. SEAL", "13. SHILD", "14. A SCRAP BEARING", "15. B SCRAP BEARING", "16. C SCRAP BEARING", "17. C1/CS CLEARANCE SCRAP BEARING", "18. VIBRATION SCRAP BEARING", "19. CAGES SCRAP BEARING", "20. OTHER BALLS (KG)"];
  const dgbbChannels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH05(SABB)", "CH07", "CH08", "CH11", "CH12", "CH13"];

  useEffect(() => {
    setTableData({});
  }, [department, category]);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const response = await fetch(`${API_URL}/api/scrap/history?department=${encodeURIComponent(department)}`);
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
    if (subView === 'history') fetchHistory();
  }, [subView, department]);

  const handleInputChange = (rowKey, colKey, val) => {
    setTableData(prev => ({ ...prev, [`${rowKey}::${colKey}`]: val }));
  };

  // Excel Movement Logic (Detects Enter, drops down a row within the identical column list)
  const handleKeyDown = (e, currentRowIdx, colIdx, totalRows, inputIdPrefix) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const nextRowIdx = currentRowIdx + 1;
      if (nextRowIdx < totalRows) {
        const nextTarget = document.getElementById(`${inputIdPrefix}-${nextRowIdx}-${colIdx}`);
        if (nextTarget) {
          nextTarget.focus();
          nextTarget.select();
        }
      }
    }
  };

  const handleSubmit = async () => {
    if (Object.keys(tableData).length === 0) {
      alert("Cannot submit an empty sheet layout.");
      return;
    }
    setIsSubmitting(true);
    
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
      if (response.ok && result.status === 'success') {
        alert("Success: Records logged to database!");
        setTableData({});
      } else {
        alert(`Failed: ${result.detail || 'Internal server anomaly'}`);
      }
    } catch (error) {
      alert("Failed to save data. Make sure the backend is running and the API URL is correct.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- RENDERING INDIVIDUAL DEPT SCHEMAS ---
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
          {htFurnaces.map((furnace, rIdx) => (
            <tr key={rIdx}>
              <td className="sticky-col font-bold">{furnace}</td>
              {htCols.map((col, cIdx) => (
                <td key={col}>
                  <input 
                    id={`ht-${rIdx}-${cIdx}`}
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${furnace}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(furnace, col, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, htFurnaces.length, 'ht')}
                  />
                </td>
              ))}
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
          {fodMachines.map((machine, rIdx) => (
            <tr key={rIdx} className={machine === 'TOTAL' ? 'row-highlight' : ''}>
              <td className="sticky-col font-bold">{machine}</td>
              {fodCols.map((col, cIdx) => (
                <td key={col}>
                  <input 
                    id={`fod-${rIdx}-${cIdx}`}
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${machine}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(machine, col, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, fodMachines.length, 'fod')}
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
          {dgbbProcesses.map((process, rIdx) => (
            <tr key={rIdx}>
              <td className="sticky-col process-cell">{process}</td>
              {dgbbChannels.map((ch, cIdx) => (
                <td key={ch}>
                  <input 
                    id={`dgbb-${rIdx}-${cIdx}`}
                    type="number" 
                    className="cell-input" 
                    value={tableData[`${process}::${ch}`] || ''} 
                    onChange={(e) => handleInputChange(process, ch, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, dgbbProcesses.length, 'dgbb')}
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
      <div className="sub-view-tabs">
        <button className={`tab-btn ${subView === 'entry' ? 'active-tab' : ''}`} onClick={() => setSubView('entry')}>
          + Add Scrap Entry
        </button>
        <button className={`tab-btn ${subView === 'history' ? 'active-tab' : ''}`} onClick={() => setSubView('history')}>
          📊 View History Logs
        </button>
      </div>

      <div className="module-header">
        <h2>{department} Scrap Module</h2>
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
          {department === 'Heat Treatment' && renderHeatTreatmentTable()}
          {department === 'Face and OD' && renderFaceAndODTable()}
          {department === 'DGBB' && renderDGBBTable()}
          {department === 'TRB' && <div className="placeholder">TRB Layout Format Configuration Pending...</div>}
          
          <div className="action-row">
            <button className="submit-btn" onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? 'Saving Sheet Data...' : 'Save Sheet Records'}
            </button>
          </div>
        </div>
      ) : (
        <div className="history-wrapper">
          <h3>Historical Records ({department})</h3>
          {loadingHistory ? (
            <p>Loading database history...</p>
          ) : historyData.length === 0 ? (
            <p className="placeholder">No history found for this section.</p>
          ) : (
            <table className="history-summary-table">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Date Logged</th>
                  <th>Shift</th>
                  <th>Category</th>
                  <th>Metrics Tracked</th>
                </tr>
              </thead>
              <tbody>
                {historyData.map((hist) => (
                  <React.Fragment key={hist.id}>
                    <tr>
                      <td>
                        <button 
                          className="view-details-btn" 
                          onClick={() => setExpandedRow(expandedRow === hist.id ? null : hist.id)}
                        >
                          {expandedRow === hist.id ? 'Hide Details' : 'View Details'}
                        </button>
                      </td>
                      <td><b>{hist.date}</b></td>
                      <td>{hist.shift}</td>
                      <td>{hist.category}</td>
                      <td>{hist.payload?.length || 0} fields saved</td>
                    </tr>
                    {expandedRow === hist.id && (
                      <tr className="expanded-row-data">
                        <td colSpan="5">
                          <div className="inner-history-log">
                            <h4>Detailed Payload Records:</h4>
                            <ul>
                              {hist.payload.map((item, idx) => (
                                <li key={idx}>
                                  <strong>{item.item_row}</strong> ({item.configuration_column}): <span className="highlight-text">{item.value}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
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

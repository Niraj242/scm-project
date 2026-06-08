// Scrap.js
import React, { useState, useEffect, useMemo } from 'react';
import './Scrap.css';

const Scrap = () => {
  const API_URL = process.env.REACT_APP_API_URL || 'https://scm-backend-pshv.onrender.com';
  const today = new Date().toISOString().split('T')[0];

  // View state management: 'entry' (New Form), 'history' (Saved Sheets Grid), 'summary' (Dynamic Cross-tab Matrix)
  const [subView, setSubView] = useState('entry'); 
  const [department, setDepartment] = useState('Heat Treatment');
  const [date, setDate] = useState(today);
  const [shift, setShift] = useState('Shift 1');
  const [category, setCategory] = useState('Industrial');
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Data Matrices
  const [tableData, setTableData] = useState({});
  const [historyRecords, setHistoryRecords] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Constants defining standard shop configurations
  const htFurnaces = ['Aichelin Unitherm', 'Roller', 'Birlec', 'Castlink', 'Aichelin', 'Shoei', 'Simplicity', 'Other-'];
  const htCols = ['G1_TYPE', 'G1_IR', 'G1_OR', 'G2_TYPE', 'G2_IR', 'G2_OR', 'G3_TYPE', 'G3_IR', 'G3_OR', 'G4_TYPE', 'G4_IR', 'G4_OR', 'Remark'];

  const fodMachines = ['DDS 709+1186', 'DDS 544', 'Gardner1016 + USA 1996', 'Gardner1601', 'S14-1584', 'Gardner BG1-1973', 'SDG-2225', 'SLDP-166', 'TOTAL', 'COL 46 1125+661', 'CL 46-839+945', 'CL-46 1600+1903', 'CL 46 -1904+170', 'CL 46 1585', 'CL 46 2021 AMHD', 'CL 3 BG -660', 'CL-660-2223'];
  const fodCols = ['G1_TYPE', 'G1_IR', 'G1_OR', 'G1_MO', 'G2_TYPE', 'G2_IR', 'G2_OR', 'G2_MO', 'G3_TYPE', 'G3_IR', 'G3_OR', 'G3_MO', 'G4_TYPE', 'G4_IR', 'G4_OR', 'G4_MO'];

  const dgbbProcesses = ["1. IR FACE GRINDING", "2. IR GROOVE GRINDING", "3. IR BORE GRINDING", "4. GRD. BURN TEST SC. IR", "5. IR AT BALL FILLING", "6. OR FACE GRINDING", "7. OR OD GRINDING", "8. OR GROOVE GRINDING", "9. OR GROOVE HONING", "10. GRD. BURN TEST SC OR", "11. OR AT BALL FILLING", "12. SEAL", "13. SHILD", "14. A SCRAP BEARING", "15. B SCRAP BEARING", "16. C SCRAP BEARING", "17. C1/CS CLEARANCE SCRAP BEARING", "18. VIBRATION SCRAP BEARING", "19. CAGES SCRAP BEARING", "20. OTHER BALLS (KG)"];
  const dgbbChannels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH05(SABB)", "CH07", "CH08", "CH11", "CH12", "CH13"];

  // Clear data tables when configuration parameters change
  useEffect(() => {
    if (subView === 'entry') {
      setTableData({});
    }
  }, [department, category, subView]);

  // Fetch all historical database records for current department
  const loadHistoryLogs = async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch(`${API_URL}/api/scrap/history?department=${encodeURIComponent(department)}`);
      const result = await res.json();
      if (result.status === 'success') {
        setHistoryRecords(result.data);
        if (result.data.length > 0 && subView === 'history') {
          // Default load the most recent record
          mapHistoryToGrid(result.data[0]);
        }
      }
    } catch (e) {
      console.error("Failed fetching history records:", e);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadHistoryLogs();
  }, [department, subView]);

  // Convert array rows from Postgres JSON back into a key-value layout state map
  const mapHistoryToGrid = (record) => {
    if (!record) return;
    setSelectedHistoryId(record.id);
    const rebuiltGrid = {};
    record.payload.forEach(item => {
      rebuiltGrid[`${item.item_row}::${item.configuration_column}`] = item.value;
    });
    setTableData(rebuiltGrid);
  };

  const handleInputChange = (rowKey, colKey, val) => {
    setTableData(prev => ({ ...prev, [`${rowKey}::${colKey}`]: val }));
  };

  // Excel keystroke movement: Enter shifts focus downward to the next row within the same column group
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

  const saveSheetRecords = async () => {
    if (Object.keys(tableData).length === 0) return alert("Cannot submit blank templates.");
    setIsSubmitting(true);

    const dataPayload = Object.keys(tableData).map(key => {
      const [row, col] = key.split('::');
      return { item_row: row, configuration_column: col, value: tableData[key] };
    });

    try {
      let response, result;
      if (subView === 'history') {
        // Edit Mode: Update existing database row
        response = await fetch(`${API_URL}/api/scrap/update`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: parseInt(selectedHistoryId), payload: dataPayload })
        });
      } else {
        // Entry Mode: Create a new database row
        response = await fetch(`${API_URL}/api/scrap/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            department, date, shift,
            category: (department === 'DGBB' || department === 'TRB') ? 'Standard' : category,
            data: dataPayload
          })
        });
      }

      result = await response.json();
      if (response.ok && result.status === 'success') {
        alert("Records updated and saved securely to database!");
        if (subView === 'entry') setTableData({});
        loadHistoryLogs();
      } else {
        alert(`Error: ${result.detail || 'Failed process event.'}`);
      }
    } catch (err) {
      alert("Network Error: Verify that connection variables match server configurations.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- CROSS TAB GENERATION LOGIC ---
  const summaryMatrix = useMemo(() => {
    const matrix = {}; // format: { [bearing_type]: { [date]: { [shift]: sum } } }
    const uniqueDates = new Set();

    historyRecords.forEach(record => {
      const logDate = record.date;
      const logShift = record.shift;
      uniqueDates.add(logDate);

      // Rebuild temporary record map for clean scanning
      const dataMap = {};
      record.payload.forEach(item => {
        if (!dataMap[item.item_row]) dataMap[item.item_row] = {};
        dataMap[item.item_row][item.configuration_column] = item.value;
      });

      const parseVal = (v) => isNaN(parseFloat(v)) ? 0 : parseFloat(v);
      const addValueToMatrix = (type, qty) => {
        if (!type || type.trim() === "" || type.toUpperCase().includes("UNKNOWN") || qty <= 0) return;
        const cleanType = type.trim().toUpperCase();
        if (!matrix[cleanType]) matrix[cleanType] = {};
        if (!matrix[cleanType][logDate]) matrix[cleanType][logDate] = {};
        matrix[cleanType][logDate][logShift] = (matrix[cleanType][logDate][logShift] || 0) + qty;
      };

      if (record.department === 'Heat Treatment') {
        htFurnaces.forEach(furnace => {
          const rowData = dataMap[furnace] || {};
          [1, 2, 3, 4].forEach(g => {
            const bType = rowData[`G${g}_TYPE`];
            const scrapQty = parseVal(rowData[`G${g}_IR`]) + parseVal(rowData[`G${g}_OR`]);
            addValueToMatrix(bType, scrapQty);
          });
        });
      } else if (record.department === 'Face and OD') {
        fodMachines.forEach(machine => {
          if (machine === 'TOTAL') return;
          const rowData = dataMap[machine] || {};
          [1, 2, 3, 4].forEach(g => {
            const bType = rowData[`G${g}_TYPE`];
            const scrapQty = parseVal(rowData[`G${g}_IR`]) + parseVal(rowData[`G${g}_OR`]);
            addValueToMatrix(bType, scrapQty);
          });
        });
      } else if (record.department === 'DGBB') {
        const headers = dataMap['HEADER'] || {};
        dgbbChannels.forEach(ch => {
          const bType = headers[`${ch}_TYPE`];
          let channelScrapSum = 0;
          dgbbProcesses.forEach(proc => {
            channelScrapSum += parseVal((dataMap[proc] || {})[ch]);
          });
          addValueToMatrix(bType, channelScrapSum);
        });
      }
    });

    const sortedDates = Array.from(uniqueDates).sort();
    return { matrix, sortedDates };
  }, [historyRecords]);

  // --- RENDER PATTERNS ---
  const renderHTLayout = (prefix) => (
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
                    id={`${prefix}-${rIdx}-${cIdx}`}
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${furnace}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(furnace, col, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, htFurnaces.length, prefix)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderFODLayout = (prefix) => (
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
                    id={`${prefix}-${rIdx}-${cIdx}`}
                    type="text" 
                    className="cell-input" 
                    value={tableData[`${machine}::${col}`] || ''} 
                    onChange={(e) => handleInputChange(machine, col, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, fodMachines.length, prefix)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderDGBBLayout = (prefix) => (
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
                    id={`${prefix}-${rIdx}-${cIdx}`}
                    type="number" 
                    className="cell-input" 
                    value={tableData[`${process}::${ch}`] || ''} 
                    onChange={(e) => handleInputChange(process, ch, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, rIdx, cIdx, dgbbProcesses.length, prefix)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // --- CROSS-TAB DATA COMPUTATION HANDLERS ---
  const dateList = summaryMatrix.sortedDates;
  const matrixData = summaryMatrix.matrix;
  const shifts = ['Shift 1', 'Shift 2', 'Shift 3'];
  
  // Track cross-tab dynamic column/row totals
  let grandTotal = 0;
  const columnTotals = {};

  return (
    <div className="scrap-module">
      {/* Dynamic Module Nav Toggles */}
      <div className="sub-view-tabs">
        <button className={`tab-btn ${subView === 'entry' ? 'active-tab' : ''}`} onClick={() => setSubView('entry')}>
          + Add Scrap Entry
        </button>
        <button className={`tab-btn ${subView === 'history' ? 'active-tab' : ''}`} onClick={() => setSubView('history')}>
          ✏️ View & Edit Saved Sheets
        </button>
        <button className={`tab-btn ${subView === 'summary' ? 'active-tab' : ''}`} onClick={() => setSubView('summary')}>
          📊 Cross-Tab Summary Matrix
        </button>
      </div>

      <div className="module-header">
        <h2>{department} System Workspace</h2>
        <div className="controls-row">
          <div className="control-group">
            <label>Workspace Department:</label>
            <select value={department} onChange={(e) => { setDepartment(e.target.value); setSelectedHistoryId(''); }}>
              <option value="Heat Treatment">Heat Treatment</option>
              <option value="Face and OD">Face and OD Grinding</option>
              <option value="DGBB">DGBB</option>
              <option value="TRB">TRB</option>
            </select>
          </div>

          {subView === 'entry' && (
            <>
              {(department === 'Heat Treatment' || department === 'Face and OD') && (
                <div className="control-group">
                  <label>Category:</label>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    <option value="Industrial">Industrial</option>
                    <option value="Automotive">Automotive</option>
                  </select>
                </div>
              )}
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

          {subView === 'history' && (
            <div className="control-group archived-selector-box">
              <label>Select Saved Archive Log Sheet:</label>
              <select 
                value={selectedHistoryId} 
                onChange={(e) => {
                  const targetRecord = historyRecords.find(r => r.id === parseInt(e.target.value));
                  mapHistoryToGrid(targetRecord);
                }}
              >
                {historyRecords.map(r => (
                  <option key={r.id} value={r.id}>
                    [{r.date}] - {r.shift} ({r.category})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* RENDER VIEW 1: DATA ENTRY BLOCK */}
      {subView === 'entry' && (
        <div className="table-wrapper">
          {department === 'Heat Treatment' && renderHTLayout('newht')}
          {department === 'Face and OD' && renderFODLayout('newfod')}
          {department === 'DGBB' && renderDGBBLayout('newdgbb')}
          {department === 'TRB' && <div className="placeholder">TRB Base Configuration Blueprint Pending...</div>}
          
          <div className="action-row">
            <button className="submit-btn" onClick={saveSheetRecords} disabled={isSubmitting}>
              {isSubmitting ? 'Writing to database...' : 'Save New Sheet Records'}
            </button>
          </div>
        </div>
      )}

      {/* RENDER VIEW 2: LOG RECORD ARCHIVE SHEET EDITOR */}
      {subView === 'history' && (
        <div className="table-wrapper archive-edit-mode">
          <div className="archive-badge">⚠️ ARCHIVE EDIT MODE ACTIVE</div>
          {loadingHistory ? (
            <p>Loading spreadsheet layout arrays from Neon database...</p>
          ) : historyRecords.length === 0 ? (
            <p className="placeholder">No past sheets saved for this section.</p>
          ) : (
            <>
              {department === 'Heat Treatment' && renderHTLayout('editht')}
              {department === 'Face and OD' && renderFODLayout('editfod')}
              {department === 'DGBB' && renderDGBBLayout('editdgbb')}
              {department === 'TRB' && <div className="placeholder">TRB Layout Configuration Blueprint Pending...</div>}
              
              <div className="action-row">
                <button className="submit-btn update-btn" onClick={saveSheetRecords} disabled={isSubmitting}>
                  {isSubmitting ? 'Modifying database records...' : 'Update Existing Archive Records'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* RENDER VIEW 3: CROSS-TAB PRODUCTION SCRAP MATRIX COMPONENT */}
      {subView === 'summary' && (
        <div className="summary-matrix-wrapper">
          <h3>Day & Shift Wise Cross-Tab Scrap Summary ({department})</h3>
          {dateList.length === 0 ? (
            <p className="placeholder">No historical parameters found to generate analytical dimensions.</p>
          ) : (
            <div className="table-container matrix-scroll">
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th rowSpan="2" className="sticky-col head-col">Bearing Family / Type</th>
                    {dateList.map(d => (
                      <th key={d} colSpan="3" className="date-header-cell">{d}</th>
                    ))}
                    <th rowSpan="2" className="total-header-cell">Total</th>
                  </tr>
                  <tr>
                    {dateList.flatMap(d => shifts.map(s => (
                      <th key={`${d}-${s}`} className="shift-sub-cell">{s === 'Shift 1' ? 'S-I' : s === 'Shift 2' ? 'S-II' : 'S-III'}</th>
                    )))}
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(matrixData).sort().map(bearingType => {
                    let rowSum = 0;
                    return (
                      <tr key={bearingType}>
                        <td className="sticky-col font-bold type-cell">{bearingType}</td>
                        {dateList.flatMap(d => shifts.map(s => {
                          const val = matrixData[bearingType]?.[d]?.[s] || 0;
                          rowSum += val;
                          
                          const colKey = `${d}-${s}`;
                          columnTotals[colKey] = (columnTotals[colKey] || 0) + val;
                          
                          return (
                            <td key={`${bearingType}-${colKey}`} className={val > 0 ? 'cell-has-value' : 'cell-empty'}>
                              {val > 0 ? val : '-'}
                            </td>
                          );
                        }))}
                        <td className="row-total-cell font-bold">{rowSum}</td>
                      </tr>
                    );
                  })}
                  
                  {/* BOTTOM ROW TOTALS AND THE GRAND TOTAL MATRIX CORNER */}
                  <tr className="grand-total-row">
                    <td className="sticky-col font-bold">Total</td>
                    {dateList.flatMap(d => shifts.map(s => {
                      const colKey = `${d}-${s}`;
                      const colTotal = columnTotals[colKey] || 0;
                      grandTotal += colTotal;
                      return <td key={`total-${colKey}`} className="font-bold">{colTotal > 0 ? colTotal : '-'}</td>;
                    }))}
                    <td className="grand-total-corner font-bold">{grandTotal}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Scrap;

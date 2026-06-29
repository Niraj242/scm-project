import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  // Top-level controls state
  const [sector, setSector] = useState('DGBB');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  
  // Matrix state to hold all entered data
  const [tableData, setTableData] = useState({});

  // Column definitions based on your 3 images
  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  // Row definitions matching the exact structure of your Excel sheets
  const ROWS = [
    { label: 'CH. BUFFER', key: 'ch_buffer_1' },
    { label: 'TYPE', key: 'type_1' },
    { label: 'CH. BUFFER', key: 'ch_buffer_2' },
    { label: 'NEXT TYPE', key: 'next_type_1' },
    { label: 'OD BUFFER', key: 'od_buffer_1' },
    { label: 'TYPE', key: 'type_2' },
    { label: 'OD BUFFER', key: 'od_buffer_2' },
    { label: 'NEXT TYPE', key: 'next_type_2' },
    { label: 'FACE BUFFER', key: 'face_buffer_1' },
    { label: 'TYPE', key: 'type_3' },
    { label: 'FACE BUFFER', key: 'face_buffer_2' },
    { label: 'TYPE', key: 'type_4' },
    { label: 'HT. BUFFER', key: 'ht_buffer_1' },
    { label: 'TYPE', key: 'type_5' },
    { label: 'HT. BUFFER', key: 'ht_buffer_2' },
    { label: 'TYPE', key: 'type_6' },
    { label: '', key: 'spacer' }, // Empty row as seen in images
    { label: 'RUNNING', key: 'running' },
    { label: 'NEXT TYPE', key: 'next_type_3' },
    { label: 'BUFFER IN DAYS', key: 'buffer_in_days' }
  ];

  // Handle clearing table when switching sectors (or you can fetch from DB here later)
  useEffect(() => {
    setTableData({});
    // LATER: Add an API call here to fetch existing data for the selected Date & Sector
  }, [sector, selectedDate]);

  // Handle typing in the grid
  const handleInputChange = (rowKey, col, subCol, value) => {
    const dataKey = `${rowKey}_${col}_${subCol}`;
    setTableData(prev => ({
      ...prev,
      [dataKey]: value
    }));
  };

  // Save handler for backend
  const handleSave = async () => {
    const payload = {
      sector,
      date: selectedDate,
      unit: unitMode,
      entries: tableData
    };
    console.log("Saving payload to Database:", payload);
    alert(`Data saved for ${sector} on ${selectedDate} in ${unitMode}`);
    // LATER: Send 'payload' to your FastAPI backend via POST request
  };

  const columns = SECTOR_COLUMNS[sector];

  return (
    <div className="sho-container">
      {/* HEADER & CONTROLS */}
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
          <input 
            type="date" 
            value={selectedDate} 
            onChange={(e) => setSelectedDate(e.target.value)} 
          />
        </div>

        <div className="control-group">
          <label>Entry Unit:</label>
          <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
            <option value="Days">Buffer Days</option>
            <option value="Boxes">Boxes</option>
            <option value="Rings">No. of Rings</option>
          </select>
        </div>

        <button className="btn-save" onClick={handleSave}>
          Save Entries
        </button>
      </div>

      {/* DYNAMIC DATA ENTRY TABLE */}
      <div className="table-wrapper">
        <table className="excel-table">
          <thead>
            {/* Top Corporate Header */}
            <tr>
              <th colSpan="2" className="text-blue text-left pl-2">SKF INDIA LTD.</th>
              <th colSpan={columns.length * 2 - 4} className="text-blue">
                CHANNEL BUFFER STATUS (VERSION - 6)<br/>
                {sector === 'DGBB' ? 'DBBB' : sector}
              </th>
              <th colSpan="2" className="text-blue text-right pr-2">DATE :- {selectedDate.split('-').reverse().join('/')}</th>
            </tr>
            
            {/* Sector Sub-header row (Specific to HUB/TRB images) */}
            {sector === 'TRB' && (
              <tr>
                <th colSpan="2" className="text-blue">BUFFER IN DAYS FOR 100% EFF.</th>
                <th colSpan={columns.length * 2 - 4} className="text-blue font-xl">TRB</th>
                <th colSpan="2" className="text-blue">SPLIT THU</th>
              </tr>
            )}
            {sector === 'HUB' && (
              <tr>
                <th colSpan="2"></th>
                <th colSpan="8" className="text-blue font-xl border-right-thick">HUB</th>
                <th colSpan="6" className="text-blue font-xl">THUB</th>
              </tr>
            )}

            {/* Main Column Headers */}
            <tr className="header-row">
              <th className="text-blue" style={{width: '120px'}}>CHANNEL</th>
              {columns.map(col => (
                <th key={col} colSpan="2" className="text-blue column-title">{col}</th>
              ))}
            </tr>
            
            {/* IR / OR Sub-headers */}
            <tr className="subheader-row">
              <th className="font-bold">PART</th>
              {columns.map(col => (
                <React.Fragment key={`${col}-sub`}>
                  <th className="font-bold">IR</th>
                  <th className="font-bold">OR</th>
                </React.Fragment>
              ))}
            </tr>
          </thead>
          
          <tbody>
            {ROWS.map((row, index) => (
              <tr key={index} className={row.key === 'spacer' ? 'spacer-row' : ''}>
                <td className="row-label font-bold">{row.label}</td>
                
                {row.key !== 'spacer' ? columns.map(col => (
                  <React.Fragment key={`${row.key}-${col}`}>
                    <td className="input-cell">
                      <input 
                        type="text"
                        value={tableData[`${row.key}_${col}_IR`] || ''}
                        onChange={(e) => handleInputChange(row.key, col, 'IR', e.target.value)}
                      />
                    </td>
                    <td className="input-cell">
                      <input 
                        type="text"
                        value={tableData[`${row.key}_${col}_OR`] || ''}
                        onChange={(e) => handleInputChange(row.key, col, 'OR', e.target.value)}
                      />
                    </td>
                  </React.Fragment>
                )) : columns.map(col => (
                  <React.Fragment key={`spacer-${col}`}>
                    <td className="spacer-cell"></td>
                    <td className="spacer-cell"></td>
                  </React.Fragment>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SHOScheduling;

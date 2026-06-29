import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [sector, setSector] = useState('DGBB');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [unitMode, setUnitMode] = useState('Days');
  const [tableData, setTableData] = useState({});

  const SECTOR_COLUMNS = {
    DGBB: ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
    TRB: ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
    HUB: ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
  };

  // Defines which columns should be blocked/merged for specific sections
  const DISABLED_BLOCKS = {
    DGBB: {
      OD: ['CH01', 'CH03', 'SABB', 'CH07', 'CH11'],
      FACE: ['CH02', 'CH04', 'SABB', 'CH07', 'CH11']
    },
    TRB: {
      OD: ['T 3', 'T 5', 'T 6', 'T 9', 'T10'],
      FACE: ['T 8', 'T 9', 'T10']
    },
    HUB: {
      OD: ['HUB 1.1', 'T HUB 1.1'],
      FACE: []
    }
  };

  const ROWS = [
    { label: 'CH. BUFFER', key: 'ch_buffer_1', section: 'CH' },
    { label: 'TYPE', key: 'type_1', section: 'CH' },
    { label: 'CH. BUFFER', key: 'ch_buffer_2', section: 'CH' },
    { label: 'NEXT TYPE', key: 'next_type_1', section: 'CH' },
    { label: 'OD BUFFER', key: 'od_buffer_1', section: 'OD' },
    { label: 'TYPE', key: 'type_2', section: 'OD' },
    { label: 'OD BUFFER', key: 'od_buffer_2', section: 'OD' },
    { label: 'NEXT TYPE', key: 'next_type_2', section: 'OD' },
    { label: 'FACE BUFFER', key: 'face_buffer_1', section: 'FACE' },
    { label: 'TYPE', key: 'type_3', section: 'FACE' },
    { label: 'FACE BUFFER', key: 'face_buffer_2', section: 'FACE' },
    { label: 'TYPE', key: 'type_4', section: 'FACE' },
    { label: 'HT. BUFFER', key: 'ht_buffer_1', section: 'HT' },
    { label: 'TYPE', key: 'type_5', section: 'HT' },
    { label: 'HT. BUFFER', key: 'ht_buffer_2', section: 'HT' },
    { label: 'TYPE', key: 'type_6', section: 'HT' },
    { label: '', key: 'spacer', section: 'NONE' },
    { label: 'RUNNING', key: 'running', section: 'RUN' },
    { label: 'NEXT TYPE', key: 'next_type_3', section: 'RUN' },
    { label: 'BUFFER IN DAYS', key: 'buffer_in_days', section: 'RUN' }
  ];

  // FETCH DATA from LocalStorage when Date or Sector changes
  useEffect(() => {
    const storageKey = `sho_db_${sector}_${selectedDate}`;
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
      setTableData(JSON.parse(savedData));
    } else {
      setTableData({}); // Clear if no data exists for this date
    }
  }, [sector, selectedDate]);

  // Handle Input
  const handleInputChange = (rowKey, col, subCol, value) => {
    setTableData(prev => ({
      ...prev,
      [`${rowKey}_${col}_${subCol}`]: value
    }));
  };

  // SAVE DATA to LocalStorage
  const handleSave = () => {
    const storageKey = `sho_db_${sector}_${selectedDate}`;
    localStorage.setItem(storageKey, JSON.stringify(tableData));
    
    console.log("Data ready for Backend:", { sector, date: selectedDate, unit: unitMode, entries: tableData });
    alert(`Saved successfully! Entries for ${sector} on ${selectedDate} are now stored.`);
  };

  const columns = SECTOR_COLUMNS[sector];

  return (
    <div className="sho-container">
      {/* CONTROLS */}
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
          <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} />
        </div>
        <div className="control-group">
          <label>Entry Unit:</label>
          <select value={unitMode} onChange={(e) => setUnitMode(e.target.value)}>
            <option value="Days">Buffer Days</option>
            <option value="Boxes">Boxes</option>
            <option value="Rings">No. of Rings</option>
          </select>
        </div>
        <button className="btn-save" onClick={handleSave}>Save Entries</button>
      </div>

      {/* TABLE WRAPPER (Handles Scrolling) */}
      <div className="table-scroll-container">
        <table className="excel-table">
          <thead>
            {/* 1st Header Row */}
            <tr>
              <th colSpan="2" className="text-blue text-left pl-2">SKF INDIA LTD.</th>
              <th colSpan={columns.length * 2 - 4} className="text-blue">
                CHANNEL BUFFER STATUS (VERSION - 6)<br/>
                {sector === 'DGBB' ? 'DBBB' : sector}
              </th>
              <th colSpan="2" className="text-blue text-right pr-2">
                DATE :- {selectedDate.split('-').reverse().join('/')}
              </th>
            </tr>
            
            {/* 2nd Header Row (Dynamic based on Sector) */}
            {sector === 'TRB' && (
              <tr>
                <th colSpan="2" className="text-blue">BUFFER IN DAYS FOR 100% EFF.</th>
                <th colSpan={(columns.length - 1) * 2} className="text-blue font-xl">TRB</th>
                <th colSpan="2" className="text-blue font-xl">SPLIT THU<br/>T10</th>
              </tr>
            )}
            {sector === 'HUB' && (
              <tr>
                <th colSpan="2"></th>
                <th colSpan="8" className="text-blue font-xl border-right-thick">HUB</th>
                <th colSpan="6" className="text-blue font-xl">THUB</th>
              </tr>
            )}
            {sector === 'DGBB' && (
              <tr>
                <th colSpan="2" className="text-blue">BUFFER IN DAYS FOR 100% EFF.</th>
                <th colSpan={columns.length * 2 - 4} className="text-blue font-xl">DBBB</th>
                <th colSpan="2" className="text-blue">SHARED OPERATION</th>
              </tr>
            )}

            {/* 3rd Header Row (Channels) */}
            <tr className="header-row">
              <th className="text-blue" style={{minWidth: '100px'}}>CHANNEL</th>
              {columns.map(col => (
                <th key={col} colSpan="2" className="text-blue column-title">{col}</th>
              ))}
            </tr>
            
            {/* 4th Header Row (IR / OR) */}
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
                
                {row.key !== 'spacer' ? columns.map(col => {
                  // Check if this cell block should be disabled/merged
                  const isDisabled = DISABLED_BLOCKS[sector][row.section]?.includes(col);

                  if (isDisabled) {
                    return <td key={`${row.key}-${col}-disabled`} colSpan="2" className="disabled-block"></td>;
                  }

                  return (
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
                  );
                }) : columns.map(col => (
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

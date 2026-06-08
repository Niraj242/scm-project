import React, { useState } from 'react';
import './Scrap.css';

const Scrap = () => {
  // Get today's date in YYYY-MM-DD format for default value
  const today = new Date().toISOString().split('T')[0];

  const [department, setDepartment] = useState('Heat Treatment');
  const [date, setDate] = useState(today);
  const [shift, setShift] = useState('Shift 1');
  const [category, setCategory] = useState('Industrial'); // Industrial or Automotive

  // --- TABLE DATA STRUCTURES BASED ON IMAGES ---

  const htFurnaces = [
    'Aichelin Unitherm', 'Roller', 'Birlec', 'Castlink', 
    'Aichelin', 'Shoei', 'Simplicity', 'Other-'
  ];

  const fodMachines = [
    'DDS 709+1186', 'DDS 544', 'Gardner1016 + USA 1996', 'Gardner1601', 'S14-1584', 
    'Gardner BG1-1973', 'SDG-2225', 'SLDP-166', 'TOTAL', 
    'COL 46 1125+661', 'CL 46-839+945', 'CL-46 1600+1903', 'CL 46 -1904+170', 
    'CL 46 1585', 'CL 46 2021 AMHD', 'CL 3 BG -660', 'CL-660-2223'
  ];

  const dgbbProcesses = [
    "1. IR FACE GRINDING", "2. IR GROOVE GRINDING", "3. IR BORE GRINDING", 
    "4. GRD. BURN TEST SC. IR", "5. IR AT BALL FILLING", "6. OR FACE GRINDING", 
    "7. OR OD GRINDING", "8. OR GROOVE GRINDING", "9. OR GROOVE HONING", 
    "10. GRD. BURN TEST SC OR", "11. OR AT BALL FILLING", "12. SEAL", 
    "13. SHILD", "14. A SCRAP BEARING", "15. B SCRAP BEARING", 
    "16. C SCRAP BEARING", "17. C1/CS CLEARANCE SCRAP BEARING", 
    "18. VIBRATION SCRAP BEARING", "19. CAGES SCRAP BEARING", "20. OTHER BALLS (KG)"
  ];

  const dgbbChannels = ["CH01", "CH02", "CH03", "CH04", "CH05", "CH05(SABB)", "CH07", "CH08", "CH11", "CH12", "CH13"];

  // --- RENDER HELPERS ---

  const renderHeatTreatmentTable = () => (
    <div className="table-container">
      <table className="scrap-table">
        <thead>
          <tr>
            <th className="sticky-col">Furnace &darr;</th>
            {[1, 2, 3, 4].map(group => (
              <React.Fragment key={group}>
                <th>TYPE</th>
                <th>IR</th>
                <th>OR</th>
              </React.Fragment>
            ))}
            <th>Remark</th>
          </tr>
        </thead>
        <tbody>
          {htFurnaces.map((furnace, idx) => (
            <tr key={idx}>
              <td className="sticky-col font-bold">{furnace}</td>
              {[...Array(12)].map((_, colIdx) => (
                <td key={colIdx}><input type="text" className="cell-input" /></td>
              ))}
              <td><input type="text" className="cell-input" /></td>
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
            {[1, 2, 3, 4].map(group => (
              <React.Fragment key={group}>
                <th>TYPE</th>
                <th>IR</th>
                <th>OR</th>
                <th>MO</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {fodMachines.map((machine, idx) => (
            <tr key={idx} className={machine === 'TOTAL' ? 'row-highlight' : ''}>
              <td className="sticky-col font-bold">{machine}</td>
              {[...Array(16)].map((_, colIdx) => (
                <td key={colIdx}><input type="text" className="cell-input" /></td>
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
            {dgbbChannels.map((ch, idx) => (
              <th key={`sub-${idx}`} className="sub-header">
                <input type="text" placeholder="MO. NO." className="header-input" />
                <input type="text" placeholder="TYPE" className="header-input" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dgbbProcesses.map((process, idx) => (
            <tr key={idx}>
              <td className="sticky-col process-cell">{process}</td>
              {dgbbChannels.map((_, colIdx) => (
                <td key={colIdx}><input type="number" className="cell-input" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Daily Scrap Entry Module</h2>
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

          {(department === 'Heat Treatment' || department === 'Face and OD') && (
            <div className="control-group category-select">
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

        </div>
      </div>

      <div className="table-wrapper">
        <div className="table-title">
          <h3>
            {category.toUpperCase()} - {department.toUpperCase()} - DAILY SCRAP REPORT
          </h3>
        </div>
        
        {department === 'Heat Treatment' && renderHeatTreatmentTable()}
        {department === 'Face and OD' && renderFaceAndODTable()}
        {department === 'DGBB' && renderDGBBTable()}
        {department === 'TRB' && <div className="placeholder">TRB Table Format Pending...</div>}
      </div>

      <div className="action-row">
        <button className="submit-btn">Save to Database</button>
      </div>
    </div>
  );
};

export default Scrap;

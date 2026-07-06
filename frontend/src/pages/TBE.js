import React, { useState, useEffect, useRef } from 'react';
import './TBE.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');
  const [showCalcHelp, setShowCalcHelp] = useState(false);
  
  // Drilldown Breakout States
  const [selectedFamily, setSelectedFamily] = useState(null); 
  const [detailData, setDetailData] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // --- CALCULATOR STATES ---
  const [selectedCells, setSelectedCells] = useState({});
  const [isDragging, setIsDragging] = useState(false);
  const [calcResult, setCalcResult] = useState(null);
  const [currentOperation, setCurrentOperation] = useState(null);

  const timerRef = useRef(null);

  // --- CALCULATOR LOGIC ---
  const selectionTotal = Object.values(selectedCells).reduce((sum, val) => sum + val, 0);

  const handleMouseDown = (e, cellId, value) => {
    // Left click only
    if (e.button !== 0) return;
    
    const numVal = parseFloat(String(value).replace(/,/g, '')) || 0;
    
    if (e.ctrlKey || e.metaKey) {
      // Toggle selection with Ctrl/Cmd
      setSelectedCells(prev => {
        const newSel = { ...prev };
        if (newSel[cellId] !== undefined) {
          delete newSel[cellId];
        } else {
          newSel[cellId] = numVal;
        }
        return newSel;
      });
    } else {
      // Normal click: Start fresh selection
      setSelectedCells({ [cellId]: numVal });
    }
    
    setIsDragging(true);
  };

  const handleMouseEnter = (e, cellId, value) => {
    if (!isDragging) return;
    const numVal = parseFloat(String(value).replace(/,/g, '')) || 0;
    setSelectedCells(prev => ({ ...prev, [cellId]: numVal }));
  };

  useEffect(() => {
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener('mouseup', handleMouseUp);
    return () => window.removeEventListener('mouseup', handleMouseUp);
  }, []);

  const handleCalcOp = (op) => {
    if (op === 'C') {
      setCalcResult(null);
      setCurrentOperation(null);
      setSelectedCells({});
      return;
    }

    if (op === '=') {
      if (currentOperation && calcResult !== null) {
        let res = calcResult;
        if (currentOperation === '+') res += selectionTotal;
        if (currentOperation === '-') res -= selectionTotal;
        if (currentOperation === '*') res *= selectionTotal;
        if (currentOperation === '/') res = selectionTotal !== 0 ? res / selectionTotal : 0;
        
        setCalcResult(res);
        setCurrentOperation(null);
        setSelectedCells({});
      }
      return;
    }

    // Set operation (+, -, *, /)
    if (calcResult === null) {
      setCalcResult(selectionTotal);
    } else if (currentOperation) {
      let res = calcResult;
      if (currentOperation === '+') res += selectionTotal;
      if (currentOperation === '-') res -= selectionTotal;
      if (currentOperation === '*') res *= selectionTotal;
      if (currentOperation === '/') res = selectionTotal !== 0 ? res / selectionTotal : 0;
      setCalcResult(res);
    }
    setCurrentOperation(op);
    setSelectedCells({});
  };

  // Re-fetch data whenever date filters change to calculate strict sums server-side
  useEffect(() => {
    fetchTBEDashboard();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [startDate, endDate]);

  useEffect(() => {
    if (!selectedFamily) {
      setDetailData([]);
      return;
    }

    const fetchVariantDetails = async () => {
      try {
        setDetailLoading(true);
        let url = `${API}/tbe_variant_details?ch=${encodeURIComponent(selectedFamily.ch)}&fam=${encodeURIComponent(selectedFamily.fam)}`;
        if (startDate) url += `&start_date=${startDate}`;
        if (endDate) url += `&end_date=${endDate}`;

        const res = await fetch(url);
        if (!res.ok) throw new Error("Could not retrieve variant sequential logs.");
        const json = await res.json();
        setDetailData(json.data || []);
      } catch (err) {
        console.error(err.message);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchVariantDetails();
  }, [selectedFamily, startDate, endDate]);

  const fetchTBEDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');

      let url = `${API}/tbe_all_mos`;
      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) url += `?${queryParams.join('&')}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error(`Server returned status code: ${res.status}`);
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
      console.log("API returned:", json.data.length);
      console.table(json.data);

       setSummaryData(json.data || []);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(fetchTBEDashboard, 4000);
      } else {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      }
    } catch (err) {
      setIsInitializing(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(item => {
    return (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
      (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase())) ||
      (item.mo_ref && String(item.mo_ref).toLowerCase().includes(search.toLowerCase()));
  });

  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.channel_ref !== b.channel_ref) {
      return String(a.channel_ref || '').localeCompare(String(b.channel_ref || ''));
    }
    if (a.product_variant !== b.product_variant) {
      return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
    }
    return String(a.ring_type || '').localeCompare(String(b.ring_type || ''));
  });

  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    if (!currentRef) return 1;
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef) return 0; 
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef) {
      span++;
    }
    return span;
  };

  const getFamilyRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    const currentFam = dataArray[currentIndex].product_variant;
    if (!currentRef || !currentFam) return 1;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].channel_ref === currentRef &&
        dataArray[currentIndex - 1].product_variant === currentFam) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && 
           dataArray[currentIndex + span].channel_ref === currentRef &&
           dataArray[currentIndex + span].product_variant === currentFam) {
      span++;
    }
    return span;
  };

  // Check if calculator should be visible
const isCalcActive = true;

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>Transit Buffer Entry Tracking Log</h1>
          <p className="sub-tag">Synchronized Channel & Ring Family Sequencing Matrices</p>
        </div>
        
        {/* --- CALCULATOR WIDGET --- */}
<div className="calculator-area">

  <button
    className="calc-help-btn"
    onClick={() => setShowCalcHelp(true)}
  >
    ℹ Calculator Guide
  </button>

  <div className={`calc-widget ${isCalcActive ? 'calc-widget-visible' : 'calc-widget-hidden'}`}>
    <span className="calc-display">
      {calcResult !== null ? calcResult.toLocaleString() : ''}
      {currentOperation ? ` ${currentOperation} ` : ''}
      {(selectionTotal !== 0 || calcResult === null)
        ? selectionTotal.toLocaleString()
        : ''}
    </span>

    <div className="calc-buttons">
      <button className="calc-btn" onClick={() => handleCalcOp('+')}>+</button>
      <button className="calc-btn" onClick={() => handleCalcOp('-')}>-</button>
      <button className="calc-btn" onClick={() => handleCalcOp('*')}>*</button>
      <button className="calc-btn" onClick={() => handleCalcOp('/')}>/</button>
      <button className="calc-btn calc-btn-eq" onClick={() => handleCalcOp('=')}>=</button>
      <button className="calc-btn calc-btn-clear" onClick={() => handleCalcOp('C')}>C</button>
    </div>
  </div>

  {showCalcHelp && (
    <div className="calc-modal-overlay">
      <div className="calc-modal">

        <h3>Calculator Guide</h3>

        <ul>
          <li>Click and drag over quantity cells.</li>
          <li>Selected quantities are automatically added.</li>
          <li>Use +, −, × and ÷ buttons for calculations.</li>
          <li>Press = to calculate.</li>
          <li>Press C to clear the calculator.</li>
          <li>The calculator always displays the latest selected total.</li>
        </ul>

        <button
          className="calc-close-btn"
          onClick={() => setShowCalcHelp(false)}
        >
          Close
        </button>

      </div>
    </div>
  )}

</div>
        

        <div className="control-actions">
          <input 
            type="date" 
            className="search-box" 
            title="Start Date"
            value={startDate} 
            onChange={(e) => setStartDate(e.target.value)} 
          />
          <span className="date-range-separator">to</span>
          <input 
            type="date" 
            className="search-box" 
            title="End Date"
            value={endDate} 
            onChange={(e) => setEndDate(e.target.value)} 
          />

          <button className="back-btn reload-btn" onClick={fetchTBEDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>
          
          <input
            className="search-box"
            placeholder="Search Channel, MO, or Family..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={isInitializing}
          />
        </div>
      </div>

      {error && <div className="error-box">⚠️ Network Error: {error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>Compiling Remote Workbook Matrix Caches...</strong></p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying server memory buffer...</div>}

      {!loading && !isInitializing && (
        /* Dynamic container giving constrained height + elegant card framing shadow */
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              {/* Row 1 Sticky Headers with high-contrast distinct section colors */}
              <tr className="super-header">
                <th colSpan="4" className="th-meta">Connection Mapping</th>
                <th colSpan="3" className="th-sho">SHO Department & Scrap (Split)</th>
                <th colSpan="2" className="th-tb">Transit Buffer (Split)</th>
                <th colSpan="3" className="th-ch">Channel Section (Combined Rollup)</th>
                <th className="th-status">Status Tracker</th>
              </tr>
              {/* Row 2 Sticky Headers with corresponding matching tint colors */}
              <tr className="sub-header">
                <th className="sub-meta">Channel Ref</th>
                <th className="sub-meta">MO</th>
                <th className="sub-meta">Ring Family</th>
                <th className="sub-meta">Ring Type</th>
                
                <th className="sub-sho">Qty</th>
                <th className="sub-sho">In Date</th>
                {/* NEW SCRAP COLUMN INJECTED HERE */}
                <th className="sub-scrap">Scrap Qty</th>

                <th className="sub-tb">Qty</th>
                <th className="sub-tb">Out Date</th>
                
                <th className="sub-ch">Qty</th>
                <th className="sub-ch">In Date</th>
                <th className="sub-ch">Out Date</th>
                
                <th className="sub-status">Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                const familySpan = getFamilyRowSpan(sortedSummary, idx);
                const uniqueKey = `${row.channel_ref || 'b'}-${row.product_variant || 'b'}-${row.ring_type || 'b'}-${idx}`;

                return (
                  <tr key={uniqueKey} className="data-row">
                    {/* Channel Column */}
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-mo-cell fw-bold">
                        {row.channel_ref || '-'}
                      </td>
                    )}
                    
                    {/* MO Column */}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-mo-cell text-muted">
                        {row.mo_ref || '-'}
                      </td>
                    )}

                    {/* Ring Family Column */}
                    {familySpan > 0 && (
                      <td 
                        rowSpan={familySpan} 
                        className="fw-bold text-primary clickable-family-cell"
                        title="Click to view full variant routing entries"
                        onClick={() => setSelectedFamily({ ch: row.channel_ref, fam: row.product_variant })}
                      >
                        {row.product_variant}
                      </td>
                    )}
                    
                    {/* Ring Type Column */}
                    <td className="fw-bold cell-ring-type">{row.ring_type}</td>
                    
                    {/* SHO Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `sho-${idx}`, row.sho_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `sho-${idx}`, row.sho_qty)}
                      className={`cell-selectable cell-sho ${selectedCells[`sho-${idx}`] !== undefined ? 'cell-sho-selected' : ''}`}>
                      {row.sho_qty ? Number(row.sho_qty).toLocaleString() : '0'}
                    </td>
                    <td className="cell-plain-sho">{row.sho_in || '-'}</td>
                    
                    {/* SCRAP Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `scrap-${idx}`, row.scrap_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `scrap-${idx}`, row.scrap_qty)}
                      className={`cell-selectable cell-scrap ${selectedCells[`scrap-${idx}`] !== undefined ? 'cell-scrap-selected' : ''}`}>
                      {row.scrap_qty ? Number(row.scrap_qty).toLocaleString() : '0'}
                    </td>

                    {/* TB Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `tb-${idx}`, row.tb_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `tb-${idx}`, row.tb_qty)}
                      className={`cell-selectable cell-tb ${selectedCells[`tb-${idx}`] !== undefined ? 'cell-tb-selected' : ''}`}>
                      {row.tb_qty ? Number(row.tb_qty).toLocaleString() : '0'}
                    </td>
                    <td className="cell-plain-tb">{row.tb_out || '-'}</td>
                    
                    {/* Channel Section */}
                    {familySpan > 0 && (
                      <td 
                        rowSpan={familySpan} 
                        className={`merged-channel-cell fw-bold cell-selectable cell-ch-qty ${selectedCells[`ch-${idx}`] !== undefined ? 'cell-ch-qty-selected' : ''}`}
                        onMouseDown={(e) => handleMouseDown(e, `ch-${idx}`, row.ch_qty)}
                        onMouseEnter={(e) => handleMouseEnter(e, `ch-${idx}`, row.ch_qty)}>
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell cell-plain-ch">{row.ch_in || '-'}</td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell cell-plain-ch">{row.ch_out || '-'}</td>
                    )}
                    
                    {/* Status Tracker */}
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`}>
                        {row.status || 'In Process'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="13" className="empty-state">
                    No records found matching the current search criteria or date range.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Redesigned Stacked Layout Detail Breakdown Modal */}
      {selectedFamily && (
        <div className="modal-overlay" onClick={() => setSelectedFamily(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>Variant Specific Location Breakdown</h3>
                <p className="modal-subheading">Family Scope: <strong>{selectedFamily.fam}</strong></p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedFamily(null)}>&times;</button>
            </div>
            <div className="modal-body">
              {detailLoading ? (
                <div className="detail-loading-box">
                  <div className="spinner"></div>
                  <p>Querying breakdown registries...</p>
                </div>
              ) : detailData.length === 0 ? (
                <div className="empty-state">No independent deployment logs located for this variant structure within chosen dates.</div>
              ) : (
                <div className="modal-table-wrapper">
                  <table className="detail-variant-table">
                    <thead>
                      <tr>
                        <th className="text-start">MO / Channel Reference</th>
                        <th className="text-start">Department / Specific Location</th>
                        <th className="text-start">Product / Part Sub Variant</th>
                        <th>In Date</th>
                        <th>Out Date</th>
                        <th>Qty</th>
                        <th>Execution Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.map((vRow, vIdx) => (
                        <tr key={vIdx} className="modal-data-row">
                          <td className="text-start text-muted">{vRow.mo_ref}</td>
                          <td className="text-start">
                            <span className={`dept-tag ${vRow.department.toLowerCase().replace(/\s+/g, '-')}`}>
                              {vRow.department}
                            </span>
                          </td>
                          <td className="text-start fw-bold">{vRow.variant}</td>
                          <td>{vRow.in_date}</td>
                          <td>{vRow.out_date}</td>
                          <td 
                            className={`fw-bold cell-selectable cell-modal-qty ${selectedCells[`modal-qty-${vIdx}`] !== undefined ? 'cell-modal-qty-selected' : ''}`}
                            onMouseDown={(e) => handleMouseDown(e, `modal-qty-${vIdx}`, vRow.qty)}
                            onMouseEnter={(e) => handleMouseEnter(e, `modal-qty-${vIdx}`, vRow.qty)}>
                            {Number(vRow.qty).toLocaleString()}
                          </td>
                          <td>
                            <span className="execution-status-dot">{vRow.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TBE;
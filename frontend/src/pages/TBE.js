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
  
  // Drilldown Breakout States
  const [selectedFamily, setSelectedFamily] = useState(null); 
  const [detailData, setDetailData] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // --- SORTING STATE ---
  const [sortConfig, setSortConfig] = useState(null);

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
        setSummaryData([]);
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

  // --- SORTING HELPER FUNCTIONS ---
  const parseDate = (dateStr) => {
    if (!dateStr || dateStr === '-') return 0;
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      // Assuming dd-mm-yyyy format
      return new Date(parts[2], parts[1] - 1, parts[0]).getTime();
    }
    return 0;
  };

  const getEarliestDate = (row) => {
    const d1 = parseDate(row.sho_in);
    const d2 = parseDate(row.ch_in);
    if (d1 === 0) return d2;
    if (d2 === 0) return d1;
    return Math.min(d1, d2);
  };

  const requestSort = (key) => {
    let direction = 'ascending';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending';
    }
    setSortConfig({ key, direction });
  };

  const getSortIcon = (name) => {
    if (!sortConfig || sortConfig.key !== name) return '↕';
    return sortConfig.direction === 'ascending' ? '▲' : '▼';
  };

  const filteredSummary = summaryData.filter(item => {
    return (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
      (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase())) ||
      (item.mo_ref && String(item.mo_ref).toLowerCase().includes(search.toLowerCase()));
  });

  // --- REVISED SORTING LOGIC ---
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    // If no specific column is clicked, default to Date-based sorting instead of Family
    if (!sortConfig) {
      const dateA = getEarliestDate(a);
      const dateB = getEarliestDate(b);
      return dateA - dateB;
    }

    const { key, direction } = sortConfig;
    const valA = a[key];
    const valB = b[key];

    const isDate = ['sho_in', 'tb_out', 'ch_in', 'ch_out'].includes(key);
    const isNum = ['sho_qty', 'scrap_qty', 'tb_qty', 'ch_qty'].includes(key);

    if (isDate) {
      const dA = parseDate(valA);
      const dB = parseDate(valB);
      return direction === 'ascending' ? dA - dB : dB - dA;
    }

    if (isNum) {
      const numA = Number(valA) || 0;
      const numB = Number(valB) || 0;
      return direction === 'ascending' ? numA - numB : numB - numA;
    }

    // String sorting (A to Z)
    const strA = String(valA || '').toLowerCase();
    const strB = String(valB || '').toLowerCase();
    if (strA < strB) return direction === 'ascending' ? -1 : 1;
    if (strA > strB) return direction === 'ascending' ? 1 : -1;
    return 0;
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
  const isCalcActive = Object.keys(selectedCells).length > 0 || calcResult !== null;

  return (
    <div className="traceability-container" style={{ fontFamily: 'Segoe UI, Roboto, sans-serif' }}>
      <div className="header-section" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
        <div>
          <h1>Transit Buffer Entry Tracking Log</h1>
          <p className="sub-tag">Synchronized Channel & Ring Family Sequencing Matrices</p>
        </div>
        
        {/* --- CALCULATOR WIDGET --- */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 14px', 
          background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', 
          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
          visibility: isCalcActive ? 'visible' : 'hidden',
          transition: 'opacity 0.2s'
        }}>
          <span style={{ fontFamily: 'monospace', fontWeight: 'bold', fontSize: '1.2em', color: '#0f172a', minWidth: '100px', textAlign: 'right' }}>
            {calcResult !== null ? calcResult.toLocaleString() : ''}
            {currentOperation ? ` ${currentOperation} ` : ''}
            {(selectionTotal !== 0 || calcResult === null) ? selectionTotal.toLocaleString() : ''}
          </span>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('+')}>+</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('-')}>-</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('*')}>*</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('/')}>/</button>
            <button style={{ padding: '2px 8px', border: '1px solid #3b82f6', background: '#eff6ff', color: '#1d4ed8', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('=')}>=</button>
            <button style={{ padding: '2px 8px', border: '1px solid #f87171', background: '#fef2f2', color: '#b91c1c', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('C')}>C</button>
          </div>
        </div>

        <div className="control-actions">
          <input 
            type="date" 
            className="search-box" 
            title="Start Date"
            value={startDate} 
            onChange={(e) => setStartDate(e.target.value)} 
          />
          <span style={{margin: '0 5px', color: '#64748b'}}>to</span>
          <input 
            type="date" 
            className="search-box" 
            title="End Date"
            value={endDate} 
            onChange={(e) => setEndDate(e.target.value)} 
          />

          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchTBEDashboard} disabled={loading}>
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
        <div className="table-wrapper" style={{ maxHeight: '680px', overflowY: 'auto', border: '1px solid #cbd5e1', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)', position: 'relative' }}>
          <table className="trace-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center' }}>
            <thead>
              {/* Row 1 Sticky Headers with high-contrast distinct section colors */}
              <tr className="super-header" style={{ height: '42px' }}>
                <th colSpan="4" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#334155', color: '#ffffff', border: '1px solid #475569', fontWeight: '600', padding: '10px' }}>Connection Mapping</th>
                <th colSpan="3" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#0284c7', color: '#ffffff', border: '1px solid #0369a1', fontWeight: '600', padding: '10px' }}>SHO Department & Scrap (Split)</th>
                <th colSpan="2" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#ea580c', color: '#ffffff', border: '1px solid #c2410c', fontWeight: '600', padding: '10px' }}>Transit Buffer (Split)</th>
                <th colSpan="3" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#16a34a', color: '#ffffff', border: '1px solid #15803d', fontWeight: '600', padding: '10px' }}>Channel Section (Combined Rollup)</th>
                <th style={{ position: 'sticky', top: 0, zIndex: 10, background: '#475569', color: '#ffffff', border: '1px solid #576880', fontWeight: '600', padding: '10px' }}>Status Tracker</th>
              </tr>
              {/* Row 2 Sticky Headers with corresponding matching tint colors & sortable capabilities */}
              <tr className="sub-header" style={{ height: '38px', userSelect: 'none' }}>
                <th onClick={() => requestSort('channel_ref')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Channel Ref</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('channel_ref')}</span></div>
                </th>
                <th onClick={() => requestSort('mo_ref')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>MO</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('mo_ref')}</span></div>
                </th>
                <th onClick={() => requestSort('product_variant')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Ring Family</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('product_variant')}</span></div>
                </th>
                <th onClick={() => requestSort('ring_type')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Ring Type</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('ring_type')}</span></div>
                </th>
                
                <th onClick={() => requestSort('sho_qty')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Qty</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('sho_qty')}</span></div>
                </th>
                <th onClick={() => requestSort('sho_in')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>In Date</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('sho_in')}</span></div>
                </th>
                <th onClick={() => requestSort('scrap_qty')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Scrap Qty</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('scrap_qty')}</span></div>
                </th>

                <th onClick={() => requestSort('tb_qty')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#ffedd5', color: '#9a3412', border: '1px solid #fed7aa', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Qty</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('tb_qty')}</span></div>
                </th>
                <th onClick={() => requestSort('tb_out')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#ffedd5', color: '#9a3412', border: '1px solid #fed7aa', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Out Date</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('tb_out')}</span></div>
                </th>
                
                <th onClick={() => requestSort('ch_qty')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#dcfce7', color: '#15803d', border: '1px solid #bbf7d0', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Qty</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('ch_qty')}</span></div>
                </th>
                <th onClick={() => requestSort('ch_in')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#dcfce7', color: '#15803d', border: '1px solid #bbf7d0', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>In Date</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('ch_in')}</span></div>
                </th>
                <th onClick={() => requestSort('ch_out')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#dcfce7', color: '#15803d', border: '1px solid #bbf7d0', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Out Date</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('ch_out')}</span></div>
                </th>
                
                <th onClick={() => requestSort('status')} style={{ cursor: 'pointer', position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}><span>Tracking Status</span><span style={{fontSize: '0.8em', opacity: 0.6}}>{getSortIcon('status')}</span></div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                const familySpan = getFamilyRowSpan(sortedSummary, idx);
                const uniqueKey = `${row.channel_ref || 'b'}-${row.product_variant || 'b'}-${row.ring_type || 'b'}-${idx}`;
                
                // Beautiful subtle zebra lines for alternate rows
                const rowBg = idx % 2 === 0 ? '#ffffff' : '#fdfdfd';

                return (
                  <tr key={uniqueKey} className="data-row" style={{ backgroundColor: rowBg, transition: 'background 0.2s' }}>
                    {/* Channel Column */}
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-mo-cell fw-bold" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f1f5f9', color: '#334155', verticalAlign: 'middle' }}>
                        {row.channel_ref || '-'}
                      </td>
                    )}
                    
                    {/* MO Column */}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-mo-cell text-muted" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f8fafc', fontSize: '0.9em', verticalAlign: 'middle' }}>
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
                        style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0f9ff', color: '#0284c7', cursor: 'pointer', verticalAlign: 'middle', textDecoration: 'underline' }}
                      >
                        {row.product_variant}
                      </td>
                    )}
                    
                    {/* Ring Type Column */}
                    <td className="fw-bold" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#1e293b' }}>{row.ring_type}</td>
                    
                    {/* SHO Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `sho-${idx}`, row.sho_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `sho-${idx}`, row.sho_qty)}
                      style={{ 
                        border: '1px solid #e2e8f0', padding: '11px 10px', color: '#0369a1', 
                        background: selectedCells[`sho-${idx}`] !== undefined ? '#bae6fd' : '#f0f9ff',
                        userSelect: 'none', cursor: 'cell' 
                      }}>
                      {row.sho_qty ? Number(row.sho_qty).toLocaleString() : '0'}
                    </td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#0369a1', background: '#f0f9ff' }}>{row.sho_in || '-'}</td>
                    
                    {/* SCRAP Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `scrap-${idx}`, row.scrap_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `scrap-${idx}`, row.scrap_qty)}
                      style={{ 
                        border: '1px solid #e2e8f0', padding: '11px 10px', color: '#b91c1c', 
                        background: selectedCells[`scrap-${idx}`] !== undefined ? '#fecaca' : '#fef2f2',
                        userSelect: 'none', cursor: 'cell', fontWeight: 'bold'
                      }}>
                      {row.scrap_qty ? Number(row.scrap_qty).toLocaleString() : '0'}
                    </td>

                    {/* TB Split */}
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `tb-${idx}`, row.tb_qty)}
                      onMouseEnter={(e) => handleMouseEnter(e, `tb-${idx}`, row.tb_qty)}
                      style={{ 
                        border: '1px solid #e2e8f0', padding: '11px 10px', color: '#c2410c', 
                        background: selectedCells[`tb-${idx}`] !== undefined ? '#fed7aa' : '#fff7ed',
                        userSelect: 'none', cursor: 'cell'
                      }}>
                      {row.tb_qty ? Number(row.tb_qty).toLocaleString() : '0'}
                    </td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#c2410c', background: '#fff7ed' }}>{row.tb_out || '-'}</td>
                    
                    {/* Channel Section */}
                    {familySpan > 0 && (
                      <td 
                        rowSpan={familySpan} 
                        className="merged-channel-cell fw-bold text-success" 
                        onMouseDown={(e) => handleMouseDown(e, `ch-${idx}`, row.ch_qty)}
                        onMouseEnter={(e) => handleMouseEnter(e, `ch-${idx}`, row.ch_qty)}
                        style={{ 
                          border: '1px solid #e2e8f0', padding: '11px 10px', 
                          background: selectedCells[`ch-${idx}`] !== undefined ? '#bbf7d0' : '#f0fdf4', 
                          color: '#16a34a', verticalAlign: 'middle', userSelect: 'none', cursor: 'cell'
                        }}>
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0fdf4', color: '#1e293b', verticalAlign: 'middle' }}>{row.ch_in || '-'}</td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0fdf4', color: '#1e293b', verticalAlign: 'middle' }}>{row.ch_out || '-'}</td>
                    )}
                    
                    {/* Status Tracker */}
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px' }}>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`}>
                        {row.status || 'In Process'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="13" className="empty-state" style={{ padding: '30px', color: '#64748b', fontStyle: 'italic' }}>
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
                <div className="modal-table-wrapper" style={{ maxHeight: '420px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <table className="detail-variant-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#334155', color: '#ffffff', height: '40px' }}>
                        <th style={{ textAlign: 'left', padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>MO / Channel Reference</th>
                        <th style={{ textAlign: 'left', padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>Department / Specific Location</th>
                        <th style={{ textAlign: 'left', padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>Product / Part Sub Variant</th>
                        <th style={{ padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>In Date</th>
                        <th style={{ padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>Out Date</th>
                        <th style={{ padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>Qty</th>
                        <th style={{ padding: '10px', position: 'sticky', top: 0, background: '#334155', zIndex: 1 }}>Execution Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.map((vRow, vIdx) => (
                        <tr key={vIdx} className="modal-data-row" style={{ background: vIdx % 2 === 0 ? '#ffffff' : '#f8fafc' }}>
                          <td className="text-start text-muted" style={{ fontSize: '0.95em', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.mo_ref}</td>
                          <td className="text-start" style={{ padding: '10px', borderBottom: '1px solid #e2e8f0' }}>
                            <span className={`dept-tag ${vRow.department.toLowerCase().replace(/\s+/g, '-')}`}>
                              {vRow.department}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{ color: '#0f172a', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.variant}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.in_date}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.out_date}</td>
                          <td 
                            className="fw-bold" 
                            onMouseDown={(e) => handleMouseDown(e, `modal-qty-${vIdx}`, vRow.qty)}
                            onMouseEnter={(e) => handleMouseEnter(e, `modal-qty-${vIdx}`, vRow.qty)}
                            style={{ 
                              padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center',
                              background: selectedCells[`modal-qty-${vIdx}`] !== undefined ? '#bae6fd' : 'inherit',
                              userSelect: 'none', cursor: 'cell' 
                            }}>
                            {Number(vRow.qty).toLocaleString()}
                          </td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
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

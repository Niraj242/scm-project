import React, { useState, useEffect, useRef } from 'react';
import './Traceability.css'; 

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
  const [summaryData, setSummaryData] = useState([]);
  
  // Drilldown Breakout States
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');
  
  const timerRef = useRef(null);

  // Re-fetch data whenever date filters change
  useEffect(() => {
    fetchSummaryDashboard();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [startDate, endDate]);

  const fetchSummaryDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');
      
      // Append date filters to the API call
      let url = `${API}/traceability_all_mos`;
      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) url += `?${queryParams.join('&')}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error('Network error pulling records.');
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setSummaryData([]);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(fetchSummaryDashboard, 4000);
      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data);
      }
    } catch (err) {
      setIsInitializing(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (moString) => {
    try {
      // Open modal frame immediately and show loading spinner inside it
      setSelectedMoFlow({ mo: moString, flow_data: [] }); 
      setDetailLoading(true);
      
      // Append date filters to the drill-down report as well
      let url = `${API}/traceability_report/${moString.trim()}`;
      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) url += `?${queryParams.join('&')}`;
      
      const res = await fetch(url);
      if (!res.ok) throw new Error('Could not pull variant flow.');
      const json = await res.json();
      
      if (json.status === 'success') {
        setSelectedMoFlow({
          mo: json.data.mo || moString,
          flow_data: json.data.rows || [] 
        });
      }
    } catch (err) {
      console.error(err.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(item => 
    (item.mo && String(item.mo).toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

  const getRowSpan = (dataArray, currentIndex, keyField) => {
    const currentVal = dataArray[currentIndex][keyField];
    if (currentIndex > 0 && dataArray[currentIndex - 1][keyField] === currentVal) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span][keyField] === currentVal) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container" style={{ fontFamily: 'Segoe UI, Roboto, sans-serif' }}>
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag">Global Order Summary by Family</p>
        </div>
        
        <div className="control-actions">
          {/* New Date Filters Added Here */}
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

          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchSummaryDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>

          <input
            className="search-box"
            placeholder="Search MO or Family..."
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
          <p><strong>System Backend is warming up...</strong></p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner" style={{textAlign:'center', padding:'20px'}}>Querying server memory buffer...</div>}

      {/* MAIN DASHBOARD */}
      {!loading && !isInitializing && (
        <div className="table-wrapper" style={{ maxHeight: '680px', overflowY: 'auto', border: '1px solid #cbd5e1', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)', position: 'relative' }}>
          <table className="trace-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center' }}>
            <thead>
              <tr className="super-header" style={{ height: '42px' }}>
                <th colSpan="4" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#334155', color: '#ffffff', border: '1px solid #475569', fontWeight: '600', padding: '10px' }}>Order Details</th>
                <th colSpan="2" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#0284c7', color: '#ffffff', border: '1px solid #0369a1', fontWeight: '600', padding: '10px' }}>SHO Target</th>
                <th colSpan="2" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#ea580c', color: '#ffffff', border: '1px solid #c2410c', fontWeight: '600', padding: '10px' }}>Transit Buffer</th>
                <th colSpan="2" style={{ position: 'sticky', top: 0, zIndex: 10, background: '#16a34a', color: '#ffffff', border: '1px solid #15803d', fontWeight: '600', padding: '10px' }}>Channel Section</th>
                <th style={{ position: 'sticky', top: 0, zIndex: 10, background: '#475569', color: '#ffffff', border: '1px solid #576880', fontWeight: '600', padding: '10px' }}>Overall Status</th>
              </tr>
              <tr className="sub-header" style={{ height: '38px' }}>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>MO Number</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>Family / Base Product</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>Component</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>Target Qty</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd', padding: '10px', fontSize: '0.9em' }}>SHO Qty</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd', padding: '10px', fontSize: '0.9em' }}>Date</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#ffedd5', color: '#9a3412', border: '1px solid #fed7aa', padding: '10px', fontSize: '0.9em' }}>TB Qty</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#ffedd5', color: '#9a3412', border: '1px solid #fed7aa', padding: '10px', fontSize: '0.9em' }}>Date</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#dcfce7', color: '#15803d', border: '1px solid #bbf7d0', padding: '10px', fontSize: '0.9em' }}>Chan Qty</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#dcfce7', color: '#15803d', border: '1px solid #bbf7d0', padding: '10px', fontSize: '0.9em' }}>Date</th>
                <th style={{ position: 'sticky', top: '42px', zIndex: 10, background: '#f8fafc', color: '#1e293b', border: '1px solid #cbd5e1', padding: '10px', fontSize: '0.9em' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSummary.map((row, idx) => {
                const moSpan = getRowSpan(filteredSummary, idx, 'mo');
                const rowBg = idx % 2 === 0 ? '#ffffff' : '#fdfdfd';

                return (
                  <tr key={idx} className="data-row" style={{ backgroundColor: rowBg, transition: 'background 0.2s' }}>
                    {moSpan > 0 && (
                      <td 
                        rowSpan={moSpan} 
                        className="merged-mo-cell fw-bold text-primary clickable-family-cell"
                        title="Click to view full variant breakdown"
                        style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0f9ff', color: '#0284c7', cursor: 'pointer', verticalAlign: 'middle', textDecoration: 'underline' }}
                        onClick={() => handleViewDetail(row.mo)}
                      >
                        {row.mo}
                      </td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell fw-bold" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f1f5f9', color: '#334155', verticalAlign: 'middle' }}>
                        {row.base_product}
                      </td>
                    )}
                    
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', fontWeight: 600, color: row.component === 'IM' ? '#0369a1' : '#b45309' }}>
                      {row.component}
                    </td>
                    <td className="qty-cell" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#1e293b' }}>{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#0369a1', background: '#f0f9ff' }}>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#0369a1', background: '#f0f9ff' }}>{row.sho_date || '-'}</td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#c2410c', background: '#fff7ed' }}>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td style={{ border: '1px solid #e2e8f0', padding: '11px 10px', color: '#c2410c', background: '#fff7ed' }}>{row.tb_date || '-'}</td>
                    
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell fw-bold text-success" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0fdf4', color: '#16a34a', verticalAlign: 'middle' }}>
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}
                      </td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0fdf4', color: '#1e293b', verticalAlign: 'middle' }}>{row.ch_date || '-'}</td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell" style={{ border: '1px solid #e2e8f0', padding: '11px 10px', background: '#f0fdf4', verticalAlign: 'middle' }}>
                        <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : ''}`}>
                          {row.status || 'In Process'}
                        </span>
                      </td>
                    )}
                  </tr>
                );
              })}
              {filteredSummary.length === 0 && (
                <tr>
                  <td colSpan="11" className="empty-state" style={{ padding: '30px', color: '#64748b', fontStyle: 'italic' }}>
                    No records found matching the current search criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* DRILLDOWN MODAL */}
      {selectedMoFlow && (
        <div className="modal-overlay" onClick={() => setSelectedMoFlow(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>Variant Specific Location Breakdown</h3>
                <p className="modal-subheading">MO Scope: <strong>{selectedMoFlow.mo}</strong></p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedMoFlow(null)}>&times;</button>
            </div>
            <div className="modal-body">
              {detailLoading ? (
                <div className="detail-loading-box">
                  <div className="spinner"></div>
                  <p>Querying breakdown registries...</p>
                </div>
              ) : selectedMoFlow.flow_data.length === 0 ? (
                <div className="empty-state">No independent deployment logs located for this MO structure.</div>
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
                      {selectedMoFlow.flow_data.map((vRow, vIdx) => (
                        <tr key={vIdx} className="modal-data-row" style={{ background: vIdx % 2 === 0 ? '#ffffff' : '#f8fafc' }}>
                          <td className="text-start text-muted" style={{ fontSize: '0.95em', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.mo_ref || selectedMoFlow.mo}</td>
                          <td className="text-start" style={{ padding: '10px', borderBottom: '1px solid #e2e8f0' }}>
                            <span className={`dept-tag ${vRow.department ? vRow.department.toLowerCase().replace(/\s+/g, '-') : ''}`}>
                              {vRow.department || '-'}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{ color: '#0f172a', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.variant || '-'}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.in_date || '-'}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.out_date || '-'}</td>
                          <td className="fw-bold" style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.qty ? Number(vRow.qty).toLocaleString() : '0'}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
                            <span className="execution-status-dot">{vRow.status || '-'}</span>
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

export default Traceability;

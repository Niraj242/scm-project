import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  const fetchSummaryDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records from pipeline.');
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setTimeout(fetchSummaryDashboard, 4000);
      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (moString) => {
    try {
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull tracking sequence for this production order.');
      const json = await res.json();
      
      if (json.status === 'success') {
        setSelectedMoFlow({
          mo: json.data.mo,
          flow_data: json.data.rows || []
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 1. Filter the data based on search
  const filteredSummary = summaryData.filter(item => 
    (item.mo && item.mo.toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. SORT the data by MO, AND THEN by Product Variant. 
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.mo !== b.mo) {
      return (a.mo || '').localeCompare(b.mo || '');
    }
    return String(a.base_product || '').localeCompare(String(b.base_product || ''));
  });

  // 3. Row Span Logic for MO Column
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo === currentMo) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo === currentMo) {
      span++;
    }
    return span;
  };

  // 4. Row Span Logic for Channel Column
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    const currentFamily = dataArray[currentIndex].base_product;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].mo === currentMo && 
        dataArray[currentIndex - 1].base_product === currentFamily) {
      return 0; 
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].mo === currentMo &&
      dataArray[currentIndex + span].base_product === currentFamily
    ) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container" style={{ fontSize: '15px' }}>
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag" style={{ fontSize: '16px', color: '#555' }}>
            {selectedMoFlow ? `Detailed Route Flow / Order: ${selectedMoFlow.mo}` : "Production Order Global KPI Summary Dashboard"}
          </p>
        </div>
        
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)} style={{ padding: '8px 16px', fontSize: '15px', cursor: 'pointer' }}>
              ← Back to Summary Dashboard
            </button>
          ) : (
            <input
              className="search-box"
              placeholder="Filter Dashboard Summary..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={isInitializing}
              style={{ padding: '8px 12px', fontSize: '15px', minWidth: '250px' }}
            />
          )}
        </div>
      </div>

      {error && <div className="error-box" style={{ padding: '15px', color: 'red', backgroundColor: '#fee2e2', marginBottom: '15px' }}>{error}</div>}
      
      {isInitializing && (
        <div className="initializing-box" style={{ textAlign: 'center', padding: '40px' }}>
          <div className="spinner"></div>
          <p style={{ fontSize: '18px' }}><strong>System Backend is warming up...</strong></p>
          <p className="sub-text">Downloading and parsing master excel configurations. Auto-refreshing in a few moments...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner" style={{ textAlign: 'center', padding: '20px', fontSize: '16px' }}>Querying Database Pipeline Cache...</div>}

      {/* VIEW BLOCK 1: MAIN SUMMARY DASHBOARD */}
      {!loading && !isInitializing && !selectedMoFlow && (
        <div className="table-wrapper" style={{ overflowX: 'auto', marginTop: '20px' }}>
          <table className="trace-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
            <thead style={{ backgroundColor: '#f8fafc' }}>
              <tr className="super-header">
                <th colSpan="4" className="meta-head" style={{ padding: '10px', border: '1px solid #ddd' }}>Order Metadata</th>
                <th colSpan="3" className="sho-head" style={{ padding: '10px', border: '1px solid #ddd', backgroundColor: '#e0f2fe' }}>SHO Department</th>
                <th colSpan="3" className="tb-head" style={{ padding: '10px', border: '1px solid #ddd', backgroundColor: '#fef08a' }}>Transit Buffer</th>
                <th colSpan="3" className="ch-head" style={{ padding: '10px', border: '1px solid #ddd', backgroundColor: '#dcfce3' }}>Channel Section (Combined)</th>
                <th className="meta-head" style={{ padding: '10px', border: '1px solid #ddd' }}>System Status</th>
              </tr>
              <tr className="sub-header">
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>MO Number</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Product Variant</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Target Qty</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Ring Type</th>
                
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Qty</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>In Date</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Out Date</th>
                
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Qty</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>In Date</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Out Date</th>
                
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Qty</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>In Date</th>
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Out Date</th>
                
                <th style={{ padding: '10px', border: '1px solid #ddd' }}>Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const moSpan = getMoRowSpan(sortedSummary, idx);
                const channelSpan = getChannelRowSpan(sortedSummary, idx); 
                
                return (
                  <tr key={idx} className="data-row">
                    {/* Spanned MO Cell */}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell" style={{ padding: '10px', border: '1px solid #ddd', verticalAlign: 'middle', textAlign: 'center' }}>
                        <button className="mo-link-btn" onClick={() => handleViewDetail(row.mo)} style={{ color: '#2563eb', fontWeight: 'bold', border: 'none', background: 'none', cursor: 'pointer', fontSize: '15px' }}>
                          {row.mo}
                        </button>
                      </td>
                    )}

                    {/* IM/OM Separation */}
                    <td className="fw-bold" style={{ padding: '10px', border: '1px solid #ddd', fontWeight: '500' }}>{row.base_product}</td>
                    <td className="qty-cell" style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    <td className="fw-bold" style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center', fontWeight: '500' }}>{row.component_type}</td>
                    
                    {/* SHO & TB */}
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.sho_in || '-'}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.sho_out || '-'}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.tb_in || '-'}</td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>{row.tb_out || '-'}</td>
                    
                    {/* Merged Channel Section */}
                    {channelSpan > 0 && (
                      <>
                        <td rowSpan={channelSpan} className="merged-channel-cell fw-bold" style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center', verticalAlign: 'middle', fontWeight: '500' }}>
                          {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}
                        </td>
                        <td rowSpan={channelSpan} className="merged-channel-cell" style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center', verticalAlign: 'middle' }}>{row.ch_in || '-'}</td>
                        <td rowSpan={channelSpan} className="merged-channel-cell" style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center', verticalAlign: 'middle' }}>{row.ch_out || '-'}</td>
                      </>
                    )}
                    
                    {/* Status */}
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`} style={{ padding: '4px 8px', borderRadius: '12px', fontSize: '13px', fontWeight: 'bold' }}>
                        {row.status || 'In Process'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="14" className="empty-state" style={{ padding: '30px', textAlign: 'center' }}>
                    No matching Production Tracking data frames located.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* VIEW BLOCK 2: TARGET DRILLDOWN DETAILED FLOW */}
      {!loading && selectedMoFlow && selectedMoFlow.flow_data && (
        <div className="table-wrapper" style={{ marginTop: '20px', overflowX: 'auto' }}>
          <table className="trace-table detail-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
            <thead style={{ backgroundColor: '#f1f5f9' }}>
              <tr className="sub-header">
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'left' }}>MO Reference</th>
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'left' }}>Department / Specific Location</th>
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'left' }}>Product / Part Sub Variant</th>
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>Qty In</th>
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>Qty Out</th>
                <th style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>Execution Status</th>
              </tr>
            </thead>
            <tbody>
              {selectedMoFlow.flow_data.map((row, index) => {
                const isFirstRow = index === 0;
                return (
                  <tr key={index} className="data-row" style={{ backgroundColor: '#ffffff' }}>
                    {isFirstRow && (
                      <td rowSpan={selectedMoFlow.flow_data.length} className="merged-mo-cell" style={{ padding: '12px', border: '1px solid #ddd', verticalAlign: 'middle', backgroundColor: '#f8fafc' }}>
                        <strong>{selectedMoFlow.mo}</strong>
                      </td>
                    )}
                    <td style={{ padding: '12px', border: '1px solid #ddd', fontWeight: '500' }}>{row.department}</td>
                    <td style={{ padding: '12px', border: '1px solid #ddd' }}>{row.product || '-'}</td>
                    {/* In Date and Out Date columns removed here */}
                    <td style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>{row.qty_in ? Number(row.qty_in).toLocaleString() : 0}</td>
                    <td style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>{row.qty_out ? Number(row.qty_out).toLocaleString() : 0}</td>
                    <td style={{ padding: '12px', border: '1px solid #ddd', textAlign: 'center' }}>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`} style={{ padding: '4px 8px', borderRadius: '12px', fontSize: '13px', fontWeight: 'bold' }}>
                        {row.status || '-'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Traceability;

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
        // Retry connection in 4 seconds automatically
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
        setSelectedMoFlow(json.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(item => 
    item.mo.toLowerCase().includes(search.toLowerCase()) ||
    item.base_product.toLowerCase().includes(search.toLowerCase()) ||
    (item.final_variant && item.final_variant.toLowerCase().includes(search.toLowerCase()))
  );

  /**
   * Lookahead utility to calculate the vertical rowSpan values.
   * Merges matching 7-letter manufacturing order meta properties safely.
   */
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    // If the previous row belongs to the same MO, this cell gets hidden (span 0)
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo === currentMo) {
      return 0;
    }
    // Loop ahead to calculate how many consecutive matching rows exist
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo === currentMo) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag">
            {selectedMoFlow ? `Detailed Route Flow / Order: ${selectedMoFlow.mo}` : "Production Order Global KPI Summary Dashboard"}
          </p>
        </div>
        
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)}>
              ← Back to Summary Dashboard
            </button>
          ) : (
            <input
              className="search-box"
              placeholder="Filter Dashboard Summary..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={isInitializing}
            />
          )}
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      
      {/* Dynamic system warmup handling */}
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>System Backend is warming up...</strong></p>
          <p className="sub-text">Downloading and parsing master excel configurations. Auto-refreshing in a few moments...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying Database Pipeline Cache...</div>}

      {/* VIEW BLOCK 1: MAIN SUMMARY DASHBOARD */}
      {!loading && !isInitializing && !selectedMoFlow && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr className="super-header">
                {/* Expanded to 4 columns to cover: MO, Product details, Qty Req, and Item Type */}
                <th colSpan="4">Order Metadata</th>
                <th colSpan="3" className="sho-head">SHO Department</th>
                <th colSpan="3" className="tb-head">Transit Buffer</th>
                <th colSpan="3" className="ch-head">Channel Section</th>
                <th>System Status</th>
              </tr>
              <tr>
                <th>MO Number</th>
                <th>Product Detail</th>
                <th>Target Qty</th>
                <th>Type</th>
                <th className="sho-head">Qty</th>
                <th className="sho-head">In Date</th>
                <th className="sho-head">Out Date</th>
                <th className="tb-head">Qty</th>
                <th className="tb-head">In Date</th>
                <th className="tb-head">Out Date</th>
                <th className="ch-head">Qty</th>
                <th className="ch-head">In Date</th>
                <th className="ch-head">Out Date</th>
                <th>Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSummary.map((row, idx) => {
                const spanValue = getMoRowSpan(filteredSummary, idx);
                
                return (
                  <tr key={idx}>
                    {/* MERGED CELL: MO LINK */}
                    {spanValue > 0 && (
                      <td rowSpan={spanValue} className="merged-mo-cell">
                        <button className="mo-link-btn" onClick={() => handleViewDetail(row.mo)}>
                          {row.mo}
                        </button>
                      </td>
                    )}

                    {/* MERGED CELL: BASE PRODUCT + SUB VARIANT */}
                    {spanValue > 0 && (
                      <td rowSpan={spanValue} className="merged-product-cell">
                        <div style={{ fontWeight: '600' }}>{row.base_product}</div>
                        {row.final_variant && (
                          <span className="variant-subtext" style={{ fontSize: '11px', color: '#666', display: 'block', marginTop: '2px' }}>
                            {row.final_variant}
                          </span>
                        )}
                      </td>
                    )}

                    {/* MERGED CELL: TARGET REQUIREMENT QUANTITY */}
                    {spanValue > 0 && (
                      <td rowSpan={spanValue} className="merged-qty-cell" style={{ fontWeight: '600', color: '#2c3e50' }}>
                        {row.qty_req > 0 ? row.qty_req.toLocaleString() : '-'}
                      </td>
                    )}

                    {/* ALWAYS DISTINCT: COMPONENT TYPE SPLIT (IM/OM) */}
                    <td><strong>{row.component_type}</strong></td>
                    
                    {/* DEPARTMENTAL BREAKDOWNS */}
                    <td>{row.sho_qty.toLocaleString()}</td>
                    <td>{row.sho_in}</td>
                    <td>{row.sho_out}</td>
                    <td>{row.tb_qty.toLocaleString()}</td>
                    <td>{row.tb_in}</td>
                    <td>{row.tb_out}</td>
                    <td>{row.ch_qty.toLocaleString()}</td>
                    <td>{row.ch_in}</td>
                    <td>{row.ch_out}</td>
                    <td>
                      <span className={`status-badge ${row.status.toLowerCase().replace(/\s+/g, '-')}`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {filteredSummary.length === 0 && (
                <tr>
                  <td colSpan="14" style={{ textAlign: 'center', padding: '30px' }}>
                    No matching Production Tracking data frames located.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* VIEW BLOCK 2: TARGET DRILLDOWN DETAILED FLOW */}
      {!loading && selectedMoFlow && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>MO Reference</th>
                <th>Department / Specific Location</th>
                <th>Product / Part Sub Variant</th>
                <th>In Date</th>
                <th>Out Date</th>
                <th>Qty In</th>
                <th>Qty Out</th>
                <th>Execution Status</th>
              </tr>
            </thead>
            <tbody>
              {selectedMoFlow.flow_data.map((row, index) => {
                const isFirstRow = index === 0;
                return (
                  <tr key={index}>
                    {isFirstRow && (
                      <td rowSpan={selectedMoFlow.flow_data.length} className="mo-cell">
                        <strong>{selectedMoFlow.mo}</strong>
                      </td>
                    )}
                    <td>{row.department}</td>
                    <td>{row.product || '-'}</td>
                    <td>{row.in_date || '-'}</td>
                    <td>{row.out_date || '-'}</td>
                    <td>{row.qty_in?.toLocaleString()}</td>
                    <td>{row.qty_out?.toLocaleString()}</td>
                    <td>
                      <span className={`status-badge ${row.status?.toLowerCase().replace(' ', '-')}`}>
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

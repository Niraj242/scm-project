import React, { useState, useEffect, useCallback } from 'react';
/* Explicitly including your provided CSS file layout */
import './Afterchannel.css';

const API_BASE_URL = "/api/afterchannel";

export default function AfterChannelModule() {
  // Navigation tabs state control
  const [activeTab, setActiveTab] = useState('accurate'); // accurate, cps, rework, vibration, summary
  
  // Data tracking arrays
  const [entries, setEntries] = useState([]);
  const [summaryData, setSummaryData] = useState([]);
  
  // Comprehensive, uncut form state parameters
  const [formData, setFormData] = useState({
    mo_number: '',
    bearing_variant: '',
    quantity: '',
    next_channel: 'Next Process',
    remarks: ''
  });
  
  // Tracking live data metrics verified from the master spreadsheets
  const [liveMasterMeta, setLiveMasterMeta] = useState({ qty: '-', variant: '-' });
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch log rows for a selected department
  const fetchDepartmentEntries = useCallback(async (dept) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/entries/${dept}`);
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
      } else {
        console.error("Failed to load department historical entries.");
      }
    } catch (err) {
      console.error("Network communication failure loading rows:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch the master compiled tracking view summaries
  const fetchSummaryData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/summary`);
      if (res.ok) {
        const data = await res.json();
        setSummaryData(data);
      } else {
        console.error("Failed to load aggregated master summaries.");
      }
    } catch (err) {
      console.error("Network communication failure loading summary:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Reset standard input elements to original values
  const resetFormState = useCallback(() => {
    setFormData({
      mo_number: '',
      bearing_variant: '',
      quantity: '',
      next_channel: 'Next Process',
      remarks: ''
    });
    setLiveMasterMeta({ qty: '-', variant: '-' });
    setEditingId(null);
  }, []);

  // Triggers immediate dataset synchronization when active workspace focus shifts
  useEffect(() => {
    if (activeTab === 'summary') {
      fetchSummaryData();
    } else {
      fetchDepartmentEntries(activeTab);
    }
    resetFormState();
  }, [activeTab, fetchDepartmentEntries, fetchSummaryData, resetFormState]);

  // Resolves quantity anomalies by validating against master data sheets
  const handleMoLookupOnBlur = async (moValue) => {
    const cleanMo = (moValue || '').trim();
    if (!cleanMo) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/lookup-mo?mo_number=${encodeURIComponent(cleanMo)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.found) {
          setLiveMasterMeta({
            qty: data.qty !== null && data.qty !== undefined ? data.qty : '0',
            variant: data.bearing_variant || 'Unknown Variant'
          });
          setFormData(prev => ({
            ...prev,
            bearing_variant: data.bearing_variant || ''
          }));
        } else {
          setLiveMasterMeta({ qty: '0', variant: 'Not Found' });
          setFormData(prev => ({ ...prev, bearing_variant: 'Not Found' }));
        }
      }
    } catch (err) {
      console.error("Master configuration catalog lookup execution issue:", err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    if (!formData.mo_number.trim()) {
      alert("Please supply a valid Manufacturing Order target code reference identifier.");
      return;
    }

    const payload = {
      mo_number: formData.mo_number.trim(),
      bearing_variant: formData.bearing_variant.trim() || liveMasterMeta.variant,
      quantity: parseFloat(formData.quantity) || 0,
      next_channel: formData.next_channel,
      remarks: formData.remarks.trim()
    };

    try {
      let url = `${API_BASE_URL}/entries/${activeTab}`;
      let method = 'POST';

      if (editingId) {
        url = `${API_BASE_URL}/entries/${activeTab}/${editingId}`;
        method = 'PUT';
      }

      const res = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        resetFormState();
        fetchDepartmentEntries(activeTab);
      } else {
        const errPayload = await res.json();
        alert(`Transaction rejected by backend engine: ${errPayload.detail || 'Malformed inputs parameters'}`);
      }
    } catch (err) {
      console.error("Failed to commit transactional database record submission:", err);
    }
  };

  const startRowModificationMode = (row) => {
    setEditingId(row.id);
    setFormData({
      mo_number: row.mo_number,
      bearing_variant: row.bearing_variant || '',
      quantity: row.quantity,
      next_channel: row.next_channel || 'Next Process',
      remarks: row.remarks || ''
    });
    setLiveMasterMeta({
      qty: 'Modifying Stored Record Metric',
      variant: row.bearing_variant || 'Stored Model'
    });
  };

  const executeRowDeletion = async (id) => {
    if (!window.confirm("Are you absolutely sure you want to permanently delete this logged record event from database registries?")) return;
    try {
      const res = await fetch(`${API_BASE_URL}/entries/${activeTab}/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchDepartmentEntries(activeTab);
        if (editingId === id) resetFormState();
      } else {
        alert("Unable to process deletion request at this time.");
      }
    } catch (err) {
      console.error("Error executing row delete sequence transaction:", err);
    }
  };

  const getFormHeaderContextTitle = () => {
    switch (activeTab) {
      case 'accurate': return 'Accurate / SHO Operational Entry Control Panel';
      case 'cps': return 'CPS / Transit Buffer Operational Configuration Ledger';
      case 'rework': return 'Rework Loop Quality Assurance Logging Workspace';
      case 'vibration': return 'Vibration Analysis Bench Test Metric Intake';
      default: return 'Operation Tracking Entry Form';
    }
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>Traceability System & After Channel Analytics</h2>
      </div>

      {/* Navigation tabs layout matching class structures */}
      <div className="sub-view-tabs">
        <button className={`tab-btn ${activeTab === 'accurate' ? 'active-tab' : ''}`} onClick={() => setActiveTab('accurate')}>Accurate / SHO</button>
        <button className={`tab-btn ${activeTab === 'cps' ? 'active-tab' : ''}`} onClick={() => setActiveTab('cps')}>CPS / Transit Buffer</button>
        <button className={`tab-btn ${activeTab === 'rework' ? 'active-tab' : ''}`} onClick={() => setActiveTab('rework')}>Rework Records</button>
        <button className={`tab-btn ${activeTab === 'vibration' ? 'active-tab' : ''}`} onClick={() => setActiveTab('vibration')}>Vibration Diagnostic</button>
        <button className={`tab-btn ${activeTab === 'summary' ? 'active-tab' : ''}`} onClick={() => setActiveTab('summary')}>Master Consolidated Summary Ledger</button>
      </div>

      {activeTab !== 'summary' ? (
        <>
          {/* Active alert visual warning context banner */}
          {editingId && (
            <div className="edit-banner-alert">
              Active Record Modification Mode. Changing attributes for Log ID Reference Record #{editingId}.
            </div>
          )}

          {/* Master Excel Reference Tracking State Visualization Card */}
          <div className="excel-master-tracker-card">
            <div className="metadata-summary-flex">
              <p>Master Sheet Matched Variant: <span className="highlight-production-text">{liveMasterMeta.variant}</span></p>
              <p>Original Master Document Quantity: <span className="highlight-production-text">{liveMasterMeta.qty}</span></p>
            </div>
          </div>

          {/* Split View Layout Configuration */}
          <div className="forms-grid-split">
            {/* Left Card: Input Elements Workspace */}
            <div className={`operation-card ${activeTab === 'accurate' || activeTab === 'rework' ? 'container-inbound' : 'container-outbound'}`}>
              <h3>{getFormHeaderContextTitle()}</h3>
              <form onSubmit={handleFormSubmit}>
                
                <div className="control-group">
                  <label>Manufacturing Order (MO Number)</label>
                  <input 
                    type="text" 
                    name="mo_number" 
                    value={formData.mo_number} 
                    onChange={handleInputChange}
                    onBlur={(e) => handleMoLookupOnBlur(e.target.value)}
                    placeholder="Provide valid Manufacturing Order code..." 
                    required 
                  />
                </div>

                <div className="control-group">
                  <label>Bearing Variant Variant Model Description</label>
                  <input 
                    type="text" 
                    name="bearing_variant" 
                    value={formData.bearing_variant} 
                    onChange={handleInputChange}
                    placeholder="Auto-matched from master if left blank..." 
                  />
                </div>

                <div className="control-group">
                  <label>Batch Quantity (Processed Count Metric)</label>
                  <input 
                    type="number" 
                    name="quantity" 
                    value={formData.quantity} 
                    onChange={handleInputChange} 
                    placeholder="Specify numerical volume total..." 
                    min="0"
                    step="any"
                    required 
                  />
                </div>

                <div className="control-group">
                  <label>Destination Route Channel Designation</label>
                  <select name="next_channel" value={formData.next_channel} onChange={handleInputChange}>
                    <option value="Next Process">Next Standard Process Step</option>
                    <option value="Scrap">Scrap</option>
                    <option value="Rework Loop">Rework Loop</option>
                    <option value="Hold for Inspection">Hold for Inspection</option>
                  </select>
                </div>

                <div className="control-group">
                  <label>Engineering Log Notes / Remarks</label>
                  <input 
                    type="text" 
                    name="remarks" 
                    value={formData.remarks} 
                    onChange={handleInputChange} 
                    placeholder="Enter additional contextual details..." 
                  />
                </div>

                <button type="submit" className={`submit-btn ${activeTab === 'accurate' || activeTab === 'rework' ? 'btn-in' : 'btn-out'}`}>
                  {editingId ? "Commit and Overwrite Entry Records" : "Save Production Run Batch Dataset"}
                </button>
                
                {editingId && (
                  <button type="button" className="submit-btn Trace-btn-override" onClick={resetFormState} style={{ marginTop: '8px' }}>
                    Abandon Modification Changes
                  </button>
                )}
              </form>
            </div>

            {/* Right Card: Persistent Workspace Ledger Table with complete scroll bindings */}
            <div className="table-wrapper structural-history-space">
              <h3>Live Continuous Section Data Log Logs</h3>
              <div className="scrollable-summary-viewport">
                <table>
                  <thead>
                    <tr>
                      <th>MO ID</th>
                      <th>Variant Code</th>
                      <th>Qty Vol</th>
                      <th>Next Channel Target</th>
                      <th>Action Controls</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan="5" className="empty-notice">Synchronizing operational database storage streams...</td></tr>
                    ) : entries.length === 0 ? (
                      <tr><td colSpan="5" className="empty-notice">No records located for this segment view inside storage registries.</td></tr>
                    ) : (
                      entries.map((item) => (
                        <tr key={item.id}>
                          <td><strong>{item.mo_number}</strong></td>
                          <td>{item.bearing_variant || '-'}</td>
                          <td className={item.next_channel === 'Scrap' ? 'text-out-color' : 'text-in-color'}>
                            {item.quantity}
                          </td>
                          <td>
                            <span className={`badge-indicator ${item.next_channel === 'Scrap' ? 'outbound-marker' : 'inbound-marker'}`}>
                              {item.next_channel}
                            </span>
                          </td>
                          <td>
                            <button className="row-action-btn edit-tint" title="Edit Entry Parameters" onClick={() => startRowModificationMode(item)}>✏️</button>
                            <button className="row-action-btn delete-tint" title="Remove Entry Permanently" onClick={() => executeRowDeletion(item.id)}>🗑️</button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      ) : (
        /* Consolidated Multi-Department Aggregation Summary Table View Layout Space */
        <div className="table-wrapper structural-history-space">
          <div className="header-badge-row">
            <h3>Fully Synchronized Master Tracking Matrix View</h3>
            <span className="line-segment-dropdown">Traceability Engine Live Connection</span>
          </div>
          <div className="scrollable-summary-viewport" style={{ maxHeight: '550px' }}>
            <table>
              <thead>
                <tr>
                  <th>MO Target reference</th>
                  <th>Bearing Model Variant</th>
                  <th>Original Spreadsheet Qty</th>
                  <th>SHO Total Vol</th>
                  <th>Transit Buffer Vol</th>
                  <th>Rework Loop Vol</th>
                  <th>Vibration Vol</th>
                  <th style={{ backgroundColor: '#fee2e2', color: '#b91c1c', fontWeight: '800' }}>Scrap Sum (All 4 Departments)</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="8" className="empty-notice">Compiling unified structural ledger metrics across databases...</td></tr>
                ) : summaryData.length === 0 ? (
                  <tr><td colSpan="8" className="empty-notice">No tracking records are stored inside active system configurations to compile.</td></tr>
                ) : (
                  summaryData.map((row, index) => (
                    <tr key={index}>
                      <td><strong>{row.mo_number}</strong></td>
                      <td>{row.bearing_variant}</td>
                      <td>{row.original_qty}</td>
                      <td>{row.accurate_qty}</td>
                      <td>{row.cps_qty}</td>
                      <td>{row.rework_qty}</td>
                      <td>{row.vibration_qty}</td>
                      <td style={{ backgroundColor: '#fef2f2', fontWeight: 'bold', color: '#dc2626' }}>
                        {row.scrap_sum}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

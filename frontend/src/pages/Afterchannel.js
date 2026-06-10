import React, { useState, useEffect, useCallback } from 'react';
import './Afterchannel.css';

const API_BASE_URL = "/api/afterchannel";

export default function AfterChannelModule() {
  const [activeTab, setActiveTab] = useState('accurate'); 
  const [entries, setEntries] = useState([]);
  const [summaryData, setSummaryData] = useState([]);
  
  const [formData, setFormData] = useState({
    mo_number: '',
    bearing_variant: '',
    quantity: '',
    next_channel: 'Next Process',
    remarks: ''
  });
  
  const [masterMeta, setMasterMeta] = useState({ qty: '-', variant: '-' });
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);

  // Load existing records for the active channel tab
  const fetchEntries = useCallback(async (channel) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/entries/${channel}`);
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
      }
    } catch (err) {
      console.error("Error fetching channel logs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load the final master summary view data
  const fetchSummary = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/summary`);
      if (res.ok) {
        const data = await res.json();
        setSummaryData(data);
      }
    } catch (err) {
      console.error("Error fetching master summary matrix:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const resetForm = useCallback(() => {
    setFormData({
      mo_number: '',
      bearing_variant: '',
      quantity: '',
      next_channel: 'Next Process',
      remarks: ''
    });
    setMasterMeta({ qty: '-', variant: '-' });
    setEditingId(null);
  }, []);

  useEffect(() => {
    if (activeTab === 'summary') {
      fetchSummary();
    } else {
      fetchEntries(activeTab);
    }
    resetForm();
  }, [activeTab, fetchEntries, fetchSummary, resetForm]);

  // Live lookup check when user leaves the MO input field
  const handleMoBlur = async (moValue) => {
    const cleanMo = (moValue || '').trim();
    if (!cleanMo) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/lookup-mo?mo_number=${encodeURIComponent(cleanMo)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.found) {
          setMasterMeta({
            qty: data.qty !== null ? data.qty : '0',
            variant: data.bearing_variant || 'Unknown'
          });
          setFormData(prev => ({
            ...prev,
            bearing_variant: data.bearing_variant || ''
          }));
        } else {
          setMasterMeta({ qty: '0', variant: 'Not Found' });
          setFormData(prev => ({ ...prev, bearing_variant: 'Not Found' }));
        }
      }
    } catch (err) {
      console.error("Error running MO master sheet check:", err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.mo_number.trim()) return;

    const payload = {
      mo_number: formData.mo_number.trim(),
      bearing_variant: formData.bearing_variant.trim() || masterMeta.variant,
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
        resetForm();
        fetchEntries(activeTab);
      }
    } catch (err) {
      console.error("Error saving channel submission entry:", err);
    }
  };

  const handleEdit = (row) => {
    setEditingId(row.id);
    setFormData({
      mo_number: row.mo_number,
      bearing_variant: row.bearing_variant || '',
      quantity: row.quantity,
      next_channel: row.next_channel || 'Next Process',
      remarks: row.remarks || ''
    });
    setMasterMeta({
      qty: 'Editing Record...',
      variant: row.bearing_variant || 'Stored'
    });
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this record entry?")) return;
    try {
      const res = await fetch(`${API_BASE_URL}/entries/${activeTab}/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchEntries(activeTab);
        if (editingId === id) resetForm();
      }
    } catch (err) {
      console.error("Error executing row deletion process:", err);
    }
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>After Channel Module</h2>
      </div>

      {/* Navigation Tabs Bar */}
      <div className="sub-view-tabs">
        <button className={`tab-btn ${activeTab === 'accurate' ? 'active-tab' : ''}`} onClick={() => setActiveTab('accurate')}>Accurate</button>
        <button className={`tab-btn ${activeTab === 'cps' ? 'active-tab' : ''}`} onClick={() => setActiveTab('cps')}>CPS</button>
        <button className={`tab-btn ${activeTab === 'rework' ? 'active-tab' : ''}`} onClick={() => setActiveTab('rework')}>Rework</button>
        <button className={`tab-btn ${activeTab === 'vibration' ? 'active-tab' : ''}`} onClick={() => setActiveTab('vibration')}>Vibration</button>
        <button className={`tab-btn ${activeTab === 'summary' ? 'active-tab' : ''}`} onClick={() => setActiveTab('summary')}>Summary</button>
      </div>

      {activeTab !== 'summary' ? (
        <>
          {editingId && (
            <div className="edit-banner-alert">
              Currently updating Log Record Reference ID: #{editingId}
            </div>
          )}

          {/* Master Sheet Sync Banner Cards */}
          <div className="excel-master-tracker-card">
            <div className="metadata-summary-flex">
              <p>Master Sheet Variant: <span className="highlight-production-text">{masterMeta.variant}</span></p>
              <p>Master Original Qty: <span className="highlight-production-text">{masterMeta.qty}</span></p>
            </div>
          </div>

          <div className="forms-grid-split">
            {/* Left Column Input Panel Form */}
            <div className={`operation-card ${activeTab === 'accurate' || activeTab === 'rework' ? 'container-inbound' : 'container-outbound'}`}>
              <h3>{activeTab.toUpperCase()} Entry Panel</h3>
              <form onSubmit={handleSubmit}>
                <div className="control-group">
                  <label>MO Number</label>
                  <input 
                    type="text" 
                    name="mo_number" 
                    value={formData.mo_number} 
                    onChange={handleInputChange}
                    onBlur={(e) => handleMoBlur(e.target.value)}
                    placeholder="Enter MO Number..." 
                    required 
                  />
                </div>

                <div className="control-group">
                  <label>Bearing Variant</label>
                  <input 
                    type="text" 
                    name="bearing_variant" 
                    value={formData.bearing_variant} 
                    onChange={handleInputChange}
                    placeholder="Auto-filled from master sheets..." 
                  />
                </div>

                <div className="control-group">
                  <label>Quantity</label>
                  <input 
                    type="number" 
                    name="quantity" 
                    value={formData.quantity} 
                    onChange={handleInputChange} 
                    placeholder="Enter process volume..." 
                    min="0"
                    step="any"
                    required 
                  />
                </div>

                <div className="control-group">
                  <label>Next Channel</label>
                  <select name="next_channel" value={formData.next_channel} onChange={handleInputChange}>
                    <option value="Next Process">Next Process</option>
                    <option value="Scrap">Scrap</option>
                    <option value="Rework">Rework</option>
                    <option value="Hold">Hold</option>
                  </select>
                </div>

                <div className="control-group">
                  <label>Remarks</label>
                  <input 
                    type="text" 
                    name="remarks" 
                    value={formData.remarks} 
                    onChange={handleInputChange} 
                    placeholder="Enter additional log data notes..." 
                  />
                </div>

                <button type="submit" className={`submit-btn ${activeTab === 'accurate' || activeTab === 'rework' ? 'btn-in' : 'btn-out'}`}>
                  {editingId ? "Update Entry Log" : "Save Channel Entry"}
                </button>
                
                {editingId && (
                  <button type="button" className="submit-btn Trace-btn-override" onClick={resetForm} style={{ marginTop: '8px' }}>
                    Cancel Edit
                  </button>
                )}
              </form>
            </div>

            {/* Right Column Continuous Log Records Table */}
            <div className="table-wrapper structural-history-space">
              <h3>Recent Channel Submissions Log</h3>
              <div className="scrollable-summary-viewport">
                <table>
                  <thead>
                    <tr>
                      <th>MO Number</th>
                      <th>Variant</th>
                      <th>Quantity</th>
                      <th>Next Channel</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan="5" className="empty-notice">Loading production tracking data records...</td></tr>
                    ) : entries.length === 0 ? (
                      <tr><td colSpan="5" className="empty-notice">No stored logging files available for this section view.</td></tr>
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
                            <button className="row-action-btn edit-tint" title="Edit" onClick={() => handleEdit(item)}>✏️</button>
                            <button className="row-action-btn delete-tint" title="Delete" onClick={() => handleDelete(item.id)}>🗑️</button>
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
        /* Summary Grid View Table Matrix layout pane */
        <div className="table-wrapper structural-history-space">
          <div className="header-badge-row">
            <h3>Master Aggregate Channels Summary</h3>
          </div>
          <div className="scrollable-summary-viewport" style={{ maxHeight: '520px' }}>
            <table>
              <thead>
                <tr>
                  <th>MO Number</th>
                  <th>Bearing Variant</th>
                  <th>Original Qty</th>
                  <th>Accurate Qty</th>
                  <th>CPS Qty</th>
                  <th>Rework Qty</th>
                  <th>Vibration Qty</th>
                  <th style={{ backgroundColor: '#fee2e2', color: '#b91c1c' }}>Total Scrap Sum</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="8" className="empty-notice">Calculating matching database row metrics...</td></tr>
                ) : summaryData.length === 0 ? (
                  <tr><td colSpan="8" className="empty-notice">No records found to compile matrix.</td></tr>
                ) : (
                  summaryData.map((row, idx) => (
                    <tr key={idx}>
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

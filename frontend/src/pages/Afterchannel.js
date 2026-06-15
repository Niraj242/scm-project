import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [], autopackaging: [], fps: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMoDetail, setSelectedMoDetail] = useState(null);

  const [moNumber, setMoNumber] = useState('');
  const [availableVariants, setAvailableVariants] = useState([]);
  const [availableMos, setAvailableMos] = useState([]);
  const [selectedVariant, setSelectedVariant] = useState('');
  const [actualProductionQty, setActualProductionQty] = useState(0);
  
  const [editingRecord, setEditingRecord] = useState(null);
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState('');

  // Date state used specifically to filter reverse MO Lookups
  const [formDate, setFormDate] = useState('');

  // Scrap logic states
  const [bearingFamily, setBearingFamily] = useState(''); 
  const [bearingScrapQty, setBearingScrapQty] = useState('');

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
  }, []);

  const fetchMasterData = async () => {
    try {
      const res = await fetch(`${API}/api/mo-list`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setAvailableMos(data);
      }
    } catch (err) {
      console.error("Error fetching MO list:", err);
    }
  };

  const fetchLedgers = async () => {
    try {
      const depts = ['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'];
      const updatedLedgers = {};
      for (const dept of depts) {
        const res = await fetch(`${API}/api/afterchannel/${dept}`);
        const data = await res.json();
        updatedLedgers[dept] = Array.isArray(data) ? data : [];
      }
      setLedgers(updatedLedgers);
    } catch (err) {
      console.error("Error fetching ledgers:", err);
    }
  };

  const lookupMoDetails = async (moStr) => {
    if (!moStr.trim()) return;
    if (moCache[moStr]) {
      setSelectedMoDetail(moCache[moStr]);
      setAvailableVariants(moCache[moStr].variants || []);
      if (moCache[moStr].variants?.length > 0) {
        setSelectedVariant(moCache[moStr].variants[0]);
      }
      return;
    }
    try {
      const res = await fetch(`${API}/api/mo-lookup?mo=${encodeURIComponent(moStr)}`);
      if (res.ok) {
        const data = await res.json();
        setMoCache(prev => ({ ...prev, [moStr]: data }));
        setSelectedMoDetail(data);
        setAvailableVariants(data.variants || []);
        if (data.variants?.length > 0) {
          setSelectedVariant(data.variants[0]);
        }
      } else {
        setSelectedMoDetail(null);
        setAvailableVariants([]);
      }
    } catch (err) {
      console.error("Error looking up MO:", err);
    }
  };

  // Handler for MO text change to trigger reverse lookup when valid date is provided
  const handleMoNumberChange = (val) => {
    setMoNumber(val);
    if (val.trim().length >= 4) {
      lookupMoDetails(val);
    }
  };

  const handleCreateOrUpdateEntry = async (e) => {
    e.preventDefault();
    if (!moNumber.trim()) {
      alert("Please enter a valid MO number");
      return;
    }

    const payload = {
      mo: moNumber,
      type: entryMode,
      inDate: formDate || new Date().toISOString().split('T')[0],
      shiftIn: e.target.shiftIn?.value || 'Shift A',
      pc: selectedMoDetail?.pc || '',
      materialInFrom: e.target.materialInFrom?.value || '',
      qtyIn: entryMode === 'IN' ? parseInt(e.target.qty?.value || 0) : 0,
      nextStation: e.target.nextStation?.value || '',
      qtySent: entryMode === 'OUT' ? parseInt(e.target.qty?.value || 0) : 0,
      outDate: entryMode === 'OUT' ? (formDate || new Date().toISOString().split('T')[0]) : null,
      shiftOut: entryMode === 'OUT' ? (e.target.shiftOut?.value || 'Shift A') : null,
      
      // fields for specific tables if necessary
      item: selectedVariant,
      rcNo: e.target.rcNo?.value || '',
      channel: e.target.channel?.value || '',
      customerOrder: e.target.customerOrder?.value || '',
      
      // scrap reason fields
      bearingFamily: bearingFamily || '',
      bearingScrapQty: bearingScrapQty ? parseInt(bearingScrapQty) : 0,
      irScrap: parseInt(e.target.irScrap?.value || 0),
      orScrap: parseInt(e.target.orScrap?.value || 0),
      cageScrap: parseInt(e.target.cageScrap?.value || 0),
      ballScrap: parseInt(e.target.ballScrap?.value || 0),
      scrapReason: e.target.scrapReason?.value || '',
    };

    let url = `${API}/api/afterchannel/${activeTab}`;
    let method = 'POST';

    if (editingRecord) {
      url = `${API}/api/afterchannel/${activeTab}/${editingRecord.id}`;
      method = 'PUT';
    }

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        alert(editingRecord ? "Entry updated successfully!" : "Entry logged successfully!");
        setEditingRecord(null);
        setMoNumber('');
        setBearingScrapQty('');
        setBearingFamily('');
        setSelectedMoDetail(null);
        fetchLedgers();
      } else {
        const errData = await res.json();
        alert(`Error: ${errData.detail || 'Failed to save entry'}`);
      }
    } catch (err) {
      console.error(err);
      alert("Network or Server error");
    }
  };

  const handleEditInit = (row) => {
    setEditingRecord(row);
    setMoNumber(row.mo);
    setEntryMode(row.type || 'IN');
    setFormDate(row.inDate || row.outDate || '');
    lookupMoDetails(row.mo);
    if (row.bearingFamily) setBearingFamily(row.bearingFamily);
    if (row.bearingScrapQty) setBearingScrapQty(row.bearingScrapQty);
  };

  const handleDeleteEntry = async (dept, id) => {
    if (!window.confirm("Are you sure you want to delete this entry?")) return;
    try {
      const res = await fetch(`${API}/api/afterchannel/${dept}/${id}`, { method: 'DELETE' });
      if (res.ok) {
        alert("Entry deleted");
        fetchLedgers();
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Dynamic calculations for summary tracking table grouped by MO
  const generateSummaryData = () => {
    const summaryMap = {};

    // Initialize summary map with active items from ledgers
    const allLists = [...ledgers.accurate, ...ledgers.cps, ...ledgers.rework, ...ledgers.dismantling, ...ledgers.autopackaging, ...ledgers.fps];
    
    allLists.forEach(item => {
      if (!item.mo) return;
      if (!summaryMap[item.mo]) {
        summaryMap[item.mo] = {
          mo: item.mo,
          pc: item.pc || '-',
          accIn: 0, accOut: 0,
          cpsIn: 0, cpsOut: 0,
          rwIn: 0, rwOut: 0,
          disIn: 0, disOut: 0,
          apIn: 0, apOut: 0,
          fpsIn: 0, fpsOut: 0,
          irScrap: 0, orScrap: 0, cageScrap: 0, ballScrap: 0, totalScrap: 0
        };
      }
    });

    // Accumulate volumes
    ledgers.accurate.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.accIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.accOut += (r.qtySent || 0);
    });

    ledgers.cps.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.cpsIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.cpsOut += (r.qtySent || 0);
    });

    ledgers.rework.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.rwIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.rwOut += (r.qtySent || 0);
    });

    ledgers.dismantling.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.disIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.disOut += (r.qtySent || 0);
      node.irScrap += (r.irScrap || 0);
      node.orScrap += (r.orScrap || 0);
      node.cageScrap += (r.cageScrap || 0);
      node.ballScrap += (r.ballScrap || 0);
    });

    ledgers.autopackaging.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.apIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.apOut += (r.qtySent || 0);
    });

    ledgers.fps.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.fpsIn += (r.qtyIn || 0);
      if (r.type === 'OUT') node.fpsOut += (r.qtySent || 0);
    });

    // Calculate individual total scrap rows
    Object.keys(summaryMap).forEach(key => {
      const s = summaryMap[key];
      s.totalScrap = s.irScrap + s.orScrap + s.cageScrap + s.ballScrap;
    });

    let result = Object.values(summaryMap);
    if (ledgerSearchQuery.trim()) {
      result = result.filter(item => item.mo.toLowerCase().includes(ledgerSearchQuery.toLowerCase()));
    }
    return result;
  };

  const filteredLedgerData = () => {
    if (activeTab === 'summary') return generateSummaryData();
    const list = ledgers[activeTab] || [];
    if (!ledgerSearchQuery.trim()) return list;
    return list.filter(item => item.mo.toLowerCase().includes(ledgerSearchQuery.toLowerCase()));
  };

  return (
    <div className="scrap-module">
      <div className="module-header">
        <h2>🏭 AFTERCHANNEL PRODUCTION & SCRAP TRACKER</h2>
        <p style={{margin:0, color:'#64748b'}}>Centralized logistics control for Accurate, CPS, Rework, Dismantling, Auto-Packaging & FPS</p>
      </div>

      {/* Tab Selectors */}
      <div className="sub-view-tabs">
        {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
          <button 
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => { setActiveTab(tab); setEditingRecord(null); setMoNumber(''); }}
          >
            {tab.toUpperCase()}
          </button>
        ))}
        <button 
          className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
          onClick={() => { setActiveTab('summary'); setEditingRecord(null); }}
          style={{background: '#dcfce7', color: '#166534', border: '1px solid #bbf7d0'}}
        >
          📊 SUMMARY VIEW
        </button>
      </div>

      {activeTab !== 'summary' && (
        <div style={{background: '#fff', padding:'20px', borderRadius:'8px', boxShadow:'0 1px 3px rgba(0,0,0,0.05)', marginBottom:'24px'}}>
          <h3 style={{marginTop:0}}>{editingRecord ? `✏️ Edit ${activeTab.toUpperCase()} Record` : `➕ Log New ${activeTab.toUpperCase()} Entry`}</h3>
          
          <form onSubmit={handleCreateOrUpdateEntry}>
            <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px'}}>
              
              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>MO Number</label>
                <input 
                  type="text" 
                  value={moNumber} 
                  onChange={(e) => handleMoNumberChange(e.target.value)} 
                  placeholder="Enter MO..." 
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                  required 
                />
              </div>

              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Transaction Type</label>
                <select 
                  value={entryMode} 
                  onChange={(e) => setEntryMode(e.target.value)}
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                >
                  <option value="IN">IN (Receive to Station)</option>
                  <option value="OUT">OUT (Send to Next Station)</option>
                </select>
              </div>

              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Date</label>
                <input 
                  type="date" 
                  value={formDate} 
                  onChange={(e) => setFormDate(e.target.value)}
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                />
              </div>

              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Shift</label>
                <select 
                  name={entryMode === 'IN' ? "shiftIn" : "shiftOut"}
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                >
                  <option value="Shift A">Shift A</option>
                  <option value="Shift B">Shift B</option>
                  <option value="Shift C">Shift C</option>
                </select>
              </div>

              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Quantity (Pcs)</label>
                <input 
                  type="number" 
                  name="qty" 
                  defaultValue={editingRecord ? (editingRecord.qtyIn || editingRecord.qtySent) : ''}
                  placeholder="Enter volume..."
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                  required
                />
              </div>

              <div>
                <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Material Source From</label>
                <input 
                  type="text" 
                  name="materialInFrom"
                  defaultValue={editingRecord?.materialInFrom || ''} 
                  placeholder="e.g. Grind line, Rework..." 
                  style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                />
              </div>

              {activeTab === 'accurate' && (
                <div>
                  <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Next Station</label>
                  <input 
                    type="text" 
                    name="nextStation" 
                    defaultValue={editingRecord?.nextStation || ''}
                    placeholder="e.g. CPS, Assembly" 
                    style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                  />
                </div>
              )}

              {activeTab === 'cps' && (
                <>
                  <div>
                    <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Select Item Variant</label>
                    <select 
                      value={selectedVariant}
                      onChange={(e) => setSelectedVariant(e.target.value)}
                      style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                    >
                      {availableVariants.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>RC Number</label>
                    <input 
                      type="text" 
                      name="rcNo" 
                      defaultValue={editingRecord?.rcNo || ''}
                      style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                    />
                  </div>
                  <div>
                    <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Channel</label>
                    <input 
                      type="text" 
                      name="channel" 
                      defaultValue={editingRecord?.channel || ''}
                      style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                    />
                  </div>
                </>
              )}

              {activeTab === 'fps' && (
                <div>
                  <label style={{display:'block', fontWeight:6, marginBottom:'4px'}}>Customer Order Reference</label>
                  <input 
                    type="text" 
                    name="customerOrder" 
                    defaultValue={editingRecord?.customerOrder || ''}
                    style={{width:'100%', padding:'8px', borderRadius:'4px', border:'1px solid #cbd5e1'}}
                  />
                </div>
              )}
            </div>

            {/* Special Scrap Tracking Section within Dismantling */}
            {activeTab === 'dismantling' && (
              <div style={{marginTop:'16px', padding:'12px', background:'#fef2f2', border:'1px solid #fee2e2', borderRadius:'6px'}}>
                <h4 style={{margin:'0 0 10px 0', color:'#991b1b'}}>🛠️ Defect Component Scrap Entry</h4>
                <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
                  <div>
                    <label style={{fontSize:'12px', fontWeight:6}}>Inner Ring (IR) Scrap</label>
                    <input type="number" name="irScrap" defaultValue={editingRecord?.irScrap || 0} style={{width:'100%', padding:'6px'}}/>
                  </div>
                  <div>
                    <label style={{fontSize:'12px', fontWeight:6}}>Outer Ring (OR) Scrap</label>
                    <input type="number" name="orScrap" defaultValue={editingRecord?.orScrap || 0} style={{width:'100%', padding:'6px'}}/>
                  </div>
                  <div>
                    <label style={{fontSize:'12px', fontWeight:6}}>Cage Scrap Qty</label>
                    <input type="number" name="cageScrap" defaultValue={editingRecord?.cageScrap || 0} style={{width:'100%', padding:'6px'}}/>
                  </div>
                  <div>
                    <label style={{fontSize:'12px', fontWeight:6}}>Ball Scrap Qty</label>
                    <input type="number" name="ballScrap" defaultValue={editingRecord?.ballScrap || 0} style={{width:'100%', padding:'6px'}}/>
                  </div>
                  <div style={{gridColumn: '1 / -1'}}>
                    <label style={{fontSize:'12px', fontWeight:6}}>Scrap Disposition Reason / Remarks</label>
                    <input type="text" name="scrapReason" defaultValue={editingRecord?.scrapReason || ''} placeholder="e.g. Scratched race, Cage deformation..." style={{width:'100%', padding:'6px'}}/>
                  </div>
                </div>
              </div>
            )}

            {selectedMoDetail && (
              <div style={{background: '#f0fdf4', border:'1px solid #bbf7d0', padding:'12px', borderRadius:'6px', marginTop:'16px', display:'flex', gap:'20px', flexWrap:'wrap'}}>
                <p style={{margin:0, fontSize:'14px'}}><strong>Product Characteristic:</strong> <span style={{color:'#15803d', fontWeight:7}}>{selectedMoDetail.pc || '-'}</span></p>
                <p style={{margin:0, fontSize:'14px'}}><strong>Target Order Volume:</strong> {selectedMoDetail.target_qty || '-'}</p>
                <p style={{margin:0, fontSize:'14px'}}><strong>Master Variant Base:</strong> {selectedMoDetail.product_desc || '-'}</p>
              </div>
            )}

            <div style={{marginTop:'16px', display:'flex', gap:'8px'}}>
              <button type="submit" style={{background:'#2563eb', color:'#fff', padding:'10px 20px', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>
                {editingRecord ? "💾 Update Ledger Entry" : "🚀 Submit Entry Record"}
              </button>
              {editingRecord && (
                <button type="button" onClick={() => setEditingRecord(null)} style={{background:'#64748b', color:'#fff', padding:'10px 20px', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>
                  Cancel Edit
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      {/* Ledger Records and Summary Presentation Block */}
      <div style={{background: '#fff', padding:'20px', borderRadius:'8px', boxShadow:'0 1px 3px rgba(0,0,0,0.05)'}}>
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'16px', flexWrap:'wrap', gap:'12px'}}>
          <h3 style={{margin:0}}>📋 {activeTab === 'summary' ? "Cross-Department Production Reconciliation Summary" : `${activeTab.toUpperCase()} Operational Logs`}</h3>
          <input 
            type="text" 
            placeholder="🔍 Search and filter by MO Number..." 
            value={ledgerSearchQuery}
            onChange={(e) => setLedgerSearchQuery(e.target.value)}
            style={{padding:'6px 12px', borderRadius:'4px', border:'1px solid #cbd5e1', width:'280px'}}
          />
        </div>

        <div style={{overflowX:'auto'}}>
          {activeTab === 'summary' ? (
            <table style={{width:'100%', borderCollapse:'collapse', fontSize:'13px', textAlign:'left'}}>
              <thead>
                <tr style={{background:'#f1f5f9', borderBottom:'2px solid #cbd5e1'}}>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1'}}>MO Number</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1'}}>PC Code</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#eff6ff', color: '#1e40af'}}>Accurate IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#eff6ff', color: '#1e40af'}}>Accurate OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fae8ff', color: '#86198f'}}>CPS IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fae8ff', color: '#86198f'}}>CPS OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fef3c7', color: '#b45309'}}>Rework IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fef3c7', color: '#b45309'}}>Rework OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f3f4f6', color: '#374151'}}>Dismantling IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f3f4f6', color: '#374151'}}>Dismantling OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f0fdf4', color: '#166534'}}>Auto-Packaging IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f0fdf4', color: '#166534'}}>Auto-Packaging OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#ecfeff', color: '#083344'}}>FPS IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#ecfeff', color: '#083344'}}>FPS OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>IR Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>OR Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>Cage Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>Ball Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fee2e2', color: '#991b1b', fontWeight:'bold'}}>Total Component Scrap</th>
                </tr>
              </thead>
              <tbody>
                {filteredLedgerData().map((row, index) => (
                  <tr key={index} style={{borderBottom:'1px solid #e2e8f0', background: index % 2 === 0 ? '#fff' : '#f8fafc'}}>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', fontWeight:'bold'}}>{row.mo}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px'}}>{row.pc}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af'}}>{row.accIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af'}}>{row.accOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f'}}>{row.cpsIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f'}}>{row.cpsOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309'}}>{row.rwIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309'}}>{row.rwOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151'}}>{row.disIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151'}}>{row.disOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#166534'}}>{row.apIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#166534'}}>{row.apOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#083344'}}>{row.fpsIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#083344'}}>{row.fpsOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.irScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.orScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.cageScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.ballScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', background: '#fef2f2', color: '#b91c1c', fontWeight:'bold'}}>{row.totalScrap}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table style={{width:'100%', borderCollapse:'collapse', fontSize:'13px', textAlign:'left'}}>
              <thead>
                <tr style={{background:'#f1f5f9', borderBottom:'2px solid #cbd5e1'}}>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>MO</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Type</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Date</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Shift</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Qty In</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Qty Sent</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>From</th>
                  {activeTab === 'accurate' && <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Next Stn</th>}
                  {activeTab === 'cps' && (
                    <>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Variant</th>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>RC No</th>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Channel</th>
                    </>
                  )}
                  {activeTab === 'fps' && <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Customer Order</th>}
                  {activeTab === 'dismantling' && (
                    <>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1', color:'#991b1b'}}>IR/OR</th>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1', color:'#991b1b'}}>Cage/Ball</th>
                      <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Reason</th>
                    </>
                  )}
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredLedgerData().map((row) => (
                  <tr key={row.id} style={{borderBottom:'1px solid #e2e8f0'}}>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', fontWeight:'bold'}}>{row.mo}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>
                      <span style={{padding:'2px 6px', borderRadius:'4px', fontSize:'11px', fontWeight:'bold', background: row.type==='IN'?'#dbeafe':'#fef9c3', color: row.type==='IN'?'#1e40af':'#854d0e'}}>
                        {row.type}
                      </span>
                    </td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.inDate || row.outDate || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.shiftIn || row.shiftOut || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#16a34a', fontWeight:'bold'}}>{row.qtyIn || 0}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#2563eb', fontWeight:'bold'}}>{row.qtySent || 0}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.materialInFrom || '-'}</td>
                    {activeTab === 'accurate' && <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.nextStation || '-'}</td>}
                    {activeTab === 'cps' && (
                      <>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.item || '-'}</td>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.rcNo || '-'}</td>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.channel || '-'}</td>
                      </>
                    )}
                    {activeTab === 'fps' && <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.customerOrder || '-'}</td>}
                    {activeTab === 'dismantling' && (
                      <>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#991b1b'}}>IR:{row.irScrap||0} / OR:{row.orScrap||0}</td>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#991b1b'}}>C:{row.cageScrap||0} / B:{row.ballScrap||0}</td>
                        <td style={{padding:'10px', border:'1px solid #cbd5e1', fontStyle:'italic'}}>{row.scrapReason || '-'}</td>
                      </>
                    )}
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>
                      <button onClick={() => handleEditInit(row)} style={{marginRight:'6px', padding:'2px 6px', background:'#e2e8f0', border:'none', borderRadius:'3px', cursor:'pointer'}}>Edit</button>
                      <button onClick={() => handleDeleteEntry(activeTab, row.id)} style={{padding:'2px 6px', background:'#fee2e2', color:'#b91c1c', border:'none', borderRadius:'3px', cursor:'pointer'}}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default Afterchannel;

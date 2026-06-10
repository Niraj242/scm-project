import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMoDetail, setSelectedMoDetail] = useState(null);

  const [moNumber, setMoNumber] = useState('');
  const [availableVariants, setAvailableVariants] = useState([]);
  const [selectedVariant, setSelectedVariant] = useState('');
  const [actualProductionQty, setActualProductionQty] = useState(0);
  
  // PATCH: Added State to hold the record currently being edited
  const [editingRecord, setEditingRecord] = useState(null);

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
  }, []);

  const fetchMasterData = async () => {
    try {
      const res = await fetch(`${API}/api/mo-lookup`);
      const data = await res.json();
      if (data.status === 'success') {
        console.log("MASTER DATA LOADED:", data.data); // Open your F12 console to see the exact keys
        setMoCache(data.data || {});
      }
    } catch (err) {
      console.error("Master Reference Load Failure:", err);
    }
  };

  const fetchLedgers = async () => {
    try {
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`);
      const json = await res.json();
      console.log("LEDGERS LOADED:", json); // Open your F12 console to check the saved data
      if (json.status === 'success' || json.data) {
        setLedgers({
          accurate: json.data?.accurate || json.data?.Accurate || [],
          cps: json.data?.cps || json.data?.CPS || [],
          rework: json.data?.rework || json.data?.Rework || [],
          dismantling: json.data?.dismantling || json.data?.Dismantling || json.data?.vibration || []
        });
      }
    } catch (err) {
      console.error("Ledger Sync Failure:", err);
    }
  };

  // --- BLIND-PROOF DATA EXTRACTORS ---
  // Scans every key in the object. If the key contains "prod", "qty", "target", it grabs the number.
  const getQtyFromRow = (row) => {
    for (const key in row) {
      const cleanKey = key.toLowerCase().replace(/[^a-z]/g, '');
      if (['qty', 'quantity', 'production', 'target', 'plan', 'total'].some(w => cleanKey.includes(w))) {
        const val = parseFloat(String(row[key]).replace(/,/g, ''));
        if (!isNaN(val) && val > 0) return val;
      }
    }
    return 0; // Fallback if absolutely nothing is found
  };

  // Scans every key for "type", "variant", "model", "bearing"
  const getTypeFromRow = (row) => {
    for (const key in row) {
      const cleanKey = key.toLowerCase().replace(/[^a-z]/g, '');
      if (['type', 'variant', 'model', 'bearing', 'item'].some(w => cleanKey.includes(w))) {
        return String(row[key]).trim();
      }
    }
    return 'UNKNOWN_VARIANT'; 
  };

  const calculateProduction = (rawRows, variantToMatch) => {
    if (!rawRows || !Array.isArray(rawRows)) return 0;
    const cleanMatch = String(variantToMatch || '').trim().toUpperCase();
    
    return rawRows.reduce((sum, r) => {
      const rowType = getTypeFromRow(r).toUpperCase();
      if (rowType === cleanMatch) {
        return sum + getQtyFromRow(r);
      }
      return sum;
    }, 0);
  };

  const handleMoBlur = () => {
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      const rawRows = moCache[key];
      const uniqueVariants = [...new Set(rawRows.map(r => getTypeFromRow(r)))].filter(Boolean);
      setAvailableVariants(uniqueVariants.map(type => ({ type })));

      if (uniqueVariants.length === 1) {
        const vType = uniqueVariants[0];
        setSelectedVariant(vType);
        setActualProductionQty(calculateProduction(rawRows, vType));
      } else {
        setSelectedVariant('');
        setActualProductionQty(0);
      }
    } else {
      setAvailableVariants([]);
      setSelectedVariant('');
      setActualProductionQty(0);
    }
  };

  const handleVariantChange = (e) => {
    const variantName = e.target.value;
    setSelectedVariant(variantName);
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      setActualProductionQty(calculateProduction(moCache[key], variantName));
    }
  };

  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    
    // Send both camelCase and snake_case to guarantee the backend accepts it
    const payload = {
      id: editingRecord ? editingRecord.id : undefined, // PATCH: Inject ID if editing
      mo: moNumber.toUpperCase(),
      bearing_type: selectedVariant.toUpperCase(),
      type: selectedVariant.toUpperCase()
    };

    const numFields = ['qtyIn', 'qtySent', 'qty_in', 'qty_sent', 'ballScrap', 'cageSealScrap', 'ball_scrap', 'cage_seal_scrap'];

    for (let [key, value] of fd.entries()) {
      const finalValue = numFields.includes(key) ? (Number(value) || 0) : (value || null);
      payload[key] = finalValue;
      
      // Auto-generate snake_case (e.g., qtyIn -> qty_in) just in case
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
      if (snakeKey !== key) {
        payload[snakeKey] = finalValue;
      }
    }

    try {
      // PATCH: Send correct endpoint dynamically
      const targetEndpoint = endpoint === 'dismantling' ? 'vibration' : endpoint;
      const response = await fetch(`${API}/api/afterchannel/${targetEndpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
      
      alert(editingRecord ? "Entry Updated Successfully!" : "Operational Record Logged Successfully!");
      e.target.reset();
      setEditingRecord(null); // PATCH: clear edit state
      await fetchLedgers(); // Refresh tables immediately
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  // PATCH: Added Handlers for Editing and Deleting Rows
  const handleEdit = (record) => {
    setMoNumber(record.mo || '');
    setSelectedVariant(record.type || record.bearing_type || '');
    setEntryMode((record.qty_sent || record.qtySent) ? 'OUT' : 'IN');
    setEditingRecord(record);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (id, tab) => {
    if(!window.confirm("Are you sure you want to delete this entry permanently?")) return;
    const endpoint = tab === 'dismantling' ? 'vibration' : tab;
    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}/${id}`, { method: 'DELETE' });
      if(response.ok) {
        await fetchLedgers();
        if(editingRecord && editingRecord.id === id) setEditingRecord(null);
      }
    } catch(err) {
      alert("Delete Error: " + err.message);
    }
  };

  // Ultra-forgiving match logic for the tables
  const isScrapStation = (val) => String(val || '').trim().toLowerCase().includes('scrap');
  const matchVariant = (l, v) => {
    const lType = String(l.bearing_type || l.type || l.bearingType || l.variant || '').replace(/\s+/g, '').toUpperCase();
    const vType = String(v).replace(/\s+/g, '').toUpperCase();
    // If the backend failed to save the type, show the row anyway so it's not totally hidden
    return lType === vType || lType === ''; 
  };

  const openSummaryModal = (mo) => {
    const rawRows = moCache[mo] || [];
    const variants = [...new Set(rawRows.map(r => getTypeFromRow(r)))].filter(Boolean);
    
    const breakdown = variants.map(v => {
      const prodQty = calculateProduction(rawRows, v);
      
      const accLedger = ledgers.accurate.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const accIn = accLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const accOut = accLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);
      const accScrap = accLedger.reduce((sum, l) => isScrapStation(l.next_station || l.nextStation) ? sum + (Number(l.qty_sent || l.qtySent) || 0) : sum, 0);

      const cpsLedger = ledgers.cps.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const cpsIn = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const cpsOut = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);
      const cpsScrap = cpsLedger.reduce((sum, l) => isScrapStation(l.next_station || l.nextStation) ? sum + (Number(l.qty_sent || l.qtySent) || 0) : sum, 0);

      const rwLedger = ledgers.rework.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const rwIn = rwLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const rwOut = rwLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);
      const rwScrap = rwLedger.reduce((sum, l) => isScrapStation(l.next_station || l.nextStation) ? sum + (Number(l.qty_sent || l.qtySent) || 0) : sum, 0);

      const disLedger = ledgers.dismantling.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const disIn = disLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const disScrap = disLedger.reduce((sum, l) => isScrapStation(l.next_station || l.nextStation) ? sum + (Number(l.qty_sent || l.qtySent) || 0) : sum, 0);
      const disInternalScrap = disLedger.reduce((sum, l) => sum + (Number(l.ball_scrap || l.ballScrap) || 0) + (Number(l.cage_seal_scrap || l.cageSealScrap) || 0), 0);

      const scrapSum = accScrap + cpsScrap + rwScrap + disScrap + disInternalScrap;

      return {
        variant: v, prodQty,
        accIn, accOut,
        cpsIn, cpsOut,
        rwIn, rwOut,
        disIn, scrapSum
      };
    });

    setSelectedMoDetail({ mo, breakdown });
  };

  // --- DYNAMIC DEPARTMENT LEDGER ENTRY TABLE ---
  const renderDepartmentLedger = (deptKey, deptName) => {
    if (!moNumber || !selectedVariant) return null;
    
    // Filter records safely
    const records = (ledgers[deptKey] || []).filter(l => 
      (l.mo || '').toUpperCase() === moNumber.toUpperCase() && 
      matchVariant(l, selectedVariant)
    );

    if (records.length === 0) return (
      <div style={{marginTop: '30px', padding: '20px', textAlign: 'center', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b'}}>
        No entries found for MO: {moNumber} | Variant: {selectedVariant} in {deptName} yet.
      </div>
    );

    return (
      <div style={{marginTop: '30px', background: '#fff', borderRadius: '8px', border: '1px solid #cbd5e1', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'}}>
        <div style={{background: '#0f172a', padding: '15px 20px', color: '#fff', fontWeight: 'bold', fontSize: '1.2em', display: 'flex', justifyContent: 'space-between'}}>
          <span>{deptName} - Entry Log</span>
          <span style={{color: '#94a3b8', fontSize: '0.8em'}}>MO: {moNumber} | {selectedVariant}</span>
        </div>
        <div style={{overflowX: 'auto'}}>
          <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95em'}}>
            <thead>
              <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Material From</th>
                <th style={{padding: '12px 15px', color: '#1d4ed8', borderRight: '2px solid #cbd5e1', background: '#eff6ff'}}>Qty IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date OUT</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Next Station</th>
                <th style={{padding: '12px 15px', color: '#b45309', background: '#fffbeb', borderRight: '1px solid #e2e8f0'}}>Qty OUT</th>
                {/* PATCH: Added Actions column */}
                <th style={{padding: '12px 15px', color: '#475569'}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const isScrap = isScrapStation(r.next_station || r.nextStation);
                return (
                  <tr key={i} style={{borderBottom: '1px solid #e2e8f0', background: i % 2 === 0 ? '#fff' : '#f8fafc', transition: 'background 0.2s'}} onMouseEnter={(e) => e.currentTarget.style.background = '#e2e8f0'} onMouseLeave={(e) => e.currentTarget.style.background = i % 2 === 0 ? '#fff' : '#f8fafc'}>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.in_date || r.inDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.material_in_from || r.materialInFrom || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '2px solid #cbd5e1', fontWeight: 'bold', color: '#1d4ed8', background: '#eff6ff'}}>{r.qty_in || r.qtyIn || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.out_date || r.outDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', color: isScrap ? '#dc2626' : '#334155', fontWeight: isScrap ? 'bold' : 'normal'}}>
                      {r.next_station || r.nextStation || '-'}
                      {isScrap && <span style={{marginLeft: '5px', fontSize: '0.8em'}}>⚠️</span>}
                    </td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold', color: '#b45309', background: '#fffbeb'}}>{r.qty_sent || r.qtySent || '-'}</td>
                    {/* PATCH: Added Edit/Delete Buttons */}
                    <td style={{padding: '12px 15px'}}>
                      <button type="button" onClick={() => handleEdit(r)} style={{marginRight: '8px', cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Edit Record">✏️</button>
                      <button type="button" onClick={() => handleDelete(r.id, deptKey)} style={{cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Delete Record">🗑️</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const filteredMos = Object.keys(moCache).filter(mo => 
    mo.toUpperCase().includes(searchQuery.toUpperCase())
  );

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      
      <datalist id="depts-list">
        <option value="Channel" /><option value="Accurate" /><option value="CPS" />
        <option value="Rework" /><option value="Dismantling" /><option value="Packaging" />
        <option value="FPS" /><option value="Scrap" />
      </datalist>

      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'].map(ch => <option key={ch} value={ch} />)}
      </datalist>

      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px'}}>
          {['accurate', 'cps', 'rework', 'vibration'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => {setActiveTab(tab); setEditingRecord(null);}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>
            📊 SUMMARY
          </button>
        </div>
      </div>

      {activeTab !== 'summary' && (
        <div style={{marginBottom: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
          <div style={{display: 'flex', gap: '20px'}}>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>MO Number</label>
              <input type="text" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Variant</label>
              {availableVariants.length > 0 ? (
                <select value={selectedVariant} onChange={handleVariantChange} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required>
                  <option value="">-- Select Variant --</option>
                  {availableVariants.map(v => <option key={v.type} value={v.type}>{v.type}</option>)}
                </select>
              ) : (
                <input type="text" value={selectedVariant} onChange={(e) => setSelectedVariant(e.target.value)} placeholder="Manual Entry" style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
              )}
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Target Production Qty</label>
              <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', color: '#16a34a'}} />
            </div>
          </div>

          <div style={{display: 'flex', gap: '20px', marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #cbd5e1'}}>
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📥 LOG IN (Receiving)
            </button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📤 LOG OUT (Dispatch)
            </button>
            {/* PATCH: Cancel Edit Button */}
            {editingRecord && (
              <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); }} style={{padding: '8px 20px', background: '#64748b', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', marginLeft: 'auto'}}>
                Cancel Edit
              </button>
            )}
          </div>
        </div>
      )}

      <div className="ac-content">
        
        {/* ================= ACCURATE TAB ================= */}
        {activeTab === 'accurate' && (
          <div>
            {/* PATCH: Key forces the form to re-render and grab the editingRecord defaultValues */}
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'accurate')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Accurate - Receiving Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>PC No</label><input type="text" name="pcNo" defaultValue={editingRecord?.pc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Accurate - Dispatch Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('accurate', 'Accurate Processing')}
          </div>
        )}

        {/* ================= CPS TAB ================= */}
        {activeTab === 'cps' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'cps')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>CPS Assembly - Receiving Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Item</label><select name="itemType" defaultValue={editingRecord?.item_type || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>CPS Assembly - Dispatch Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('cps', 'CPS Assembly')}
          </div>
        )}

        {/* ================= REWORK TAB ================= */}
        {activeTab === 'rework' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'rework')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Rework Station - Receiving Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineType" defaultValue={editingRecord?.line_type || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Rework Activity</label><input type="text" name="reworkActivity" defaultValue={editingRecord?.rework_activity || ''} style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Rework Station - Dispatch Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Operator</label><input type="text" name="operator" defaultValue={editingRecord?.operator || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Remark</label><input type="text" name="remark" defaultValue={editingRecord?.remark || ''} style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('rework', 'Rework Station')}
          </div>
        )}

        {/* ================= VIBRATION / DISMANTLING TAB ================= */}
        {activeTab === 'vibration' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Vibration Dismantling - Receiving Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineType" defaultValue={editingRecord?.line_type || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Reason</label><select name="reason" defaultValue={editingRecord?.reason || ''} style={{width:'100%', padding:'6px'}}><option></option><option>D4</option><option>OD Mark</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Activity</label><select name="activity" defaultValue={editingRecord?.activity || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Ball Remove</option><option>Rivet Press</option></select></div>
                    <div><label>Ring Type</label><select name="ringType" defaultValue={editingRecord?.ring_type || ''} style={{width:'100%', padding:'6px'}}><option></option><option>IR</option><option>OR</option></select></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Vibration Dismantling - Output Log {editingRecord && <span style={{color:'red'}}>(EDITING)</span>}</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Ball Scrap</label><input type="number" name="ballScrap" defaultValue={editingRecord?.ball_scrap || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Cage/Seal Scrap</label><input type="number" name="cageSealScrap" defaultValue={editingRecord?.cage_seal_scrap || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Operator</label><input type="text" name="operator" defaultValue={editingRecord?.operator || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Remark</label><input type="text" name="remark" defaultValue={editingRecord?.remark || ''} style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Vibration/Dismantling')}
          </div>
        )}

        {/* ================= SUMMARY VIEW ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '25px', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', border: '1px solid #e2e8f0'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.4em', margin: 0, color: '#0f172a', fontWeight: 'bold'}}>Active Master Orders (MO) Reference Index</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} style={{padding: '10px 15px', width: '350px', border: '2px solid #cbd5e1', borderRadius: '6px', outline: 'none', transition: 'border-color 0.2s'}} onFocus={(e) => e.target.style.borderColor = '#2563eb'} onBlur={(e) => e.target.style.borderColor = '#cbd5e1'} />
            </div>
            
            <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95em', border: '1px solid #cbd5e1'}}>
              <thead>
                <tr style={{background: '#1e293b', color: '#f8fafc'}}>
                  <th style={{padding: '15px', fontWeight: '600', borderRight: '1px solid #334155'}}>Master Order (MO) ID</th>
                  <th style={{padding: '15px', fontWeight: '600', borderRight: '1px solid #334155'}}>Registered Specifications Count</th>
                  <th style={{padding: '15px', fontWeight: '600', textAlign: 'center'}}>Audit Control</th>
                </tr>
              </thead>
              <tbody>
                {filteredMos.map((mo, index) => (
                  <tr key={mo} style={{background: index % 2 === 0 ? '#ffffff' : '#f8fafc', borderBottom: '1px solid #cbd5e1', transition: 'background 0.2s'}} onMouseEnter={(e) => e.currentTarget.style.background = '#e2e8f0'} onMouseLeave={(e) => e.currentTarget.style.background = index % 2 === 0 ? '#ffffff' : '#f8fafc'}>
                    <td style={{padding: '15px', fontWeight: 'bold', color: '#2563eb', borderRight: '1px solid #cbd5e1'}}>{mo}</td>
                    <td style={{padding: '15px', color: '#475569', borderRight: '1px solid #cbd5e1'}}>{moCache[mo] ? moCache[mo].length : 0} Variant Matrices Compiled</td>
                    <td style={{padding: '15px', textAlign: 'center'}}>
                      <button onClick={() => openSummaryModal(mo)} style={{padding: '8px 16px', background: '#0284c7', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 2px 4px rgba(0,0,0,0.1)'}}>
                        View Detailed Pipeline
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedMoDetail && (
        <div className="modal-backdrop" style={{position: 'fixed', top:0, left:0, width:'100vw', height:'100vh', background:'rgba(15, 23, 42, 0.75)', display:'flex', justifyContent:'center', alignItems:'center', zIndex: 1000}}>
          <div className="modal-window" style={{background:'#fff', padding:'30px', borderRadius:'10px', width:'95%', maxWidth:'1300px', maxHeight:'85vh', overflowY:'auto', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)'}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', borderBottom:'3px solid #0f172a', paddingBottom:'15px', marginBottom:'25px'}}>
              <h2 style={{margin: 0, color: '#0f172a'}}>Cross-Department Flow Trace: <span style={{color: '#2563eb'}}>{selectedMoDetail.mo}</span></h2>
              <button onClick={() => setSelectedMoDetail(null)} style={{fontSize:'2em', cursor:'pointer', border:'none', background:'none', color: '#64748b', lineHeight: '1'}}>&times;</button>
            </div>
            
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.9em', border: '1px solid #94a3b8'}}>
              <thead>
                <tr style={{background: '#334155', color: '#fff'}}>
                  <th style={{border: '1px solid #475569', padding: '12px', textAlign: 'left'}}>Variant Model</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#166534'}}>Actual Prod Qty</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#1e40af'}}>Accurate In</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#1e40af'}}>Accurate Out</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#86198f'}}>CPS In</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#86198f'}}>CPS Out</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#b45309'}}>Rework In</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#b45309'}}>Rework Out</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#374151'}}>Dismantle In</th>
                  <th style={{border: '1px solid #475569', padding: '12px', background: '#991b1b'}}>Scrap Sum</th>
                </tr>
              </thead>
              <tbody>
                {selectedMoDetail.breakdown.map((row, i) => (
                  <tr key={i} style={{background: i % 2 === 0 ? '#fff' : '#f1f5f9', borderBottom: '1px solid #cbd5e1', textAlign: 'center'}}>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', fontWeight:'bold', textAlign:'left', color: '#334155'}}>{row.variant}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', background:'#dcfce7', color:'#166534', fontWeight:'bold'}}>{row.prodQty > 0 ? row.prodQty.toLocaleString() : '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af'}}>{row.accIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af'}}>{row.accOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f'}}>{row.cpsIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f'}}>{row.cpsOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309'}}>{row.rwIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309'}}>{row.rwOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151'}}>{row.disIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', background: '#fee2e2', color:'#991b1b', fontWeight: 'bold'}}>{row.scrapSum || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Afterchannel;

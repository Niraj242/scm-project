import React, { useState, useEffect, useMemo } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  // Global States
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [], autopackaging: [], fps: [] });
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState('');
  const [editingRecord, setEditingRecord] = useState(null);
  
  // Header Inputs
  const [moNumber, setMoNumber] = useState('');
  const [selectedVariant, setSelectedVariant] = useState('');
  const [actualProductionQty, setActualProductionQty] = useState(0);
  const [availableVariantsList, setAvailableVariantsList] = useState([]);
  const [availableMos, setAvailableMos] = useState([]);
  const [formDate, setFormDate] = useState('');

  // Tab-Specific States
  const [bearingFamily, setBearingFamily] = useState(''); 

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
  }, []);

  const fetchMasterData = async () => {
    try {
      const res = await fetch(`${API}/api/mo-lookup`);
      const data = await res.json();
      if (data.status === 'success') {
        setMoCache(data.data || {});
        setAvailableMos(Object.keys(data.data || {}));
      }
    } catch (err) {
      console.error("Master Reference Load Failure:", err);
    }
  };

  const fetchLedgers = async () => {
    try {
      const depts = ['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'];
      const updatedLedgers = {};
      
      // We fetch all ledgers individually as the backend might expose them as individual endpoints
      // Fallback logic implemented if you use a combined summary endpoint
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`).catch(() => null);
      if (res && res.ok) {
        const json = await res.json();
        const data = json.data || {};
        setLedgers({
          accurate: data.accurate || [],
          cps: data.cps || [],
          rework: data.rework || [],
          dismantling: data.dismantling || data.vibration || [],
          autopackaging: data.autopackaging || [],
          fps: data.fps || []
        });
      } else {
        // Fallback if summary_ledgers is not available
        for (const dept of depts) {
          const endpoint = dept === 'dismantling' ? 'vibration' : dept;
          const deptRes = await fetch(`${API}/api/afterchannel/${endpoint}`);
          if(deptRes.ok) {
             const data = await deptRes.json();
             updatedLedgers[dept] = Array.isArray(data) ? data : (data.data || []);
          }
        }
        setLedgers(updatedLedgers);
      }
    } catch (err) {
      console.error("Ledger Sync Failure:", err);
    }
  };

  // --- MO & Variant Logic ---
  const getQtyFromRow = (row) => {
    for (const key in row) {
      const cleanKey = key.toLowerCase().replace(/[^a-z]/g, '');
      if (['qty', 'quantity', 'production', 'target', 'plan', 'total'].some(w => cleanKey.includes(w))) {
        const val = parseFloat(String(row[key]).replace(/,/g, ''));
        if (!isNaN(val) && val > 0) return val;
      }
    }
    return 0;
  };

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
      if (rowType === cleanMatch) return sum + getQtyFromRow(r);
      return sum;
    }, 0);
  };

  const allVariants = useMemo(() => {
    const variants = new Set();
    Object.values(moCache).forEach(rows => {
      rows.forEach(r => {
        const t = getTypeFromRow(r);
        if (t) variants.add(t.toUpperCase());
      });
    });
    return Array.from(variants);
  }, [moCache]);

  useEffect(() => {
    if (moNumber && moCache[moNumber.toUpperCase()]) {
      const rawRows = moCache[moNumber.toUpperCase()];
      const uniqueVariants = [...new Set(rawRows.map(r => getTypeFromRow(r).toUpperCase()))].filter(Boolean);
      setAvailableVariantsList(uniqueVariants);
    } else {
      setAvailableVariantsList(allVariants);
    }

    if (!selectedVariant) {
      setAvailableMos(Object.keys(moCache));
      return;
    }
    
    let matchingMos = Object.keys(moCache).filter(mo => {
      return moCache[mo].some(r => getTypeFromRow(r).toUpperCase() === selectedVariant);
    });

    setAvailableMos(matchingMos);
  }, [selectedVariant, formDate, moCache, moNumber, allVariants]);

  const handleMoBlur = () => {
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      const rawRows = moCache[key];
      const uniqueVariants = [...new Set(rawRows.map(r => getTypeFromRow(r)))].filter(Boolean);
      
      if (uniqueVariants.length === 1) {
        setSelectedVariant(uniqueVariants[0]);
        setActualProductionQty(calculateProduction(rawRows, uniqueVariants[0]));
      } else {
        if (!uniqueVariants.includes(selectedVariant)) setSelectedVariant('');
        setActualProductionQty(selectedVariant ? calculateProduction(rawRows, selectedVariant) : 0);
      }
    } else {
      setSelectedVariant('');
      setActualProductionQty(0);
      setAvailableMos(Object.keys(moCache)); 
    }
  };

  const handleVariantChange = (e) => {
    const variantName = e.target.value.toUpperCase();
    setSelectedVariant(variantName);
    if (moNumber && moCache[moNumber.toUpperCase()]) {
      setActualProductionQty(calculateProduction(moCache[moNumber.toUpperCase()], variantName));
    }
  };

  // --- Form & API Handling ---
  const handleFormSubmit = async (e) => {
    e.preventDefault();
    
    // HTTP 500 FIX: Carefully build payload ensuring no 'undefined' reaches Python BaseModel.
    // Map camelCase explicitly as python's FastAPI/Pydantic BaseModel expects it.
    const qtyValue = parseInt(e.target.qty?.value) || 0;

    const payload = {
      id: editingRecord ? editingRecord.id : undefined,
      mo: moNumber.toUpperCase(),
      type: entryMode,
      inDate: entryMode === 'IN' ? (formDate || null) : null,
      shiftIn: entryMode === 'IN' ? (e.target.shiftIn?.value || null) : null,
      materialInFrom: e.target.materialInFrom?.value || null,
      qtyIn: entryMode === 'IN' ? qtyValue : 0,
      
      outDate: entryMode === 'OUT' ? (formDate || null) : null,
      shiftOut: entryMode === 'OUT' ? (e.target.shiftOut?.value || null) : null,
      nextStation: e.target.nextStation?.value || null,
      qtySent: entryMode === 'OUT' ? qtyValue : 0,
      
      // Specific to models
      pc: e.target.pc?.value || null,
      item: selectedVariant.toUpperCase(), // Alias mapping
      bearing_type: selectedVariant.toUpperCase(), // Alias mapping
      rcNo: e.target.rcNo?.value || null,
      channel: e.target.channel?.value || null,
      reason: e.target.reason?.value || null,
      customerOrder: e.target.customerOrder?.value || null,

      // Dismantling / Scrap specifics
      bearingFamily: bearingFamily || null,
      ringType: e.target.ringType?.value || 'Whole Bearing',
      remark: e.target.remark?.value || null,
      
      irScrap: parseInt(e.target.irScrap?.value) || 0,
      orScrap: parseInt(e.target.orScrap?.value) || 0,
      cageScrap: parseInt(e.target.cageScrap?.value) || 0,
      ballScrap: parseInt(e.target.ballScrap?.value) || 0,
      rollerScrap: parseInt(e.target.rollerScrap?.value) || 0,
      sealScrap: parseInt(e.target.sealScrap?.value) || 0,
      shieldScrap: parseInt(e.target.shieldScrap?.value) || 0,
    };

    const endpoint = activeTab === 'dismantling' ? 'vibration' : activeTab;
    let url = `${API}/api/afterchannel/${endpoint}`;
    let method = 'POST';

    if (editingRecord) {
      url = `${API}/api/afterchannel/${endpoint}/${editingRecord.id}`;
      method = 'PUT'; // Using PUT as per original logic for edits
    }

    try {
      const response = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      alert(editingRecord ? "Entry Updated Successfully!" : "Operational Record Logged Successfully!");
      e.target.reset();
      setEditingRecord(null);
      await fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  const handleEditInit = (row) => {
    setMoNumber(row.mo || '');
    setSelectedVariant(row.item || row.bearing_type || row.type || '');
    setBearingFamily(row.bearing_family || row.bearingFamily || '');
    setEntryMode((row.qtySent || row.qty_sent) ? 'OUT' : 'IN');
    setFormDate(row.inDate || row.in_date || row.outDate || row.out_date || '');
    setEditingRecord(row);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDeleteEntry = async (id, tab) => {
    if(!window.confirm("Are you sure you want to delete this entry permanently?")) return;
    const endpoint = tab === 'dismantling' ? 'vibration' : tab;
    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}/${id}`, { method: 'DELETE' });
      if(response.ok) {
        alert("Entry deleted successfully.");
        await fetchLedgers();
        if(editingRecord && editingRecord.id === id) setEditingRecord(null);
      }
    } catch(err) {
      alert("Delete Error: " + err.message);
    }
  };

  // --- Summary Generation Logic ---
  const generateSummaryData = () => {
    const summaryMap = {};
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

    ledgers.accurate.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.accIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.accOut += (r.qtySent || r.qty_sent || 0);
    });

    ledgers.cps.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.cpsIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.cpsOut += (r.qtySent || r.qty_sent || 0);
    });

    ledgers.rework.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.rwIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.rwOut += (r.qtySent || r.qty_sent || 0);
    });

    ledgers.dismantling.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.disIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.disOut += (r.qtySent || r.qty_sent || 0);
      
      node.irScrap += (r.irScrap || r.ir_scrap || 0);
      node.orScrap += (r.orScrap || r.or_scrap || 0);
      node.cageScrap += (r.cageScrap || r.cage_scrap || 0);
      node.ballScrap += (r.ballScrap || r.ball_scrap || r.rollerScrap || r.roller_scrap || 0); 
    });

    ledgers.autopackaging.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.apIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.apOut += (r.qtySent || r.qty_sent || 0);
    });

    ledgers.fps.forEach(r => {
      const node = summaryMap[r.mo];
      if (!node) return;
      if (r.type === 'IN') node.fpsIn += (r.qtyIn || r.qty_in || 0);
      if (r.type === 'OUT') node.fpsOut += (r.qtySent || r.qty_sent || 0); 
    });

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
    return list.filter(item => (item.mo || '').toLowerCase().includes(ledgerSearchQuery.toLowerCase()));
  };

  // --- Rendering UI Helpers ---
  const renderField = (label, name, type="text", list=null, required=false, options=[]) => {
    // Determine the default value considering both camelCase and snake_case from DB
    const snakeCaseName = name.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
    let defaultValue = editingRecord?.[name] !== undefined ? editingRecord[name] : editingRecord?.[snakeCaseName];
    if(defaultValue === undefined || defaultValue === null) defaultValue = '';

    return (
      <div>
        <label style={{display: 'block', fontWeight: '500', marginBottom: '4px', fontSize: '0.9em', color: '#334155'}}>{label}</label>
        {options.length > 0 ? (
          <select name={name} defaultValue={defaultValue} style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px'}} required={required}>
            <option value=""></option>
            {options.map(o => <option key={o.value || o} value={o.value || o}>{o.label || o}</option>)}
          </select>
        ) : (
          <input type={type} name={name} list={list} required={required}
            defaultValue={defaultValue}
            onChange={type === 'date' ? (e) => setFormDate(e.target.value) : undefined}
            style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px', boxSizing:'border-box'}} 
          />
        )}
      </div>
    );
  };

  return (
    <div className="scrap-module">
      {/* Global Datalists */}
      <datalist id="depts-list">
        <option value="Channel" /><option value="Accurate" /><option value="CPS" />
        <option value="Rework" /><option value="Dismantling" /><option value="Autopackaging" />
        <option value="FPS" /><option value="Scrap" />
      </datalist>
      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'].map(ch => <option key={ch} value={ch} />)}
      </datalist>
      <datalist id="mo-list">{availableMos.map(mo => <option key={mo} value={mo} />)}</datalist>
      <datalist id="variant-list">{availableVariantsList.map(v => <option key={v} value={v} />)}</datalist>

      <div className="module-header">
        <h2>🏭 AFTERCHANNEL PRODUCTION & SCRAP TRACKER</h2>
        <p style={{margin:0, color:'#64748b'}}>Centralized logistics control for Accurate, CPS, Rework, Dismantling, Auto-Packaging & FPS</p>
      </div>

      {/* TABS */}
      <div className="sub-view-tabs">
        {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
          <button key={tab} className={`tab-btn ${activeTab === tab ? 'active' : ''}`} 
            onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily('');}} 
            style={{background: activeTab === tab ? '#0f172a' : '', color: activeTab === tab ? '#fff' : ''}}>
            {tab.toUpperCase()}
          </button>
        ))}
        <button className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
          onClick={() => { setActiveTab('summary'); setEditingRecord(null); setLedgerSearchQuery(''); }}
          style={{background: activeTab === 'summary' ? '#166534' : '#dcfce7', color: activeTab === 'summary' ? '#fff' : '#166534', border: '1px solid #bbf7d0'}}>
          📊 SUMMARY VIEW
        </button>
      </div>

      {activeTab !== 'summary' && (
        <div style={{background: '#fff', padding:'20px', borderRadius:'8px', boxShadow:'0 1px 3px rgba(0,0,0,0.05)', marginBottom:'24px'}}>
          <h3 style={{marginTop:0, marginBottom:'20px', color: '#1e293b', borderBottom:'1px solid #e2e8f0', paddingBottom:'10px'}}>
             {editingRecord ? `✏️ Edit ${activeTab.toUpperCase()} Record` : `➕ Log New ${activeTab.toUpperCase()} Entry`}
          </h3>
          
          <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={handleFormSubmit}>
            
            {/* Global Header Inputs */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginBottom: '20px'}}>
              <div>
                <label style={{display: 'block', fontWeight: '600', marginBottom: '8px'}}>Variant / Type</label>
                <input list="variant-list" value={selectedVariant} onChange={handleVariantChange} placeholder="Type or Select Variant..." style={{width: '100%', padding: '10px', border: '1px solid #cbd5e1', borderRadius: '6px'}} required />
              </div>
              <div>
                <label style={{display: 'block', fontWeight: '600', marginBottom: '8px'}}>MO Number</label>
                <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." style={{width: '100%', padding: '10px', border: '1px solid #cbd5e1', borderRadius: '6px'}} required />
              </div>
              <div>
                <label style={{display: 'block', fontWeight: '600', marginBottom: '8px'}}>Target Qty Reference</label>
                <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '10px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '6px', fontWeight: 'bold', color: '#16a34a'}} />
              </div>
            </div>
            
            {/* IN / OUT Toggles */}
            <div style={{display: 'flex', gap: '15px', marginBottom: '20px', paddingBottom: '20px', borderBottom: '1px dashed #cbd5e1'}}>
              <button type="button" onClick={() => setEntryMode('IN')} style={{flex: 1, padding: '10px', background: entryMode === 'IN' ? '#2563eb' : '#f1f5f9', color: entryMode === 'IN' ? '#fff' : '#64748b', border: entryMode === 'IN' ? 'none' : '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📥 RECEIVE (IN)</button>
              <button type="button" onClick={() => setEntryMode('OUT')} style={{flex: 1, padding: '10px', background: entryMode === 'OUT' ? '#ea580c' : '#f1f5f9', color: entryMode === 'OUT' ? '#fff' : '#64748b', border: entryMode === 'OUT' ? 'none' : '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📤 DISPATCH (OUT)</button>
            </div>

            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px'}}>
              {/* COMMON FIELDS */}
              {entryMode === 'IN' ? (
                <>
                  {renderField("In Date", "inDate", "date", null, true)}
                  {renderField("Shift In", "shiftIn", "text", null, false, ['Shift A', 'Shift B', 'Shift C'])}
                  {renderField("Material In From", "materialInFrom", "text", "depts-list")}
                </>
              ) : (
                <>
                  {renderField("Out Date", "outDate", "date", null, true)}
                  {renderField("Shift Out", "shiftOut", "text", null, false, ['Shift A', 'Shift B', 'Shift C'])}
                  {activeTab !== 'fps' && renderField("Next Station", "nextStation", "text", "depts-list")}
                </>
              )}

              {/* SPECIFIC TAB LOGIC */}
              {activeTab === 'accurate' && entryMode === 'IN' && renderField("PC", "pc", "text")}
              
              {activeTab === 'cps' && (
                <>
                  {renderField("RC No", "rcNo", "text")}
                  {renderField("Channel", "channel", "text", "channels-list")}
                </>
              )}

              {['rework', 'dismantling'].includes(activeTab) && (
                <div style={{gridColumn: 'span 1'}}>
                  <label style={{display:'block', fontWeight:'500', marginBottom:'4px', fontSize:'0.9em', color:'#334155'}}>Bearing Family</label>
                  <select name="bearingFamily" defaultValue={editingRecord?.bearing_family || editingRecord?.bearingFamily || bearingFamily} onChange={(e)=>setBearingFamily(e.target.value)} style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px'}}>
                    <option value=""></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option>
                  </select>
                </div>
              )}
              
              {activeTab === 'rework' && entryMode === 'IN' && renderField("Reason", "reason", "text")}
              {activeTab === 'dismantling' && entryMode === 'IN' && renderField("Channel", "channel", "text", "channels-list")}

              {/* DISMANTLING COMPONENT SCRAP LOGIC */}
              {activeTab === 'dismantling' && entryMode === 'OUT' && (
                 <>
                    <div style={{gridColumn: '1 / -1', background: '#fef2f2', padding: '15px', borderRadius: '6px', border: '1px solid #fca5a5', marginTop: '10px'}}>
                      <h4 style={{margin: '0 0 10px 0', color: '#991b1b'}}>🛠️ Dismantled Component Output & Scrap</h4>
                      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '15px'}}>
                        {renderField("IR Scrap", "irScrap", "number")}
                        {renderField("OR Scrap", "orScrap", "number")}
                        {renderField("Cage Scrap", "cageScrap", "number")}
                        {bearingFamily === 'TRB' ? renderField("Roller Scrap", "rollerScrap", "number") : renderField("Ball Scrap", "ballScrap", "number")}
                        {renderField("Seal Scrap", "sealScrap", "number")}
                        {renderField("Shield Scrap", "shieldScrap", "number")}
                      </div>
                    </div>
                    {renderField("Component Sent Type", "ringType", "text", null, false, [
                      {value: 'Whole Bearing', label: 'Whole Bearing'},
                      {value: 'IR', label: 'Inner Ring (IR)'},
                      {value: 'OR', label: 'Outer Ring (OR)'},
                      {value: 'Components', label: 'Mixed Components'}
                    ])}
                    <div style={{gridColumn: 'span 2'}}>{renderField("Flow Remarks (e.g. 10 OR sent, 2 IR Scraped)", "remark", "text")}</div>
                 </>
              )}

              {activeTab === 'fps' && entryMode === 'OUT' && renderField("Customer Order", "customerOrder", "text")}

              {/* QUANTITY FIELD */}
              {renderField(activeTab === 'dismantling' && entryMode === 'OUT' ? "Qty Sent (Main Flow)" : "Quantity (Pcs)", "qty", "number", null, true)}

            </div>

            <div style={{marginTop:'20px', display:'flex', gap:'10px', justifyContent:'flex-end'}}>
              {editingRecord && (
                <button type="button" onClick={() => setEditingRecord(null)} style={{background:'#e2e8f0', color:'#475569', padding:'10px 20px', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>Cancel Edit</button>
              )}
              <button type="submit" style={{background: entryMode === 'IN' ? '#2563eb' : '#ea580c', color:'#fff', padding:'10px 25px', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>
                {editingRecord ? "💾 Update Ledger Entry" : "🚀 Submit Entry Record"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Ledger Records and Summary Presentation Block */}
      <div style={{background: '#fff', padding:'20px', borderRadius:'8px', boxShadow:'0 1px 3px rgba(0,0,0,0.05)'}}>
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'16px', flexWrap:'wrap', gap:'12px'}}>
          <h3 style={{margin:0}}>📋 {activeTab === 'summary' ? "Cross-Department Production Reconciliation Summary" : `${activeTab.toUpperCase()} Operational Logs`}</h3>
          <input type="text" placeholder="🔍 Search and filter by MO Number..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding:'8px 12px', borderRadius:'4px', border:'1px solid #cbd5e1', width:'300px'}} />
        </div>

        <div style={{overflowX:'auto'}}>
          {activeTab === 'summary' ? (
            <table style={{width:'100%', borderCollapse:'collapse', fontSize:'13px', textAlign:'left'}}>
              <thead>
                <tr style={{background:'#f1f5f9', borderBottom:'2px solid #cbd5e1'}}>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1'}}>MO Number</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#eff6ff', color: '#1e40af'}}>Accurate IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#eff6ff', color: '#1e40af'}}>Accurate OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fae8ff', color: '#86198f'}}>CPS IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fae8ff', color: '#86198f'}}>CPS OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fef3c7', color: '#b45309'}}>Rework IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fef3c7', color: '#b45309'}}>Rework OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f3f4f6', color: '#374151'}}>Dismantling IN</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#f3f4f6', color: '#374151'}}>Dismantling OUT</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>IR Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>OR Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>Cage Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', color: '#991b1b'}}>Ball/Roll Scrap</th>
                  <th style={{padding:'12px', border:'1px solid #cbd5e1', background: '#fee2e2', color: '#991b1b', fontWeight:'bold'}}>Total Component Scrap</th>
                </tr>
              </thead>
              <tbody>
                {filteredLedgerData().map((row, index) => (
                  <tr key={index} style={{borderBottom:'1px solid #e2e8f0', background: index % 2 === 0 ? '#fff' : '#f8fafc'}}>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', fontWeight:'bold'}}>{row.mo}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af', fontWeight:'bold'}}>{row.accIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#1e40af'}}>{row.accOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f', fontWeight:'bold'}}>{row.cpsIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#86198f'}}>{row.cpsOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309', fontWeight:'bold'}}>{row.rwIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#b45309'}}>{row.rwOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151', fontWeight:'bold'}}>{row.disIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151'}}>{row.disOut || '-'}</td>
                    
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
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Variant</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Type</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Date</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Shift</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Qty In</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Qty Sent</th>
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>From/Next</th>
                  {activeTab === 'dismantling' && (
                    <th style={{padding:'10px', border:'1px solid #cbd5e1', color:'#991b1b', width: '300px'}}>Dismantle Flow & Scrap Log</th>
                  )}
                  <th style={{padding:'10px', border:'1px solid #cbd5e1'}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredLedgerData().map((row) => (
                  <tr key={row.id} style={{borderBottom:'1px solid #e2e8f0', background: row.type==='IN'?'#fff':'#f8fafc'}}>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', fontWeight:'bold'}}>{row.mo}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', fontWeight:'600'}}>{row.item || row.type || row.bearing_type || row.bearingType || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>
                      <span style={{padding:'2px 6px', borderRadius:'4px', fontSize:'11px', fontWeight:'bold', background: row.type==='IN'?'#dbeafe':'#ffedd5', color: row.type==='IN'?'#1e40af':'#c2410c'}}>
                        {row.type}
                      </span>
                    </td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.inDate || row.in_date || row.outDate || row.out_date || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>{row.shiftIn || row.shift_in || row.shiftOut || row.shift_out || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#16a34a', fontWeight:'bold', background:'#f0fdf4'}}>{row.qtyIn || row.qty_in || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1', color:'#ea580c', fontWeight:'bold', background:'#fff7ed'}}>{row.qtySent || row.qty_sent || '-'}</td>
                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>
                       {row.type === 'IN' ? `From: ${row.materialInFrom || row.material_in_from || '-'}` : `To: ${row.nextStation || row.next_station || '-'}`}
                    </td>
                    
                    {activeTab === 'dismantling' && (
                      <td style={{padding:'10px', border:'1px solid #cbd5e1', fontSize:'0.9em', color:'#7f1d1d'}}>
                         {(row.irScrap || row.ir_scrap || row.orScrap || row.or_scrap || row.cageScrap || row.cage_scrap || row.ballScrap || row.ball_scrap || row.rollerScrap || row.roller_scrap) ? (
                            `IR:${row.irScrap||row.ir_scrap||0} | OR:${row.orScrap||row.or_scrap||0} | C:${row.cageScrap||row.cage_scrap||0} | B/R:${(row.ballScrap||row.ball_scrap||0)+(row.rollerScrap||row.roller_scrap||0)}`
                         ) : '-'}
                         {row.ringType && row.ringType !== 'Whole Bearing' && <div style={{color: '#b45309', marginTop: '4px'}}>Sent: {row.ringType}</div>}
                         {(row.remark || row.scrapReason || row.scrap_reason) && <div style={{color: '#0369a1', marginTop: '4px', fontStyle: 'italic'}}>{row.remark || row.scrapReason || row.scrap_reason}</div>}
                      </td>
                    )}

                    <td style={{padding:'10px', border:'1px solid #cbd5e1'}}>
                      <button onClick={() => handleEditInit(row)} style={{marginRight:'6px', padding:'4px 8px', background:'#e2e8f0', border:'none', borderRadius:'3px', cursor:'pointer', fontWeight:'bold'}}>Edit</button>
                      <button onClick={() => handleDeleteEntry(row.id, activeTab)} style={{padding:'4px 8px', background:'#fee2e2', color:'#b91c1c', border:'none', borderRadius:'3px', cursor:'pointer', fontWeight:'bold'}}>Del</button>
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

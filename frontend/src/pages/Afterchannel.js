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
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`);
      const json = await res.json();
      if (json.status === 'success' || json.data) {
        setLedgers({
          accurate: json.data?.accurate || [],
          cps: json.data?.cps || [],
          rework: json.data?.rework || [],
          dismantling: json.data?.dismantling || json.data?.vibration || [],
          autopackaging: json.data?.autopackaging || [],
          fps: json.data?.fps || []
        });
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

    if (formDate) {
      const inputTime = new Date(formDate).getTime();
      matchingMos = matchingMos.filter(mo => {
        return moCache[mo].some(r => {
          if (getTypeFromRow(r).toUpperCase() !== selectedVariant) return false;
          if (!r.date) return true; 
          const moTime = new Date(r.date).getTime();
          const diffDays = Math.abs((moTime - inputTime) / (1000 * 3600 * 24));
          return diffDays <= 2;
        });
      });
    }

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
  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    
    const payload = {
      id: editingRecord ? editingRecord.id : undefined,
      mo: moNumber.toUpperCase(),
      bearing_type: selectedVariant.toUpperCase(),
      type: selectedVariant.toUpperCase()
    };

    const numFields = ['qtyIn', 'qtySent', 'qty_in', 'qty_sent', 'ballScrap', 'rollerScrap', 'cageScrap', 'sealScrap', 'shieldScrap', 'irScrap', 'orScrap'];

    for (let [key, value] of fd.entries()) {
      const finalValue = numFields.includes(key) ? (Number(value) || 0) : (value || null);
      payload[key] = finalValue;
      // Convert camelCase to snake_case for backend compatibility
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
      if (snakeKey !== key) payload[snakeKey] = finalValue;
    }

    try {
      const targetEndpoint = endpoint === 'dismantling' ? 'vibration' : endpoint;
      const response = await fetch(`${API}/api/afterchannel/${targetEndpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
      
      alert(editingRecord ? "Entry Updated Successfully!" : "Operational Record Logged Successfully!");
      e.target.reset();
      setEditingRecord(null);
      await fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  const handleEdit = (record) => {
    setMoNumber(record.mo || '');
    setSelectedVariant(record.type || record.bearing_type || record.item_type || '');
    setBearingFamily(record.bearing_family || '');
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

  const isScrapStation = (val) => String(val || '').trim().toLowerCase().includes('scrap');

  // --- Rendering UI Helpers ---
  const renderField = (label, name, type="text", list=null, required=false, options=[]) => (
    <div>
      <label style={{display: 'block', fontWeight: '500', marginBottom: '4px', fontSize: '0.9em', color: '#334155'}}>{label}</label>
      {options.length > 0 ? (
        <select name={name} defaultValue={editingRecord?.[name] || editingRecord?.[name.replace(/[A-Z]/g, l => `_${l.toLowerCase()}`)] || ''} style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px'}} required={required}>
          <option value=""></option>
          {options.map(o => <option key={o.value || o} value={o.value || o}>{o.label || o}</option>)}
        </select>
      ) : (
        <input type={type} name={name} list={list} required={required}
          defaultValue={editingRecord?.[name] || editingRecord?.[name.replace(/[A-Z]/g, l => `_${l.toLowerCase()}`)] || ''}
          onChange={type === 'date' ? (e) => setFormDate(e.target.value) : undefined}
          style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px', boxSizing:'border-box'}} 
        />
      )}
    </div>
  );

  const renderTableHeaders = (headers) => (
    <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
      {headers.map((h, i) => <th key={i} style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>{h}</th>)}
      <th style={{padding: '12px 15px', color: '#475569'}}>Actions</th>
    </tr>
  );

  const renderDepartmentLedger = (deptKey, deptName) => {
    const deptData = ledgers[deptKey] || [];
    const records = deptData.filter(l => {
      const search = ledgerSearchQuery.toUpperCase();
      const moMatch = (l.mo || '').toUpperCase().includes(search);
      const typeMatch = (l.bearing_type || l.type || l.item_type || '').toUpperCase().includes(search);
      return moMatch || typeMatch;
    });

    if (records.length === 0) return (
      <div style={{marginTop: '30px', padding: '20px', textAlign: 'center', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b'}}>
        No entries found for {deptName}.
      </div>
    );

    return (
      <div style={{marginTop: '30px', background: '#fff', borderRadius: '8px', border: '1px solid #cbd5e1', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'}}>
        <div style={{background: '#0f172a', padding: '15px 20px', color: '#fff', fontWeight: 'bold', fontSize: '1.2em', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <span>{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '8px 12px', border: '1px solid #cbd5e1', borderRadius: '4px', width: '300px', outline: 'none', color: '#000'}} />
        </div>
        <div style={{overflowX: 'auto'}}>
          <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95em'}}>
            <thead>
              {deptKey === 'accurate' && renderTableHeaders(['MO', 'Variant', 'Date IN', 'Shift IN', 'PC', 'Material From', 'Qty IN', 'Date OUT', 'Shift OUT', 'Next Station', 'Qty OUT'])}
              {deptKey === 'cps' && renderTableHeaders(['MO', 'Variant', 'Item', 'Date IN', 'Shift IN', 'RC No', 'Material From', 'Channel', 'Qty IN', 'Date OUT', 'Shift OUT', 'Next Station', 'Qty OUT'])}
              {deptKey === 'rework' && renderTableHeaders(['MO', 'Variant', 'Family', 'Date IN', 'Shift IN', 'Material From', 'Reason', 'Qty IN', 'Date OUT', 'Shift OUT', 'Next Station', 'Qty OUT'])}
              {deptKey === 'dismantling' && renderTableHeaders(['MO', 'Variant', 'Family', 'Date IN', 'Shift IN', 'Channel', 'Material From', 'Qty IN', 'Date OUT', 'Shift OUT', 'Next Station', 'Qty OUT', 'Scrap & Notes'])}
              {deptKey === 'autopackaging' && renderTableHeaders(['MO', 'Variant', 'Date IN', 'Shift IN', 'Material From', 'Qty IN', 'Date OUT', 'Shift OUT', 'Next Station', 'Qty OUT'])}
              {deptKey === 'fps' && renderTableHeaders(['MO', 'Variant', 'Date IN', 'Shift IN', 'Material From', 'Qty IN', 'Date OUT', 'Shift OUT', 'Customer Order', 'Qty OUT'])}
            </thead>
            <tbody>
              {records.map((r, i) => {
                const isScrap = isScrapStation(r.next_station || r.nextStation);
                return (
                  <tr key={i} style={{borderBottom: '1px solid #e2e8f0', background: i % 2 === 0 ? '#fff' : '#f8fafc', transition: 'background 0.2s'}}>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.mo || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.bearing_type || r.type || r.item_type || '-'}</td>
                    
                    {/* Unique Columns Per Tab */}
                    {deptKey === 'cps' && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.item || '-'}</td>}
                    {['rework', 'dismantling'].includes(deptKey) && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.bearing_family || '-'}</td>}
                    
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.in_date || r.inDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.shift_in || r.shiftIn || '-'}</td>

                    {deptKey === 'accurate' && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.pc || '-'}</td>}
                    {deptKey === 'cps' && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.rc_no || r.rcNo || '-'}</td>}
                    
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.material_in_from || r.materialInFrom || '-'}</td>
                    
                    {['cps', 'dismantling'].includes(deptKey) && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.channel || '-'}</td>}
                    {deptKey === 'rework' && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.reason || '-'}</td>}

                    <td style={{padding: '12px 15px', borderRight: '2px solid #cbd5e1', fontWeight: 'bold', color: '#1d4ed8', background: '#eff6ff'}}>{r.qty_in || r.qtyIn || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.out_date || r.outDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.shift_out || r.shiftOut || '-'}</td>
                    
                    {deptKey !== 'fps' && (
                      <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', color: isScrap ? '#dc2626' : '#334155', fontWeight: isScrap ? 'bold' : 'normal'}}>
                        {r.next_station || r.nextStation || '-'}
                      </td>
                    )}
                    {deptKey === 'fps' && <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.customer_order || r.customerOrder || '-'}</td>}

                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold', color: '#b45309', background: '#fffbeb'}}>{r.qty_sent || r.qtySent || '-'}</td>
                    
                    {/* SCENARIO: DISMANTLING SCRAP DATA */}
                    {deptKey === 'dismantling' && (
                      <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontSize: '0.85em', color: '#7f1d1d'}}>
                         {(r.ir_scrap || r.or_scrap || r.cage_scrap || r.ball_scrap || r.roller_scrap || r.seal_scrap || r.shield_scrap) ? (
                            `IR:${r.ir_scrap||0} | OR:${r.or_scrap||0} | Cage:${r.cage_scrap||0} | Roll/Ball:${(r.ball_scrap||0)+(r.roller_scrap||0)}`
                         ) : '-'}
                         {r.remark && <div style={{color: '#0369a1', marginTop: '4px', fontWeight: '600'}}>Note: {r.remark}</div>}
                         {r.ring_type && r.ring_type !== 'Whole Bearing' && <div style={{color: '#b45309', marginTop: '4px'}}>Sent: {r.ring_type}</div>}
                      </td>
                    )}

                    <td style={{padding: '12px 15px'}}>
                      <button type="button" onClick={() => handleEdit(r)} style={{marginRight: '8px', cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Edit">✏️</button>
                      <button type="button" onClick={() => handleDelete(r.id, deptKey)} style={{cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Delete">🗑️</button>
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

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif', background: '#f8fafc', minHeight: '100vh'}}>
      
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

      {/* Header & Tabs */}
      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '15px'}}>
        <h1 style={{fontSize: '1.8em', color: '#0f172a', margin: 0}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} 
              onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily('');}} 
              style={{padding: '10px 18px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#fff', color: activeTab === tab ? '#fff' : '#475569', border: '1px solid #cbd5e1', borderRadius: '6px', fontWeight: '600', transition: 'all 0.2s'}}>
              {tab.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Global Header Inputs */}
      <div style={{marginBottom: '24px', background: '#fff', padding: '20px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)'}}>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px'}}>
          <div>
            <label style={{display: 'block', fontWeight: '600', marginBottom: '8px', color: '#1e293b'}}>Variant / Type</label>
            <input list="variant-list" value={selectedVariant} onChange={handleVariantChange} placeholder="Type or Select Variant..." style={{width: '100%', padding: '10px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '1em'}} required />
          </div>
          <div>
            <label style={{display: 'block', fontWeight: '600', marginBottom: '8px', color: '#1e293b'}}>MO Number</label>
            <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." style={{width: '100%', padding: '10px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '1em'}} required />
          </div>
          <div>
            <label style={{display: 'block', fontWeight: '600', marginBottom: '8px', color: '#1e293b'}}>Target Production Qty</label>
            <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '10px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '6px', fontWeight: 'bold', color: '#16a34a', fontSize: '1em'}} />
          </div>
        </div>
        
        {/* IN / OUT Toggles */}
        <div style={{display: 'flex', gap: '15px', marginTop: '20px', paddingTop: '20px', borderTop: '1px dashed #cbd5e1'}}>
          <button type="button" onClick={() => setEntryMode('IN')} style={{flex: 1, padding: '12px', background: entryMode === 'IN' ? '#2563eb' : '#f1f5f9', color: entryMode === 'IN' ? '#fff' : '#64748b', border: entryMode === 'IN' ? 'none' : '1px solid #cbd5e1', borderRadius: '6px', fontWeight: 'bold', fontSize: '1.1em', cursor: 'pointer', transition: 'all 0.2s'}}>📥 RECEIVE (IN)</button>
          <button type="button" onClick={() => setEntryMode('OUT')} style={{flex: 1, padding: '12px', background: entryMode === 'OUT' ? '#ea580c' : '#f1f5f9', color: entryMode === 'OUT' ? '#fff' : '#64748b', border: entryMode === 'OUT' ? 'none' : '1px solid #cbd5e1', borderRadius: '6px', fontWeight: 'bold', fontSize: '1.1em', cursor: 'pointer', transition: 'all 0.2s'}}>📤 DISPATCH (OUT)</button>
        </div>
      </div>

      {/* DYNAMIC FORMS BASED ON TAB */}
      <div style={{background: '#fff', padding: '24px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)'}}>
        <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, activeTab)}>
          
          <h2 style={{marginTop: 0, marginBottom: '20px', color: entryMode === 'IN' ? '#1d4ed8' : '#c2410c', borderBottom: `2px solid ${entryMode === 'IN' ? '#bfdbfe' : '#fed7aa'}`, paddingBottom: '10px'}}>
            {activeTab.toUpperCase()} - {entryMode === 'IN' ? 'Receiving Log' : 'Dispatch Log'} {editingRecord && '(Editing Mode)'}
          </h2>

          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px'}}>
            
            {/* COMMON FIELDS PER MODE */}
            {entryMode === 'IN' ? (
              <>
                {renderField("In Date", "inDate", "date", null, true)}
                {renderField("Shift In", "shiftIn", "text", null, false, [1, 2, 3])}
                {renderField("Material In From", "materialInFrom", "text", "depts-list")}
              </>
            ) : (
              <>
                {renderField("Out Date", "outDate", "date", null, true)}
                {renderField("Shift Out", "shiftOut", "text", null, false, [1, 2, 3])}
                {activeTab !== 'fps' && renderField("Next Station", "nextStation", "text", "depts-list")}
              </>
            )}

            {/* ACCURATE SPECIFIC */}
            {activeTab === 'accurate' && entryMode === 'IN' && renderField("PC", "pc", "text")}
            
            {/* CPS SPECIFIC */}
            {activeTab === 'cps' && entryMode === 'IN' && (
              <>
                {renderField("Item", "item", "text")}
                {renderField("RC No", "rcNo", "text")}
                {renderField("Channel", "channel", "text", "channels-list")}
              </>
            )}

            {/* REWORK SPECIFIC */}
            {activeTab === 'rework' && (
              <div style={{gridColumn: 'span 1'}}><label style={{display:'block', fontWeight:'500', marginBottom:'4px', fontSize:'0.9em', color:'#334155'}}>Bearing Family</label><select name="bearingFamily" defaultValue={editingRecord?.bearing_family || bearingFamily} onChange={(e)=>setBearingFamily(e.target.value)} style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px'}}><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select></div>
            )}
            {activeTab === 'rework' && entryMode === 'IN' && renderField("Reason", "reason", "text")}

            {/* DISMANTLING SPECIFIC */}
            {activeTab === 'dismantling' && (
              <div style={{gridColumn: 'span 1'}}><label style={{display:'block', fontWeight:'500', marginBottom:'4px', fontSize:'0.9em', color:'#334155'}}>Bearing Family</label><select name="bearingFamily" defaultValue={editingRecord?.bearing_family || bearingFamily} onChange={(e)=>setBearingFamily(e.target.value)} style={{width:'100%', padding:'8px', border:'1px solid #cbd5e1', borderRadius:'4px'}}><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select></div>
            )}
            {activeTab === 'dismantling' && entryMode === 'IN' && renderField("Channel", "channel", "text", "channels-list")}
            
            {activeTab === 'dismantling' && entryMode === 'OUT' && (
               <>
                  <div style={{gridColumn: '1 / -1', background: '#fef2f2', padding: '15px', borderRadius: '6px', border: '1px solid #fca5a5', marginTop: '10px'}}>
                    <h4 style={{margin: '0 0 10px 0', color: '#991b1b'}}>Component Scrap Entry</h4>
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '15px'}}>
                      {renderField("IR Scrap", "irScrap", "number")}
                      {renderField("OR Scrap", "orScrap", "number")}
                      {renderField("Cage Scrap", "cageScrap", "number")}
                      {bearingFamily === 'TRB' ? renderField("Roller Scrap", "rollerScrap", "number") : renderField("Ball Scrap", "ballScrap", "number")}
                      {renderField("Seal Scrap", "sealScrap", "number")}
                      {renderField("Shield Scrap", "shieldScrap", "number")}
                    </div>
                  </div>
                  {renderField("Component Sent", "ringType", "text", null, false, [
                    {value: 'Whole Bearing', label: 'Whole Bearing'},
                    {value: 'IR', label: 'Inner Ring (IR)'},
                    {value: 'OR', label: 'Outer Ring (OR)'},
                    {value: 'Components', label: 'Mixed Components'}
                  ])}
                  <div style={{gridColumn: 'span 2'}}>{renderField("Remarks / Notes (Flow Description)", "remark", "text")}</div>
               </>
            )}

            {/* FPS SPECIFIC */}
            {activeTab === 'fps' && entryMode === 'OUT' && renderField("Customer Order", "customerOrder", "text")}

            {/* QUANTITY FIELD (ALWAYS LAST) */}
            {entryMode === 'IN' ? renderField("Quantity IN", "qtyIn", "number", null, true) : renderField(activeTab === 'dismantling' ? "Qty Sent (Rings/Bearings)" : "Quantity OUT", "qtySent", "number", null, true)}

          </div>

          <div style={{marginTop: '25px', textAlign: 'right'}}>
            {editingRecord && (
              <button type="button" onClick={() => setEditingRecord(null)} style={{marginRight: '15px', padding: '10px 20px', background: '#f1f5f9', color: '#475569', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold'}}>Cancel Edit</button>
            )}
            <button type="submit" style={{padding: '12px 30px', background: entryMode === 'IN' ? '#2563eb' : '#ea580c', color: '#fff', border: 'none', borderRadius: '4px', fontSize: '1.1em', fontWeight: 'bold', cursor: 'pointer', boxShadow: '0 4px 6px rgba(0,0,0,0.1)'}}>
              {editingRecord ? 'Update Entry' : 'Save Entry'}
            </button>
          </div>
        </form>
      </div>

      {/* LEDGER TABLE RENDERING */}
      {renderDepartmentLedger(activeTab, activeTab.toUpperCase() + ' Log')}

    </div>
  );
};

export default Afterchannel;

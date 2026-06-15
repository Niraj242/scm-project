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

  // Two-way filter logic for Variant + Date -> MO list
  useEffect(() => {
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
          if (!r.date) return true; // If no date recorded in backend, keep it
          const moTime = new Date(r.date).getTime();
          const diffDays = Math.abs((moTime - inputTime) / (1000 * 3600 * 24));
          return diffDays <= 2;
        });
      });
    }

    setAvailableMos(matchingMos);
  }, [selectedVariant, formDate, moCache]);

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
      setBearingScrapQty(''); 
      await fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  const handleEdit = (record) => {
    setMoNumber(record.mo || '');
    setSelectedVariant(record.type || record.bearing_type || '');
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
  const matchVariant = (l, v) => {
    const lType = String(l.bearing_type || l.type || l.bearingType || l.variant || '').replace(/\s+/g, '').toUpperCase();
    const vType = String(v).replace(/\s+/g, '').toUpperCase();
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

      const cpsLedger = ledgers.cps.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const cpsIn = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const cpsOut = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);

      const rwLedger = ledgers.rework.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const rwIn = rwLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const rwOut = rwLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);

      const disLedger = ledgers.dismantling.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const disIn = disLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const disOut = disLedger.reduce((sum, l) => !isScrapStation(l.next_station || l.nextStation) ? sum + (Number(l.qty_sent || l.qtySent) || 0) : sum, 0);
      
      const apLedger = ledgers.autopackaging.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const apIn = apLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const apOut = apLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);

      const fpsLedger = ledgers.fps.filter(l => (l.mo||'').toUpperCase() === mo && matchVariant(l, v));
      const fpsIn = fpsLedger.reduce((sum, l) => sum + (Number(l.qty_in || l.qtyIn) || 0), 0);
      const fpsOut = fpsLedger.reduce((sum, l) => sum + (Number(l.qty_sent || l.qtySent) || 0), 0);

      // Sum all scrap components
      const irScrap = disLedger.reduce((sum, l) => sum + (Number(l.ir_scrap) || 0), 0);
      const orScrap = disLedger.reduce((sum, l) => sum + (Number(l.or_scrap) || 0), 0);
      const cageScrap = disLedger.reduce((sum, l) => sum + (Number(l.cage_scrap) || 0), 0);
      const rollScrap = disLedger.reduce((sum, l) => sum + (Number(l.ball_scrap) || 0) + (Number(l.roller_scrap) || 0), 0);
      const accScrap = disLedger.reduce((sum, l) => sum + (Number(l.seal_scrap) || 0) + (Number(l.shield_scrap) || 0), 0);

      return {
        variant: v, prodQty, accIn, accOut, cpsIn, cpsOut, rwIn, rwOut, disIn, disOut,
        apIn, apOut, fpsIn, fpsOut,
        irScrap, orScrap, cageScrap, rollScrap, accScrap
      };
    });

    setSelectedMoDetail({ mo, breakdown });
  };

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
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px'}}>
          <span style={{fontWeight: 'bold', color: '#0f172a', fontSize: '1.2em'}}>{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '8px 12px', border: '1px solid #cbd5e1', borderRadius: '4px', width: '300px'}} />
        </div>
        No entries found.
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
              <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>MO</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Variant</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Material From</th>
                <th style={{padding: '12px 15px', color: '#1d4ed8', borderRight: '2px solid #cbd5e1', background: '#eff6ff'}}>Qty IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date OUT</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Next Station</th>
                <th style={{padding: '12px 15px', color: '#b45309', background: '#fffbeb', borderRight: '1px solid #e2e8f0'}}>Qty OUT</th>
                <th style={{padding: '12px 15px', color: '#475569'}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const isScrap = isScrapStation(r.next_station || r.nextStation);
                return (
                  <tr key={i} style={{borderBottom: '1px solid #e2e8f0', background: i % 2 === 0 ? '#fff' : '#f8fafc', transition: 'background 0.2s'}} onMouseEnter={(e) => e.currentTarget.style.background = '#e2e8f0'} onMouseLeave={(e) => e.currentTarget.style.background = i % 2 === 0 ? '#fff' : '#f8fafc'}>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.mo || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.bearing_type || r.type || r.item_type || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.in_date || r.inDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.material_in_from || r.materialInFrom || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '2px solid #cbd5e1', fontWeight: 'bold', color: '#1d4ed8', background: '#eff6ff'}}>{r.qty_in || r.qtyIn || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.out_date || r.outDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', color: isScrap ? '#dc2626' : '#334155', fontWeight: isScrap ? 'bold' : 'normal'}}>
                      {r.next_station || r.nextStation || '-'}
                      {isScrap && <span style={{marginLeft: '5px', fontSize: '0.8em'}}>⚠️</span>}
                    </td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold', color: '#b45309', background: '#fffbeb'}}>{r.qty_sent || r.qtySent || '-'}</td>
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

  const filteredMos = Object.keys(moCache).filter(mo => 
    mo.toUpperCase().includes(searchQuery.toUpperCase())
  );

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      
      <datalist id="depts-list">
        <option value="Channel" /><option value="Accurate" /><option value="CPS" />
        <option value="Rework" /><option value="Dismantling" /><option value="Autopackaging" />
        <option value="FPS" /><option value="Scrap" />
      </datalist>

      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'].map(ch => <option key={ch} value={ch} />)}
      </datalist>
      
      <datalist id="mo-list">
        {availableMos.map(mo => <option key={mo} value={mo} />)}
      </datalist>

      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily('');}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => {setActiveTab('summary'); setLedgerSearchQuery('');}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>
            📊 SUMMARY
          </button>
        </div>
      </div>

      {activeTab !== 'summary' && (
        <div style={{marginBottom: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
          <div style={{display: 'flex', gap: '20px'}}>
            
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Variant</label>
              <input type="text" value={selectedVariant} onChange={handleVariantChange} placeholder="Type Variant First to Filter MO..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>

            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>MO Number</label>
              <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>

            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Target Production Qty</label>
              <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', color: '#16a34a'}} />
            </div>
          </div>

          <div style={{display: 'flex', gap: '20px', marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #cbd5e1'}}>
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor:'pointer'}}>
              📥 LOG IN (Receiving)
            </button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor:'pointer'}}>
              📤 LOG OUT (Dispatch)
            </button>
            {editingRecord && (
              <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); setBearingFamily(''); }} style={{padding: '8px 20px', background: '#64748b', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', marginLeft: 'auto'}}>
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
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'accurate')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Accurate - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>PC No</label><input type="text" name="pcNo" defaultValue={editingRecord?.pc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Accurate - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
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
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>CPS Assembly - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Item</label><select name="itemType" defaultValue={editingRecord?.item_type || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>CPS Assembly - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
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
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Rework Station - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Bearing Family</label><select name="bearingFamily" value={bearingFamily} onChange={(e)=>setBearingFamily(e.target.value)} style={{width:'100%', padding:'6px'}}><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select></div>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineType" defaultValue={editingRecord?.line_type || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Rework Activity</label><input type="text" name="reworkActivity" defaultValue={editingRecord?.rework_activity || ''} style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Rework Station - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
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

        {/* ================= DISMANTLING TAB ================= */}
        {activeTab === 'dismantling' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Dismantling - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Bearing Family</label><select name="bearingFamily" value={bearingFamily} onChange={(e)=>setBearingFamily(e.target.value)} style={{width:'100%', padding:'6px'}} required><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select></div>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineType" defaultValue={editingRecord?.line_type || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Reason</label><select name="reason" defaultValue={editingRecord?.reason || ''} style={{width:'100%', padding:'6px'}}><option></option><option>D4</option><option>OD Mark</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Activity</label><select name="activity" defaultValue={editingRecord?.activity || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Ball Remove</option><option>Rivet Press</option></select></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Dismantling - Dispatch & Scrap Log</legend>
                  
                  <div style={{background: '#fee2e2', padding: '15px', borderRadius: '6px', border: '1px solid #ef4444', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 10px 0', color: '#b91c1c'}}>Auto-Scrap Calculator</h4>
                    <div style={{display: 'flex', gap: '15px', alignItems: 'flex-end'}}>
                      <div style={{flex: 1}}><label>Bearing Scrap Qty (Total)</label><input type="number" value={bearingScrapQty} onChange={(e) => setBearingScrapQty(e.target.value)} style={{width:'100%', padding:'6px'}} placeholder="e.g. 100" /></div>
                      <div style={{flex: 1, color: '#7f1d1d', fontSize: '0.9em', paddingBottom: '5px'}}>
                        <em>Select Family (DGBB/TRB) above to auto-fill balls vs rollers.</em>
                      </div>
                    </div>
                  </div>

                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '15px', marginBottom: '20px', paddingBottom: '15px', borderBottom: '1px dashed #cbd5e1'}}>
                    <div><label>IR Scrap</label><input type="number" name="irScrap" value={bearingScrapQty || editingRecord?.ir_scrap || ''} onChange={()=>{}} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>OR Scrap</label><input type="number" name="orScrap" value={bearingScrapQty || editingRecord?.or_scrap || ''} onChange={()=>{}} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Cage Scrap</label><input type="number" name="cageScrap" value={bearingScrapQty || editingRecord?.cage_scrap || ''} onChange={()=>{}} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Seal Scrap</label><input type="number" name="sealScrap" defaultValue={editingRecord?.seal_scrap || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shield Scrap</label><input type="number" name="shieldScrap" defaultValue={editingRecord?.shield_scrap || ''} style={{width:'100%', padding:'6px'}}/></div>
                    
                    {bearingFamily === 'DGBB' ? (
                      <div><label>Ball Scrap (Qty x 8)</label><input type="number" name="ballScrap" value={(bearingScrapQty ? bearingScrapQty * 8 : editingRecord?.ball_scrap) || ''} onChange={()=>{}} style={{width:'100%', padding:'6px', background: '#dbeafe'}}/></div>
                    ) : bearingFamily === 'TRB' ? (
                      <div><label>Roller Scrap (Qty x 8)</label><input type="number" name="rollerScrap" value={(bearingScrapQty ? bearingScrapQty * 8 : editingRecord?.roller_scrap) || ''} onChange={()=>{}} style={{width:'100%', padding:'6px', background: '#dbeafe'}}/></div>
                    ) : null}
                  </div>

                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Operator</label><input type="text" name="operator" defaultValue={editingRecord?.operator || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Remark</label><input type="text" name="remark" defaultValue={editingRecord?.remark || ''} style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Dismantling Processing')}
          </div>
        )}

        {/* ================= AUTOPACKAGING TAB ================= */}
        {activeTab === 'autopackaging' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'autopackaging')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Autopackaging - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Autopackaging - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('autopackaging', 'Autopackaging Station')}
          </div>
        )}

        {/* ================= FPS TAB ================= */}
        {activeTab === 'fps' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'fps')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>FPS - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>FPS - Final Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Customer Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('fps', 'FPS Storage')}
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
          <div className="modal-window" style={{background:'#fff', padding:'30px', borderRadius:'10px', width:'95%', maxWidth:'1500px', maxHeight:'85vh', overflowY:'auto', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)'}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', borderBottom:'3px solid #0f172a', paddingBottom:'15px', marginBottom:'25px'}}>
              <h2 style={{margin: 0, color: '#0f172a'}}>Cross-Department Flow Trace: <span style={{color: '#2563eb'}}>{selectedMoDetail.mo}</span></h2>
              <button onClick={() => setSelectedMoDetail(null)} style={{fontSize:'2em', cursor:'pointer', border:'none', background:'none', color: '#64748b', lineHeight: '1'}}>&times;</button>
            </div>
            
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85em', border: '1px solid #94a3b8'}}>
              <thead>
                <tr style={{background: '#334155', color: '#fff'}}>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', textAlign: 'left'}}>Variant Model</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#166534'}}>Prod Qty</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#1e40af'}}>Acc In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#1e40af'}}>Acc Out</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#86198f'}}>CPS In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#86198f'}}>CPS Out</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#b45309'}}>RW In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#b45309'}}>RW Out</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#374151'}}>Dis In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#374151'}}>Dis Out</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#16a34a'}}>AP In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#16a34a'}}>AP Out</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#083344'}}>FPS In</th>
                  <th rowSpan="2" style={{border: '1px solid #475569', padding: '12px', background: '#083344'}}>FPS Out</th>
                  <th colSpan="5" style={{border: '1px solid #475569', padding: '8px', background: '#991b1b', textAlign: 'center'}}>Granular Scrap Components (Dismantling)</th>
                </tr>
                <tr style={{background: '#7f1d1d', color: '#fff', fontSize: '0.9em'}}>
                  <th style={{border: '1px solid #475569', padding: '8px'}}>IR</th>
                  <th style={{border: '1px solid #475569', padding: '8px'}}>OR</th>
                  <th style={{border: '1px solid #475569', padding: '8px'}}>Cage</th>
                  <th style={{border: '1px solid #475569', padding: '8px'}}>Ball/Roller</th>
                  <th style={{border: '1px solid #475569', padding: '8px'}}>Seal/Shield</th>
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
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#374151'}}>{row.disOut || '-'}</td>

                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#16a34a'}}>{row.apIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#16a34a'}}>{row.apOut || '-'}</td>

                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#083344'}}>{row.fpsIn || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#083344'}}>{row.fpsOut || '-'}</td>
                    
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.irScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.orScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.cageScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.rollScrap || '-'}</td>
                    <td style={{border: '1px solid #cbd5e1', padding:'12px', color: '#991b1b'}}>{row.accScrap || '-'}</td>
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
